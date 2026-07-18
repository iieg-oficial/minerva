import logging

from sqlmodel import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_password, verify_password
from app.modules.audit.repository import AuditRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserRead, UserStatusUpdate, UserUpdate

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = UserRepository(session)
        self.audit_repo = AuditRepository(session)

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

    def create_user(self, data: UserCreate) -> UserRead:
        existing = self.repo.get_by_email(data.email)
        if existing:
            raise ConflictError(detail="El correo ya está registrado")

        user = User(
            email=data.email,
            full_name=data.full_name,
            auth_provider=data.auth_provider,
            domain=data.domain,
        )
        if data.password:
            user.hashed_password = hash_password(data.password)

        user = self.repo.create(user)
        return UserRead.model_validate(user)

    def update_user(self, user_id: str, data: UserUpdate) -> UserRead:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        if data.full_name is not None:
            user.full_name = data.full_name
        if data.email is not None and data.email != user.email:
            existing = self.repo.get_by_email(data.email)
            if existing and existing.id != user_id:
                raise ConflictError(detail="El correo ya está registrado")
            user.email = data.email
        if data.password:
            user.hashed_password = hash_password(data.password)
        if data.status is not None:
            user.status = data.status
        if data.domain is not None:
            user.domain = data.domain

        user = self.repo.update(user)
        return UserRead.model_validate(user)

    def update_status(self, user_id: str, data: UserStatusUpdate) -> UserRead:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(detail="Usuario no encontrado")

        user.status = data.status
        user = self.repo.update(user)
        return UserRead.model_validate(user)

    def revoke_refresh_tokens(self, user_id: str) -> list[str]:
        """Revoca los refresh tokens OIDC vigentes del usuario (parte de invalidar
        sus sesiones al cambiar credenciales/status). Devuelve los access_jti a
        blacklistear. La invalidación de los bearer/sesión (por `iat`) la resuelve
        el marcador en Redis desde el router."""
        from app.modules.auth.repository import RefreshTokenRepository

        return RefreshTokenRepository(self.session).revoke_all_for_user(user_id)

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

    def get_or_create_google_user(self, email: str, name: str, provider_subject: str) -> User:
        user = self.repo.get_by_email(email)
        if user:
            if user.auth_provider != "google":
                raise BadRequestError(detail="El usuario ya existe con otro proveedor")
            user.full_name = name
            user.provider_subject = provider_subject
            user = self.repo.update(user)
        else:
            user = User(
                email=email,
                full_name=name,
                auth_provider="google",
                provider_subject=provider_subject,
                hashed_password=None,
            )
            user = self.repo.create(user)
        return user
