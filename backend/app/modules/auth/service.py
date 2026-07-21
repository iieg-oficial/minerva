import logging
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import (
    create_access_token_rs256,
    create_id_token,
    hash_token,
    verify_pkce,
    verify_secret,
)
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.service import ApplicationService
from app.modules.auth.repository import AuthCodeRepository, RefreshTokenRepository, RefreshTokenRowLocked
from app.modules.auth.schemas import AuthRegister
from app.modules.authorization.service import AuthorizationService
from app.modules.groups.repository import GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.oidc.service import OIDCService, claims_for_scopes
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService
from app.shared.datetime_utils import as_utc

logger = logging.getLogger(__name__)


# Lo que Minerva puede poner en el callback (RFC 6749 §4.1.2 y §4.1.2.1). La lista es
# del protocolo, no de la llamada: por eso se limpia entera en cada respuesta.
_PARAMS_RESPUESTA = frozenset({"code", "state", "error", "error_description", "error_uri"})


def session_auth_time(claims: dict) -> int | None:
    """`auth_time` de la sesión del panel que trae el token, o `None` si no lo acredita.

    Es por sesión, no por usuario: dos navegadores del mismo usuario tienen cada uno el
    suyo, así que iniciar sesión en uno no rejuvenece al otro.

    **No cae a `iat`.** Un token emitido antes de que el claim existiera no trae prueba
    de cuándo se autenticó: `/auth/refresh` regeneraba `iat` sin re-autenticar a nadie,
    así que una sesión vieja recién refrescada exhibiría un `iat` reciente y pasaría un
    `max_age` que no cumple. Sin evidencia, se re-autentica (ver `_requires_reauth` y
    `reissue_session_token`); es un solo re-login y solo para sesiones previas al
    cambio, que además caducan solas dentro del TTL de sesión."""
    value = claims.get("auth_time")
    return int(value) if value is not None else None


def build_callback_url(redirect_uri: str, **params: str | None) -> str:
    """URL de vuelta al consumidor: preserva la query que la `redirect_uri` registrada
    ya traiga y codifica los valores (los `None` se omiten).

    Concatenar `?code=...` a mano rompía una `redirect_uri` que ya tuviera query (dos
    `?`) y alteraba cualquier `state` con caracteres reservados. El `state` debe volver
    exactamente igual (RFC 6749 §4.1.2): el cliente lo compara para detectar CSRF, así
    que alterarlo rompe su defensa.

    De la query previa se eliminan TODOS los parámetros de respuesta del protocolo, no
    solo los que se emiten en esta llamada: una `redirect_uri` registrada con
    `?state=fijo` daría dos claves iguales (y de cuál se queda el consumidor depende de
    su parser), y una registrada con `?code=fijo` haría que un callback de error llegara
    igualmente con un `code`."""
    parts = urlsplit(redirect_uri)
    query = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in _PARAMS_RESPUESTA
    ]
    query += [(key, value) for key, value in params.items() if value is not None]
    return urlunsplit(parts._replace(query=urlencode(query)))


class RefreshReuseError(BadRequestError):
    """Reúso de un refresh token ya rotado/revocado (posible robo): revoca la familia.
    Lleva los access_jti a blacklistear para que el router los ponga en Redis ANTES de
    confirmar la revocación en PG (fail-closed), y luego devuelva el error 400."""

    def __init__(self, blacklist_jtis: list[str], detail: str):
        super().__init__(detail=detail)
        self.blacklist_jtis = blacklist_jtis


class RefreshRotationInProgressError(ConflictError):
    """Contención concurrente real: otro request ya está rotando este MISMO refresh
    token en este instante (`FOR UPDATE NOWAIT` no consiguió el lock). No es reúso:
    NO revoca la familia, el ganador de la carrera sigue siendo válido. El cliente
    debe reintentar (p. ej. con backoff), no tratar esto como sesión revocada."""

    def __init__(self, detail: str = "El refresh token ya está siendo procesado por otra solicitud; reintente"):
        super().__init__(detail=detail)


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
        self.authz_service = AuthorizationService(session)
        self.user_role_repo = UserRoleRepository(session)
        self.group_user_repo = GroupUserRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    def register(self, data: AuthRegister) -> dict:
        from app.modules.users.schemas import UserCreate

        user_data = UserCreate(email=data.email, full_name=data.full_name, password=data.password)
        user = self.user_service.create_user(user_data)
        # El alta es un evento de autenticación (deja sesión abierta), así que registra
        # el último acceso igual que el login. `create_user` devuelve el schema de
        # lectura, no el modelo, así que se recarga.
        self._touch_last_login(self.user_repo.get_by_id(user.id))
        token = self.oidc_service.issue_session_token(user.id, user.email, user.full_name)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.effective_token_expire_minutes * 60,
        }

    def reissue_session_token(self, current_user: dict) -> dict:
        """Reemite el token de sesión interna (panel) a partir de los claims del
        token actual. RS256, como toda la firma del sistema.

        Conserva el `auth_time` original: refrescar el token alarga la sesión, no
        vuelve a autenticar al usuario. Si se renovara, un `max_age` nunca se
        cumpliría en una sesión que se refresca sola.

        Por eso mismo una sesión sin `auth_time` (emitida antes del claim) no se puede
        refrescar: `issue_session_token` le pondría uno de "ahora", convirtiendo en
        evidencia de autenticación algo que nunca lo fue. Se exige re-login."""
        if session_auth_time(current_user) is None:
            raise UnauthorizedError(detail="La sesión no acredita cuándo se autenticó; inicia sesión de nuevo")
        token = self.oidc_service.issue_session_token(
            user_id=current_user["sub"],
            email=current_user["email"],
            name=current_user.get("name", ""),
            application_slug=current_user.get("aud", "minerva"),
            roles=current_user.get("roles", []),
            permissions=current_user.get("permissions", []),
            auth_time=session_auth_time(current_user),
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.effective_token_expire_minutes * 60,
        }

    def _touch_last_login(self, user) -> None:
        """Registra el último acceso del usuario. Único punto de escritura de
        `last_login_at`, que es informativo: NO gobierna `auth_time` ni `max_age`, que
        son por sesión y viven en el token (ver `session_auth_time`)."""
        user.last_login_at = datetime.now(timezone.utc)
        self.user_repo.update(user)

    def login(self, email: str, password: str) -> dict:
        token = self.user_service.authenticate(email, password)
        self._touch_last_login(self.user_repo.get_by_email(email))
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

    def validate_client_and_redirect(self, client_id: str, redirect_uri: str) -> None:
        """Valida que la app exista, esté activa y que `redirect_uri` esté registrada.

        Se extrae como método propio porque hay que llamarlo ANTES de decidir si
        se redirige a login (Modo B, ver router): nunca se redirige a un destino
        sin validar primero que sea uno legítimo (evita open redirect)."""
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if app.status != "active":
            raise ForbiddenError(detail="Aplicación inactiva")
        if not self.app_service.validate_redirect_uri(client_id, redirect_uri):
            raise BadRequestError(detail="redirect_uri no autorizada para esta aplicación")

    def _requires_reauth(self, auth_time: int | None, prompt: str | None, max_age: int | None) -> bool:
        """`max_age` se evalúa contra el `auth_time` de ESTA sesión, no contra el último
        login del usuario: si fuera lo segundo, autenticarse en otro navegador
        rejuvenecería esta sesión y le dejaría pasar un `max_age` que ya no cumple.
        Sin `auth_time` no hay forma de acreditar frescura, así que se re-autentica."""
        if prompt == "login":
            return True
        if max_age is not None:
            if auth_time is None:
                return True
            return datetime.now(timezone.utc).timestamp() - auth_time > max_age
        return False

    def _has_app_access(self, user_id: str, app_slug: str) -> bool:
        """True si el usuario tiene al menos un rol asignado en la app (directo o
        por grupo), o si es administrador global de Minerva."""
        if self.authz_service.is_minerva_admin(user_id):
            return True
        _, role_slugs = self._get_user_permissions(user_id, app_slug)
        return bool(role_slugs)

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
        prompt: str | None = None,
        max_age: int | None = None,
        auth_time: int | None = None,
    ) -> tuple[str | None, str | None]:
        """`auth_time` es el instante de autenticación de la sesión que hace la
        solicitud (lo trae su token; ver `session_auth_time`): gobierna `max_age` y es
        lo que se graba en el código para que el `id_token` lo reporte. Los dos usos
        salen del mismo valor a propósito, para que lo que Minerva exige y lo que
        informa no puedan divergir.

        Devuelve `(redirect_url, reauth_reason)`. Si `reauth_reason` no es
        `None` (`"login"`, `"max_age"` o `"access_denied"`), el caller (router)
        decide la respuesta HTTP — no se modela como excepción porque no es un
        caso de error, es una señal de control de flujo esperada por
        `prompt`/`max_age` (OIDC Core 3.1.2.1) o de acceso denegado por rol."""
        app = self.app_service.get_application_by_client_id(client_id)
        self.validate_client_and_redirect(client_id, redirect_uri)

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

        # Clientes públicos (sin client_secret): PKCE es la única forma de ligar
        # el código al solicitante legítimo, así que es obligatorio.
        if app.client_secret_hash is None and code_challenge is None:
            raise BadRequestError(detail="code_challenge (PKCE) requerido para clientes públicos")

        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        if user.status != "active":
            raise ForbiddenError(detail="Usuario inactivo")

        if not self._has_app_access(user_id, app.slug):
            return None, "access_denied"

        if self._requires_reauth(auth_time, prompt, max_age):
            return None, ("login" if prompt == "login" else "max_age")

        # Se graba el auth_time de la sesión, NO el instante de emisión del código: un
        # SSO silencioso 6 h después sigue reportando esa autenticación de hace 6 h. Si
        # es None, `create_id_token` omite el claim, que es lo correcto: solo es
        # obligatorio con `max_age`, y ahí `_requires_reauth` ya forzó re-login arriba.
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
        return build_callback_url(redirect_uri, code=auth_code.code, state=state), None

    def exchange_token(
        self,
        client_id: str,
        code: str,
        redirect_uri: str,
        client_secret: str | None = None,
        code_verifier: str | None = None,
    ) -> dict:
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if app.status != "active":
            raise ForbiddenError(detail="Aplicación inactiva")

        if app.client_secret_hash is not None:
            if not client_secret or not verify_secret(client_secret, app.client_secret_hash):
                raise ForbiddenError(detail="client_secret inválido")
        elif not code_verifier:
            # Cliente público: sin secret, PKCE es obligatorio en el canje.
            raise BadRequestError(detail="code_verifier requerido (PKCE) para clientes públicos")

        auth_code = self.auth_code_repo.get_by_code(code)
        if not auth_code:
            raise BadRequestError(detail="Código de autorización inválido o ya usado")

        # El código está ligado al client y al redirect_uri con que se emitió:
        # ambos deben coincidir exactamente en el canje (RFC 6749 §4.1.3).
        if auth_code.client_id != client_id:
            raise BadRequestError(detail="El código no pertenece a esta aplicación")
        if auth_code.redirect_uri != redirect_uri:
            raise BadRequestError(detail="redirect_uri no coincide con el del código")

        if datetime.now(timezone.utc) > as_utc(auth_code.expires_at):
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
        if user.status != "active":
            raise ForbiddenError(detail="Usuario inactivo")

        if not self.auth_code_repo.mark_used(auth_code):
            raise BadRequestError(detail="Código de autorización inválido o ya usado")

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
        commit: bool = True,
    ) -> dict:
        """Emite el bundle de tokens (access + refresh + id_token) y persiste el
        refresh token. Compartido por el canje del código y la rotación. commit=False
        deja el nuevo refresh pendiente para que la rotación lo confirme tras Redis."""
        wants_openid = "openid" in scope.split()
        access_ttl = settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES
        jti = uuid.uuid4().hex
        kid, private_pem = self.oidc_service.get_active_private_pem()

        access_token = create_access_token_rs256(
            user_id=user.id,
            email=user.email,
            name=user.full_name,
            kid=kid,
            private_key_pem=private_pem,
            application_slug=app.slug,
            roles=roles,
            permissions=permissions,
            scope=scope,
            email_verified=user.auth_provider == "google",
            jti=jti,
            expires_minutes=access_ttl,
            typ="access",
        )

        raw_refresh = secrets.token_urlsafe(32)
        self.refresh_repo.create(
            token_hash=hash_token(raw_refresh),
            family_id=family_id,
            user_id=user.id,
            client_id=app.client_id,
            scope=scope or None,
            access_jti=jti,
            ttl_days=settings.MINERVA_REFRESH_TOKEN_TTL_DAYS,
            commit=commit,
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
            # el slug de la app). Lleva nonce y auth_time capturados en /authorize,
            # y claims de identidad filtrados por scope (OIDC Core 5.4).
            result["id_token"] = create_id_token(
                user_id=user.id,
                client_id=app.client_id,
                kid=kid,
                private_key_pem=private_pem,
                claims=claims_for_scopes(user, scope),
                nonce=nonce,
                auth_time=auth_time,
                expires_minutes=access_ttl,
            )
        return result

    def rotate_refresh_token(
        self, client_id: str, refresh_token_raw: str, client_secret: str | None = None, commit: bool = True
    ) -> tuple[dict, list[str]]:
        """Canjea un refresh token por uno nuevo (rotación) y un access token nuevo.

        Devuelve (respuesta, jtis_a_revocar). Si se reutiliza un token ya rotado o
        revocado (posible robo), revoca toda la familia y lanza RefreshReuseError.
        commit=False deja la rotación (o la revocación de familia) pendiente para que el
        router la confirme tras blacklistear en Redis (fail-closed)."""
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if app.status != "active":
            raise ForbiddenError(detail="Aplicación inactiva")
        if app.client_secret_hash is not None:
            if not client_secret or not verify_secret(client_secret, app.client_secret_hash):
                raise ForbiddenError(detail="client_secret inválido")

        # FOR UPDATE NOWAIT (no-op en SQLite): si otra rotación de ESTE MISMO token está
        # en curso ahora mismo, falla rápido en vez de esperar su commit. Eso es
        # contención concurrente, no reúso, así que NO revoca la familia (issue #38).
        try:
            refresh = self.refresh_repo.get_by_hash_for_update(hash_token(refresh_token_raw))
        except RefreshTokenRowLocked:
            raise RefreshRotationInProgressError()
        if not refresh:
            raise BadRequestError(detail="refresh token inválido")
        if refresh.client_id != client_id:
            raise BadRequestError(detail="El refresh token no pertenece a esta aplicación")

        if refresh.status != "active":
            # Con el lock ya adquirido arriba, esto no es una carrera en curso: es un
            # reúso genuino de un token que quedó rotado/revocado en el pasado (posible
            # robo). Revoca la familia y entrega sus access_jti para que el router los
            # blacklistee antes de confirmar.
            jtis = self._revoke_family_or_conflict(refresh.family_id, commit)
            raise RefreshReuseError(jtis, detail="refresh token ya utilizado; la sesión fue revocada por seguridad")

        if datetime.now(timezone.utc) > as_utc(refresh.expires_at):
            self.refresh_repo.revoke(refresh)
            raise BadRequestError(detail="refresh token expirado")

        user = self.user_repo.get_by_id(refresh.user_id)
        if not user or user.status != "active":
            raise ForbiddenError(detail="Usuario inválido o inactivo")

        if not self.refresh_repo.mark_rotated(refresh, commit=False):
            # Inalcanzable en la práctica: ya tenemos el lock de fila desde
            # get_by_hash_for_update, nadie más puede haber cambiado el status entre medio.
            # Se conserva como red de seguridad si algún día el lock deja de cubrir esta ruta.
            jtis = self._revoke_family_or_conflict(refresh.family_id, commit)
            raise RefreshReuseError(jtis, detail="refresh token ya utilizado; la sesión fue revocada por seguridad")

        perms, role_slugs = self._get_user_permissions(user.id, app.slug)
        response = self._issue_tokens(
            user=user,
            app=app,
            scope=refresh.scope or "",
            roles=role_slugs,
            permissions=perms,
            family_id=refresh.family_id,
            commit=commit,
        )
        return response, [refresh.access_jti] if refresh.access_jti else []

    def revoke_refresh_token(
        self, client_id: str, refresh_token_raw: str, client_secret: str | None = None, commit: bool = True
    ) -> list[str]:
        """Revoca un refresh token y toda su familia (RFC 7009). Devuelve los jtis
        de access tokens a poner en la blacklist. Idempotente y silencioso si el
        token no existe (no se filtra información). commit=False deja la revocación
        pendiente para que el router la confirme tras blacklistear los jtis en Redis."""
        app = self.app_service.get_application_by_client_id(client_id)
        if not app:
            raise BadRequestError(detail="Aplicación no encontrada")
        if app.client_secret_hash is not None:
            if not client_secret or not verify_secret(client_secret, app.client_secret_hash):
                raise ForbiddenError(detail="client_secret inválido")

        refresh = self.refresh_repo.get_by_hash(hash_token(refresh_token_raw))
        if not refresh or refresh.client_id != client_id:
            return []
        return self._revoke_family_or_conflict(refresh.family_id, commit)

    def _revoke_family_or_conflict(self, family_id: str, commit: bool) -> list[str]:
        """Revoca la familia traduciendo un lock contendido (otro miembro se está
        rotando ahora mismo) a un conflicto explícito de reintento, en vez de dejar
        que el caller se tope con `RefreshTokenRowLocked` crudo."""
        try:
            return self.refresh_repo.revoke_family(family_id, commit=commit)
        except RefreshTokenRowLocked:
            raise RefreshRotationInProgressError()

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
