import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.database import get_session
from app.core.dependencies.db import get_db
from app.core.models import import_models
from app.main import app
from app.modules.applications.models import Application
from app.modules.groups.models import UserRole
from app.modules.roles.models import Role
from app.modules.users.models import User

TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(TEST_DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def override_get_db():
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_session] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    import_models()
    SQLModel.metadata.create_all(test_engine)
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def client():
    return TestClient(app)


def _grant_minerva_admin(email: str) -> None:
    """Asigna el rol global minerva.admin a un usuario (creando app/rol si faltan).

    El seed real corre en el lifespan, que no se dispara con TestClient sin `with`,
    por eso los tests preparan el rol aquí.
    """
    with Session(test_engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        app_row = session.exec(select(Application).where(Application.slug == "minerva")).first()
        if not app_row:
            app_row = Application(name="Minerva", slug="minerva", status="active")
            session.add(app_row)
            session.flush()
        role = session.exec(
            select(Role).where(Role.application_id == app_row.id, Role.slug == "minerva.admin")
        ).first()
        if not role:
            role = Role(application_id=app_row.id, name="Administrador", slug="minerva.admin")
            session.add(role)
            session.flush()
        link = session.exec(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        ).first()
        if not link:
            session.add(UserRole(user_id=user.id, role_id=role.id))
        session.commit()


@pytest.fixture
def admin_token(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "testadmin@iieg.gob.mx",
            "full_name": "Test Admin",
            "password": "testpass123",
        },
    )
    _grant_minerva_admin("testadmin@iieg.gob.mx")
    return response.json()["access_token"]


@pytest.fixture
def non_admin_token(client):
    """Token de un usuario autenticado pero SIN rol de administrador."""
    response = client.post(
        "/auth/register",
        json={
            "email": "plainuser@iieg.gob.mx",
            "full_name": "Plain User",
            "password": "testpass123",
        },
    )
    return response.json()["access_token"]


@pytest.fixture
def admin_user(client, admin_token):
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    return response.json()["user"]
