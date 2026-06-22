import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.security import (
    create_access_token,
    create_access_token_rs256,
    create_id_token,
    hash_token,
    verify_pkce,
    verify_secret,
)
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.service import ApplicationService
from app.modules.auth.repository import AuthCodeRepository, RefreshTokenRepository
from app.modules.auth.schemas import AuthRegister
from app.modules.groups.repository import GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.oidc.service import OIDCService
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.user_service = UserService(session)
        self.user_repo = UserRepository(session)
        self.auth_code_repo = AuthCodeRepository(session)
        self.refresh_repo = RefreshTokenRepository(session)
        self.app_service = ApplicationService(session)
        self.app_repo = ApplicationRepository(session)
        self.oidc_service = OIDCService(session)
        self.user_role_repo = UserRoleRepository(session)
        self.group_user_repo = GroupUserRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    def register(self, data: AuthRegister) -> dict:
        from app.modules.users.schemas import UserCreate

        user_data = UserCreate(email=data.email, full_name=data.full_name, password=data.password)
        user = self.user_service.create_user(user_data)
        token = create_access_token(user.id, user.email, user.full_name)
        return {"access_token": token, "token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}

    def login(self, email: str, password: str) -> dict:
        token = self.user_service.authenticate(email, password)
        user = self.user_repo.get_by_email(email)
        user.last_login_at = datetime.now(timezone.utc)
        self.user_repo.update(user)
        return {"access_token": token, "token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}

    def get_me(self, user_id: str) -> dict:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        direct_roles = self.user_role_repo.list_roles_for_user(user_id)
        group_ids = self.group_user_repo.list_groups_for_user(user_id)
        group_roles = []
        for gid in group_ids:
            group_roles.extend(self.group_role_repo.list_roles_for_group(gid))

        all_roles = list({r.id: r for r in direct_roles + group_roles}.values())

        all_permissions = []
        for role in all_roles:
            all_permissions.extend(self.role_perm_repo.list_permissions_by_role(role.id))

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "auth_provider": user.auth_provider,
                "status": user.status,
            },
            "roles": [
                {"id": r.id, "name": r.name, "slug": r.slug, "application_id": r.application_id} for r in all_roles
            ],
            "permissions": [
                {"id": p.id, "name": p.name, "slug": p.slug, "application_id": p.application_id}
                for p in all_permissions
            ],
        }

    def authorize(
        self,
        client_id: str,
        redirect_uri: str,
        user_id: str,
        state: str,
        scope: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        nonce: str | None = None,
    ) -> str:
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if app.status != "active":
            raise ForbiddenError(detail="Aplicación inactiva")

        if not self.app_service.validate_redirect_uri(client_id, redirect_uri):
            raise BadRequestError(detail="redirect_uri no autorizada para esta aplicación")

        # PKCE: si el cliente envía un challenge, solo se admite el método S256
        # (se rechaza "plain" por ser un downgrade inseguro). El método es
        # opcional y, si se omite junto al challenge, se asume S256.
        if code_challenge is not None:
            method = code_challenge_method or "S256"
            if method != "S256":
                raise BadRequestError(detail="code_challenge_method no soportado; use S256")
            code_challenge_method = method
        elif code_challenge_method is not None:
            raise BadRequestError(detail="code_challenge_method enviado sin code_challenge")

        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        if user.status != "active":
            raise ForbiddenError(detail="Usuario inactivo")

        auth_time = int(datetime.now(timezone.utc).timestamp())
        auth_code = self.auth_code_repo.create_code(
            client_id,
            user_id,
            redirect_uri,
            scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
            auth_time=auth_time,
        )
        return redirect_uri + f"?code={auth_code.code}&state={state}"

    def exchange_token(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> dict:
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")

        if not verify_secret(client_secret, app.client_secret_hash):
            raise ForbiddenError(detail="client_secret inválido")

        auth_code = self.auth_code_repo.get_by_code(code)
        if not auth_code:
            raise BadRequestError(detail="Código de autorización inválido o ya usado")

        # El código está ligado al client y al redirect_uri con que se emitió:
        # ambos deben coincidir exactamente en el canje (RFC 6749 §4.1.3).
        if auth_code.client_id != client_id:
            raise BadRequestError(detail="El código no pertenece a esta aplicación")
        if auth_code.redirect_uri != redirect_uri:
            raise BadRequestError(detail="redirect_uri no coincide con el del código")

        # expires_at se guarda en una columna sin timezone, por lo que vuelve naive;
        # lo normalizamos a UTC para poder compararlo con un datetime aware.
        expires_at = auth_code.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise BadRequestError(detail="Código de autorización expirado")

        # PKCE: si el código se emitió con challenge, exige un verifier válido.
        if auth_code.code_challenge is not None:
            if not code_verifier:
                raise BadRequestError(detail="code_verifier requerido (PKCE)")
            if not verify_pkce(code_verifier, auth_code.code_challenge):
                raise BadRequestError(detail="code_verifier inválido (PKCE)")

        user = self.user_repo.get_by_id(auth_code.user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        self.auth_code_repo.mark_used(auth_code)

        all_perms, all_role_slugs = self._get_user_permissions(user.id, app.slug)
        return self._issue_tokens(
            user=user,
            app=app,
            scope=auth_code.scope or "",
            roles=all_role_slugs,
            permissions=all_perms,
            family_id=str(uuid.uuid4()),
            nonce=auth_code.nonce,
            auth_time=auth_code.auth_time,
        )

    def _issue_tokens(
        self,
        user,
        app,
        scope: str,
        roles: list[str],
        permissions: list[str],
        family_id: str,
        nonce: str | None = None,
        auth_time: int | None = None,
    ) -> dict:
        """Emite el bundle de tokens (access + refresh + id_token) y persiste el
        refresh token. Compartido por el canje del código y la rotación."""
        wants_openid = "openid" in scope.split()
        access_ttl = settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES
        jti: str | None = uuid.uuid4().hex

        # El access token honra MINERVA_SIGNING_ALG (RS256 con JWKS o HS256 en
        # transición). El id_token es OIDC puro y SIEMPRE va firmado con RS256,
        # porque solo tiene sentido verificarlo contra el JWKS.
        if settings.MINERVA_SIGNING_ALG == "RS256" or wants_openid:
            kid, private_pem = self.oidc_service.get_active_private_pem()

        if settings.MINERVA_SIGNING_ALG == "RS256":
            access_token = create_access_token_rs256(
                user_id=user.id,
                email=user.email,
                name=user.full_name,
                kid=kid,
                private_key_pem=private_pem,
                application_slug=app.slug,
                roles=roles,
                permissions=permissions,
                jti=jti,
                expires_minutes=access_ttl,
            )
        else:
            access_token = create_access_token(
                user_id=user.id,
                email=user.email,
                name=user.full_name,
                application_slug=app.slug,
                roles=roles,
                permissions=permissions,
            )
            jti = None  # HS256 no lleva jti

        raw_refresh = secrets.token_urlsafe(32)
        self.refresh_repo.create(
            token_hash=hash_token(raw_refresh),
            family_id=family_id,
            user_id=user.id,
            client_id=app.client_id,
            scope=scope or None,
            access_jti=jti,
            ttl_days=settings.MINERVA_REFRESH_TOKEN_TTL_DAYS,
        )

        result = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": access_ttl * 60,
            "scope": scope or None,
            "refresh_token": raw_refresh,
        }
        if wants_openid:
            # aud del id_token = client_id (distinto del access token, cuyo aud es
            # el slug de la app). Lleva nonce y auth_time capturados en /authorize.
            result["id_token"] = create_id_token(
                user_id=user.id,
                email=user.email,
                name=user.full_name,
                client_id=app.client_id,
                kid=kid,
                private_key_pem=private_pem,
                nonce=nonce,
                auth_time=auth_time,
                expires_minutes=access_ttl,
            )
        return result

    def rotate_refresh_token(
        self, client_id: str, client_secret: str, refresh_token_raw: str
    ) -> tuple[dict, list[str]]:
        """Canjea un refresh token por uno nuevo (rotación) y un access token nuevo.

        Devuelve (respuesta, jtis_a_revocar). Si se reutiliza un token ya rotado o
        revocado (posible robo), revoca toda la familia y rechaza.
        """
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if not verify_secret(client_secret, app.client_secret_hash):
            raise ForbiddenError(detail="client_secret inválido")

        refresh = self.refresh_repo.get_by_hash(hash_token(refresh_token_raw))
        if not refresh:
            raise BadRequestError(detail="refresh token inválido")
        if refresh.client_id != client_id:
            raise BadRequestError(detail="El refresh token no pertenece a esta aplicación")

        if refresh.status != "active":
            # Reúso de un token ya rotado/revocado → posible robo: revoca la familia.
            self.refresh_repo.revoke_family(refresh.family_id)
            raise BadRequestError(detail="refresh token ya utilizado; la sesión fue revocada por seguridad")

        expires_at = refresh.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            self.refresh_repo.revoke(refresh)
            raise BadRequestError(detail="refresh token expirado")

        user = self.user_repo.get_by_id(refresh.user_id)
        if not user or user.status != "active":
            raise ForbiddenError(detail="Usuario inválido o inactivo")

        self.refresh_repo.mark_rotated(refresh)
        perms, role_slugs = self._get_user_permissions(user.id, app.slug)
        response = self._issue_tokens(
            user=user,
            app=app,
            scope=refresh.scope or "",
            roles=role_slugs,
            permissions=perms,
            family_id=refresh.family_id,
        )
        return response, [refresh.access_jti] if refresh.access_jti else []

    def revoke_refresh_token(self, client_id: str, client_secret: str, refresh_token_raw: str) -> list[str]:
        """Revoca un refresh token y toda su familia (RFC 7009). Devuelve los jtis
        de access tokens a poner en la blacklist. Idempotente y silencioso si el
        token no existe (no se filtra información)."""
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if not verify_secret(client_secret, app.client_secret_hash):
            raise ForbiddenError(detail="client_secret inválido")

        refresh = self.refresh_repo.get_by_hash(hash_token(refresh_token_raw))
        if not refresh or refresh.client_id != client_id:
            return []
        return self.refresh_repo.revoke_family(refresh.family_id)

    def _get_user_permissions(self, user_id: str, app_slug: str) -> tuple[list[str], list[str]]:
        direct_roles = self.user_role_repo.list_roles_for_user(user_id)
        group_ids = self.group_user_repo.list_groups_for_user(user_id)
        group_roles = []
        for gid in group_ids:
            group_roles.extend(self.group_role_repo.list_roles_for_group(gid))
        all_roles = list({r.id: r for r in direct_roles + group_roles}.values())
        app_roles = [r for r in all_roles if self._app_slug_by_id(r.application_id) == app_slug]
        permissions = []
        for role in app_roles:
            for perm in self.role_perm_repo.list_permissions_by_role(role.id):
                if perm.application_id == role.application_id:
                    permissions.append(perm.slug)
        return permissions, [r.slug for r in app_roles]

    def _app_slug_by_id(self, app_id: str) -> str:
        app = self.app_repo.get_by_id(app_id)
        if app:
            return app.slug
        return ""
