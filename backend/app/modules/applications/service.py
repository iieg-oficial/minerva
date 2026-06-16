import uuid

from sqlmodel import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.applications.repository import ApplicationRepository, RedirectURIRepository
from app.modules.applications.schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationWithSecrets,
    RedirectURICreate,
    RedirectURIRead,
)


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

    def create_application(self, data: ApplicationCreate) -> ApplicationWithSecrets:
        existing = self.repo.get_by_slug(data.slug)
        if existing:
            raise ConflictError(detail="Ya existe una aplicación con ese slug")

        raw_secret = str(uuid.uuid4())
        app = Application(
            name=data.name,
            slug=data.slug,
            description=data.description,
            homepage_url=data.homepage_url,
            client_id=str(uuid.uuid4()),
            client_secret_hash=hash_secret(raw_secret),
        )
        app = self.repo.create(app)
        result = ApplicationWithSecrets.model_validate(app)
        result.client_secret_hash = raw_secret
        return result

    def update_application(self, app_id: str, data: ApplicationUpdate) -> ApplicationRead:
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

        app = self.repo.update(app)
        return ApplicationRead.model_validate(app)

    def add_redirect_uri(self, app_id: str, data: RedirectURICreate) -> RedirectURIRead:
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        existing = self.redirect_repo.get_by_uri(app_id, data.uri)
        if existing:
            raise ConflictError(detail="Esa URI ya está registrada para esta aplicación")

        uri = RedirectURI(application_id=app_id, uri=data.uri, environment=data.environment)
        uri = self.redirect_repo.create(uri)
        return RedirectURIRead.model_validate(uri)

    def list_redirect_uris(self, app_id: str) -> list[RedirectURIRead]:
        app = self.repo.get_by_id(app_id)
        if not app:
            raise NotFoundError(detail="Aplicación no encontrada")

        uris = self.redirect_repo.list_by_application(app_id)
        return [RedirectURIRead.model_validate(u) for u in uris]

    def delete_redirect_uri(self, uri_id: str) -> None:
        self.redirect_repo.delete(uri_id)

    def validate_redirect_uri(self, client_id: str, redirect_uri: str) -> bool:
        app = self.repo.get_by_client_id(client_id)
        if not app:
            return False
        return self.redirect_repo.get_by_uri(app.id, redirect_uri) is not None
