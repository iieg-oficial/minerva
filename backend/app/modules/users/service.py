import logging

from sqlmodel import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_password, verify_password
from app.modules.audit.repository import AuditRepository
from app.modules.credentials.repository import CredentialTokenRepository
from app.modules.users.models import LINKABLE_STATUSES, User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserRead, UserStatusUpdate, UserUpdate

logger = logging.getLogger(__name__)


def _check_status_change(current: str, new: str) -> None:
    """`pending` solo lo asigna el alta sin contraseña: puesto a mano dejaría esperando una
    invitación a alguien que ya tiene contraseña."""
    if new == "pending" and current != "pending":
        raise BadRequestError(detail="El estado pendiente solo lo asigna el alta por invitación")


class UserService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = UserRepository(session)
        self.audit_repo = AuditRepository(session)
        self.credential_repo = CredentialTokenRepository(session)

    def get_user(self, user_id: str) -> UserRead:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")
        return UserRead.model_validate(user)

    def get_user_by_email(self, email: str) -> User | None:
        return self.repo.get_by_email(email)

    def list_users(self, offset: int = 0, limit: int = 100) -> tuple[list[UserRead], int]:
        users, total = self.repo.list_all(offset, limit)
        return [UserRead.model_validate(u) for u in users], total

    def create_user(self, data: UserCreate, commit: bool = True) -> UserRead:
        existing = self.repo.get_by_email(data.email)
        if existing:
            raise ConflictError(detail="El correo ya está registrado")

        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password) if data.password else None,
            # Sin contraseña queda pendiente hasta que la persona la fije con su invitación.
            status="active" if data.password else "pending",
            domain=data.domain,
        )

        user = self.repo.create(user, commit=commit)
        return UserRead.model_validate(user)

    def update_user(self, user_id: str, data: UserUpdate, commit: bool = True) -> UserRead:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        if data.full_name is not None:
            user.full_name = data.full_name
        email_changed = False
        if data.email is not None and data.email != user.email:
            existing = self.repo.get_by_email(data.email)
            if existing and existing.id != user_id:
                raise ConflictError(detail="El correo ya está registrado")
            user.email = data.email
            email_changed = True
        if data.password:
            user.hashed_password = hash_password(data.password)
            user.password_change_required = data.require_change
            # Con una contraseña asignada ya no espera su invitación.
            if user.status == "pending" and data.status is None:
                user.status = "active"
        if data.status is not None:
            _check_status_change(user.status, data.status)
            user.status = data.status
        if data.domain is not None:
            user.domain = data.domain
        # Un enlace pendiente no debe sobrevivir a un cambio de credenciales ni a una baja.
        if data.password or email_changed or user.status not in LINKABLE_STATUSES:
            self.credential_repo.invalidate_unused_for_user(user_id)

        user = self.repo.update(user, commit=commit)
        return UserRead.model_validate(user)

    def update_status(self, user_id: str, data: UserStatusUpdate, commit: bool = True) -> UserRead:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        _check_status_change(user.status, data.status)
        user.status = data.status
        if user.status not in LINKABLE_STATUSES:
            self.credential_repo.invalidate_unused_for_user(user_id)
        user = self.repo.update(user, commit=commit)
        return UserRead.model_validate(user)

    def change_own_password(self, user_id: str, current_password: str, new_password: str, commit: bool = True) -> None:
        """Cambio de contraseña por el propio usuario: exige la actual y retira la marca de
        cambio obligatorio. El caller invalida las sesiones antes de confirmar."""
        user = self.repo.get_by_id(user_id)
        if not user or not user.hashed_password or not verify_password(current_password, user.hashed_password):
            raise BadRequestError(detail="La contraseña actual no es correcta")
        user.hashed_password = hash_password(new_password)
        user.password_change_required = False
        # Un enlace de restablecimiento filtrado no debe poder pisar la contraseña recién elegida.
        self.credential_repo.invalidate_unused_for_user(user_id)
        self.repo.update(user, commit=commit)

    def revoke_refresh_tokens(self, user_id: str, commit: bool = True) -> list[str]:
        """Revoca los refresh tokens OIDC vigentes del usuario (parte de invalidar
        sus sesiones al cambiar credenciales/status). Devuelve los access_jti a
        blacklistear. La invalidación de los bearer/sesión (por `iat`) la resuelve
        el marcador en Redis desde el router. commit=False deja la revocación pendiente
        para confirmarla junto con el cambio, tras escribir las invalidaciones en Redis."""
        from app.modules.auth.repository import RefreshTokenRepository, RefreshTokenRowLocked

        try:
            return RefreshTokenRepository(self.session).revoke_all_for_user(user_id, commit=commit)
        except RefreshTokenRowLocked:
            # Contención real: uno de los refresh tokens del usuario se está rotando
            # ahora mismo (lock de fila tomado por esa transacción). No es un error de
            # negocio, es un conflicto temporal: el caller (router) debe reintentar.
            raise ConflictError(detail="Hay una rotación de token en curso para este usuario; reintente")

    def authenticate(self, email: str, password: str) -> str:
        user = self.repo.get_by_email(email)
        if not user or not user.hashed_password:
            raise BadRequestError(detail="Credenciales inválidas")

        if user.status != "active":
            raise BadRequestError(detail="Usuario inactivo o bloqueado")

        if not verify_password(password, user.hashed_password):
            raise BadRequestError(detail="Credenciales inválidas")

        from app.modules.oidc.service import OIDCService

        return OIDCService(self.session).issue_session_token(user.id, user.email, user.full_name)
