from typing import Generator

from sqlmodel import Session, create_engine

from app.core.config import settings

engine = create_engine(settings.effective_db_url, echo=settings.APP_DEBUG)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
