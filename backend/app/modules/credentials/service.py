import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import hash_password, hash_token
from app.modules.applications.models import Application
from app.modules.authorization.service import AuthorizationService
from app.modules.credentials.models import CredentialToken
from app.modules.credentials.repository import CredentialTokenRepository
from app.modules.credentials.schemas import CredentialDestination, CredentialInspection, CredentialLink
from app.modules.users.models import LINKABLE_STATUSES
from app.modules.users.repository import UserRepository
from app.shared.datetime_utils import as_utc

# Un solo mensaje para enlace inexistente, usado o vencido: no revela cuál de los tres es.
INVALID_LINK_DETAIL = "El enlace no es válido, ya se usó o expiró. Pide uno nuevo a un administrador."


def _ttl(purpose: str) -> timedelta:
    if purpose == "invite":
        return timedelta(hours=settings.CREDENTIAL_INVITE_TTL_HOURS)
    if purpose == "reset":
        return timedelta(hours=settings.CREDENTIAL_RESET_TTL_HOURS)
    return timedelta(minutes=settings.CREDENTIAL_FORCED_CHANGE_TTL_MINUTES)


def destination_of(app: Application) -> CredentialDestination:
    assert app.homepage_url is not None
    return CredentialDestination(id=app.id, name=app.display_name or app.name, homepage_url=app.homepage_url)


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


class CredentialService:
    """Enlaces de un solo uso para fijar la contraseña: invitación (alta sin credencial),
    restablecimiento (lo emite un admin) y cambio obligatorio (lo emite el login)."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = CredentialTokenRepository(session)
        self.user_repo = UserRepository(session)
        self.authorization = AuthorizationService(session)

    def issue_token(
        self,
        user_id: str,
        purpose: str,
        created_by: str | None = None,
        commit: bool = True,
        application_id: str | None = None,
    ) -> tuple[str, datetime]:
        """Emite un token nuevo y devuelve su valor en claro (única vez que existe fuera
        del hash). Un token nuevo invalida los anteriores del usuario: solo el último sirve."""
        raw = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + _ttl(purpose)
        self.repo.invalidate_unused_for_user(user_id)
        self.repo.create(
            CredentialToken(
                user_id=user_id,
                token_hash=hash_token(raw),
                purpose=purpose,
                expires_at=expires_at,
                created_by=created_by,
                application_id=application_id,
            ),
            commit=commit,
        )
        return raw, expires_at

    def destinations(self, user_id: str) -> list[CredentialDestination]:
        if not self.user_repo.get_by_id(user_id):
            raise NotFoundError(detail="Usuario no encontrado")
        return [destination_of(app) for app in self.authorization.get_user_applications(user_id)]

    def issue_link(
        self,
        user_id: str,
        created_by: str | None = None,
        commit: bool = True,
        application_id: str | None = None,
    ) -> CredentialLink:
        """Enlace para entregar a la persona: invitación si sigue pendiente, restablecimiento
        si no. El token va en el fragmento (`#`): el navegador no lo envía al servidor, así
        que no queda en logs de acceso ni en el `Referer`.

        Con `application_id`, al fijar la contraseña se manda a la persona a esa aplicación
        en vez del login de Minerva. Solo se acepta una de `destinations()`."""
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        if user.status not in LINKABLE_STATUSES:
            raise BadRequestError(detail="La cuenta está inactiva o suspendida; reactívala antes de generar el enlace")
        destination = None
        if application_id is not None:
            destination = next((d for d in self.destinations(user.id) if d.id == application_id), None)
            if destination is None:
                raise BadRequestError(
                    detail="La persona no tiene acceso a esa aplicación o la aplicación no tiene página de inicio"
                )
        purpose = "invite" if user.status == "pending" else "reset"
        raw, expires_at = self.issue_token(
            user.id, purpose, created_by=created_by, commit=commit, application_id=application_id
        )
        return CredentialLink(
            url=f"{settings.FRONTEND_URL}/activar#token={raw}",
            purpose=purpose,
            expires_at=expires_at,
            application=destination,
        )

    def _get_valid(self, raw: str) -> CredentialToken:
        token = self.repo.get_by_hash(hash_token(raw))
        if not token or token.used_at is not None or datetime.now(timezone.utc) > as_utc(token.expires_at):
            raise BadRequestError(detail=INVALID_LINK_DETAIL)
        return token

    def inspect(self, raw: str) -> CredentialInspection:
        token = self._get_valid(raw)
        user = self.user_repo.get_by_id(token.user_id)
        if not user:
            raise BadRequestError(detail=INVALID_LINK_DETAIL)
        # Se revalida al abrir el enlace: la aplicación pudo desactivarse, perder su
        # `homepage_url` o retirarle los roles a la persona desde que se emitió.
        destination = None
        if token.application_id:
            destination = next((d for d in self.destinations(user.id) if d.id == token.application_id), None)
        return CredentialInspection(
            purpose=token.purpose,
            email=mask_email(user.email),
            expires_at=as_utc(token.expires_at),
            application=destination,
        )

    def consume(self, raw: str, new_password: str, commit: bool = True) -> CredentialToken:
        """Fija la contraseña con el enlace y lo quema. Activa al usuario pendiente y retira
        la marca de cambio obligatorio. Con commit=False el caller confirma después de
        invalidar las sesiones previas."""
        token = self._get_valid(raw)
        user = self.user_repo.get_by_id(token.user_id)
        if not user or user.status not in LINKABLE_STATUSES or not self.repo.claim(token.id):
            raise BadRequestError(detail=INVALID_LINK_DETAIL)
        user.hashed_password = hash_password(new_password)
        user.password_change_required = False
        if user.status == "pending":
            user.status = "active"
        self.user_repo.update(user, commit=commit)
        return token
