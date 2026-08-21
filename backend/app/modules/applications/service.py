import uuid
from ipaddress import ip_address
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.applications.repository import ApplicationRepository, RedirectURIRepository
from app.modules.applications.schemas import (
    ApplicationBranding,
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationWithSecrets,
    RedirectURICreate,
    RedirectURIRead,
)


def is_safe_redirect_uri(uri: str) -> bool:
    try:
        parsed = urlsplit(uri)
        parsed.port
    except ValueError:
        return False

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return False
    if parsed.scheme == "https" or not settings.is_production:
        return True
    if parsed.hostname == "localhost":
        return True
    try:
        return ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


class ApplicationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = ApplicationRepository(session)
        self.redirect_repo = RedirectURIRepository(session)

    def get_application(self, app_id: str) -> ApplicationRead:
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")
        return ApplicationRead.model_validate(app)

    def get_application_by_slug(self, slug: str) -> Application:
        return self.repo.get_by_slug(slug)

    def get_application_by_client_id(self, client_id: str) -> Application:
        return self.repo.get_by_client_id(client_id)

    def list_applications(self, offset: int = 0, limit: int = 100) -> tuple[list[ApplicationRead], int]:
        apps, total = self.repo.list_all(offset, limit)
        return [ApplicationRead.model_validate(a) for a in apps], total

    def create_application(self, data: ApplicationCreate, commit: bool = True) -> ApplicationWithSecrets:
        existing = self.repo.get_by_slug(data.slug)
        if existing:
            raise ConflictError(detail="Ya existe una aplicación con ese slug")

        raw_secret = None if data.is_public else str(uuid.uuid4())
        app = Application(
            name=data.name,
            slug=data.slug,
            description=data.description,
            homepage_url=data.homepage_url,
            client_id=str(uuid.uuid4()),
            client_secret_hash=hash_secret(raw_secret) if raw_secret is not None else None,
        )
        app = self.repo.create(app, commit=commit)
        result = ApplicationWithSecrets.model_validate(app)
        result.client_secret_hash = raw_secret
        return result

    def delete_application(self, app_id: str, commit: bool = True) -> None:
        """Elimina la aplicación y todo lo derivado de ella (permisos, roles,
        redirect URIs y asignaciones). Operación destructiva e irreversible."""
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")
        self.repo.delete(app, commit=commit)

    def regenerate_secret(self, app_id: str, commit: bool = True) -> ApplicationWithSecrets:
        """Genera un nuevo client_secret para la aplicación y lo devuelve una sola vez.

        Útil cuando se perdió el secret original (solo se muestra al crear) o para
        rotarlo. El client_id no cambia.
        """
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        raw_secret = str(uuid.uuid4())
        app.client_secret_hash = hash_secret(raw_secret)
        app = self.repo.update(app, commit=commit)
        result = ApplicationWithSecrets.model_validate(app)
        result.client_secret_hash = raw_secret
        return result

    def update_application(self, app_id: str, data: ApplicationUpdate, commit: bool = True) -> ApplicationRead:
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        if data.name is not None:
            app.name = data.name
        if data.description is not None:
            app.description = data.description
        if data.homepage_url is not None:
            app.homepage_url = data.homepage_url
        if data.status is not None:
            app.status = data.status
        if data.display_name is not None:
            app.display_name = data.display_name
        if data.logo_url is not None:
            app.logo_url = data.logo_url
        if data.brand_color is not None:
            app.brand_color = data.brand_color

        app = self.repo.update(app, commit=commit)
        return ApplicationRead.model_validate(app)

    def get_branding(self, client_id: str) -> ApplicationBranding:
        """Branding público de una app por client_id, para la pantalla de login.
        Solo devuelve datos no sensibles."""
        app = self.repo.get_by_client_id(client_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")
        return ApplicationBranding.model_validate(app, from_attributes=True)

    def add_redirect_uri(self, app_id: str, data: RedirectURICreate) -> RedirectURIRead:
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")
        if not is_safe_redirect_uri(data.uri):
            raise BadRequestError(detail="redirect_uri inválida o insegura")

        existing = self.redirect_repo.get_by_uri(app_id, data.uri)
        if existing:
            raise ConflictError(detail="Esa URI ya está registrada para esta aplicación")

        uri = RedirectURI(application_id=app_id, uri=data.uri, environment=data.environment)
        try:
            uri = self.redirect_repo.create(uri)
        except IntegrityError:
            # Ver RoleService.create_role: la comprobación previa no cierra la carrera
            # entre dos altas concurrentes; el constraint de BD sí (issue #76).
            self.session.rollback()
            raise ConflictError(detail="Esa URI ya está registrada para esta aplicación")
        return RedirectURIRead.model_validate(uri)

    def list_redirect_uris(self, app_id: str) -> list[RedirectURIRead]:
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        uris = self.redirect_repo.list_by_application(app_id)
        return [RedirectURIRead.model_validate(u) for u in uris]

    def validate_redirect_uri(self, client_id: str, redirect_uri: str) -> bool:
        if not is_safe_redirect_uri(redirect_uri):
            return False
        app = self.repo.get_by_client_id(client_id)
        if not app:
            return False
        return self.redirect_repo.get_by_uri(app.id, redirect_uri) is not None
