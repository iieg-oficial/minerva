import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.database import get_session
from app.core.dependencies.db import get_db
from app.core.models import import_models
from app.core.redis import get_redis
from app.main import app
from app.modules.applications.models import Application
from app.modules.groups.models import UserRole
from app.modules.oidc.router import userinfo_app, wellknown_app
from app.modules.roles.models import Role
from app.modules.users.models import User

TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(TEST_DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def grant_role(session: Session, application_id: str, user_id: str, slug: str = "member") -> None:
    """Asigna un rol al usuario en la aplicación indicada. Helper de fixtures:
    desde el issue #11 /authorize exige al menos un rol en la app del client_id."""
    role = Role(application_id=application_id, name="Member", slug=slug)
    session.add(role)
    session.add(UserRole(user_id=user_id, role_id=role.id))


def override_get_db():
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_session] = override_get_db
# Las sub-apps (`.well-known`, `/userinfo`) mantienen su propio registro de
# overrides: son ASGI apps separadas, no heredan los de `app`.
wellknown_app.dependency_overrides[get_db] = override_get_db
userinfo_app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    import_models()
    SQLModel.metadata.create_all(test_engine)
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture(autouse=True)
def fresh_redis():
    """Inyecta un Redis falso aislado por test (el lifespan no corre con TestClient).

    Cada test recibe una instancia limpia, así el rate limiting no arrastra
    contadores entre tests. Devuelve el cliente por si el test quiere inspeccionarlo.
    """
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake
    userinfo_app.dependency_overrides[get_redis] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_redis, None)
    userinfo_app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def client():
    # Toda la firma es RS256: cualquier flujo HTTP que emita/valide tokens necesita
    # una clave de firma activa (en producción la siembra el lifespan).
    from app.modules.oidc.service import OIDCService

    with Session(test_engine) as session:
        OIDCService(session).ensure_active_signing_key()
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
        role = session.exec(select(Role).where(Role.application_id == app_row.id, Role.slug == "minerva.admin")).first()
        if not role:
            role = Role(application_id=app_row.id, name="Administrador", slug="minerva.admin")
            session.add(role)
            session.flush()
        link = session.exec(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)).first()
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
