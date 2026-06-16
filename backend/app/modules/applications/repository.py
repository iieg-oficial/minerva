from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.applications.models import Application, RedirectURI


class ApplicationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, app_id: str) -> Application | None:
        return self.session.get(Application, app_id)

    def get_by_slug(self, slug: str) -> Application | None:
        statement = select(Application).where(Application.slug == slug)
        return self.session.exec(statement).first()

    def get_by_client_id(self, client_id: str) -> Application | None:
        statement = select(Application).where(Application.client_id == client_id)
        return self.session.exec(statement).first()

    def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[Application], int]:
        statement = select(Application).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(Application)).all()
        return items, len(total)

    def create(self, app: Application) -> Application:
        self.session.add(app)
        self.session.commit()
        self.session.refresh(app)
        return app

    def update(self, app: Application) -> Application:
        app.updated_at = datetime.now(timezone.utc)
        self.session.add(app)
        self.session.commit()
        self.session.refresh(app)
        return app


class RedirectURIRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_application(self, app_id: str) -> list[RedirectURI]:
        statement = select(RedirectURI).where(RedirectURI.application_id == app_id)
        return self.session.exec(statement).all()

    def get_by_uri(self, app_id: str, uri: str) -> RedirectURI | None:
        statement = select(RedirectURI).where(
            RedirectURI.application_id == app_id,
            RedirectURI.uri == uri,
        )
        return self.session.exec(statement).first()

    def create(self, redirect_uri: RedirectURI) -> RedirectURI:
        self.session.add(redirect_uri)
        self.session.commit()
        self.session.refresh(redirect_uri)
        return redirect_uri

    def delete(self, redirect_uri: RedirectURI) -> None:
        self.session.delete(redirect_uri)
        self.session.commit()
