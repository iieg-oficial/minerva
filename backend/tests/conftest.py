import fakeredis.aioredis
import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import app.core.redis as redis_module
from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies.auth import (
    _panel_user_from_cookie,
    _resolve_token,
    get_current_panel_user,
    get_optional_panel_user,
)
from app.core.dependencies.db import get_db
from app.core.exceptions import UnauthorizedError
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


def require_test_database_url(url: str) -> None:
    """Guarda fail-closed antes de dropear/crear esquemas contra PostgreSQL real (issue
    #38): que exista MINERVA_TEST_POSTGRES_URL nunca es suficiente por sí solo, exige
    además que el nombre de la base termine en `_test` para no apuntar por error a una
    base de desarrollo/producción real."""
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not db_name.endswith("_test"):
        raise RuntimeError(
            f"MINERVA_TEST_POSTGRES_URL apunta a la base {db_name!r}, que no termina en "
            "'_test'. Abortando para no dropear/crear esquemas sobre una base que podría "
            "ser real; usa una base dedicada a pruebas (p. ej. 'minerva_test')."
        )


def grant_role(session: Session, application_id: str, user_id: str, slug: str = "member") -> None:
    """Asigna un rol al usuario en la aplicación indicada. Helper de fixtures:
    desde el issue #11 /authorize exige al menos un rol en la app del client_id.

    Get-or-create por (application_id, slug): dos llamadas para la misma app y el
    mismo slug (p. ej. dos usuarios con el rol "member" por defecto) comparten la
    fila en vez de duplicarla, ya inválido desde el constraint del issue #76."""
    role = session.exec(select(Role).where(Role.application_id == application_id, Role.slug == slug)).first()
    if not role:
        role = Role(application_id=application_id, name="Member", slug=slug)
        session.add(role)
    session.add(UserRole(user_id=user_id, role_id=role.id))


def override_get_db():
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_session] = override_get_db


# La suite legacy autentica el panel con Bearer `typ=session`; en producción el panel
# es cookie-only. Este override (SOLO test) acepta la cookie real —path de producción,
# usado por test_panel_session— o, en su defecto, un Bearer de sesión, para no reescribir
# ~70 llamadas existentes. El middleware CSRF real igual se aplica cuando hay cookie.
async def _override_panel_user(request: Request, session: Session = Depends(get_db), redis=Depends(get_redis)) -> dict:
    # Bearer PRIMERO: login/register fijan cookie en el jar del TestClient, y la suite
    # legacy cambia de identidad por Bearer; priorizarlo evita que una cookie residual
    # contamine esos tests. test_panel_session no manda Bearer → cae al path de cookie real.
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            return await _resolve_token(auth[7:], session, redis, expected_types={"session"}, audience="minerva")
        except ValueError as e:
            raise UnauthorizedError(detail=str(e))
    if request.cookies.get(settings.session_cookie_name):
        return await _panel_user_from_cookie(request, session, redis, optional=False)
    raise UnauthorizedError(detail="Token no proporcionado")


async def _override_optional_panel_user(
    request: Request, session: Session = Depends(get_db), redis=Depends(get_redis)
) -> dict | None:
    try:
        return await _override_panel_user(request, session, redis)
    except UnauthorizedError:
        return None


app.dependency_overrides[get_current_panel_user] = _override_panel_user
app.dependency_overrides[get_optional_panel_user] = _override_optional_panel_user
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
    # El middleware CSRF usa get_redis() directo (no por DI), así que fijamos también
    # el singleton del módulo para que apunte al mismo fake que ven las dependencias.
    redis_module._redis = fake
    yield fake
    app.dependency_overrides.pop(get_redis, None)
    userinfo_app.dependency_overrides.pop(get_redis, None)
    redis_module._redis = None


@pytest.fixture(autouse=True)
def enable_public_register():
    """El registro público está cerrado por defecto (R4). Los tests crean usuarios
    vía /auth/register, así que lo habilitan aquí; la prueba del cierre lo apaga
    explícitamente con monkeypatch."""
    original = settings.MINERVA_ENABLE_PUBLIC_REGISTER
    settings.MINERVA_ENABLE_PUBLIC_REGISTER = True
    yield
    settings.MINERVA_ENABLE_PUBLIC_REGISTER = original


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


def _mint_session_token(email: str) -> str:
    """Emite un token de sesión (`typ=session`) para un usuario ya creado. El panel es
    cookie-only, así que /register ya no devuelve el JWT; la suite legacy lo obtiene
    aquí para autenticar por Bearer (ver `_override_panel_user`)."""
    from app.modules.oidc.service import OIDCService

    with Session(test_engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        return OIDCService(session).issue_session_token(user.id, user.email, user.full_name)


@pytest.fixture
def make_session_token():
    """Devuelve el acuñador de tokens de sesión (para tests que necesitan el JWT de
    un usuario para autenticar por Bearer sin pasar por /auth/login)."""
    return _mint_session_token


@pytest.fixture
def admin_token(client):
    client.post(
        "/auth/register",
        json={
            "email": "testadmin@iieg.gob.mx",
            "full_name": "Test Admin",
            "password": "testpass123",
        },
    )
    # /register fija la cookie de sesión en el jar del TestClient; la limpiamos para
    # que la suite legacy (que autentica por Bearer) no dispare el middleware CSRF.
    client.cookies.clear()
    _grant_minerva_admin("testadmin@iieg.gob.mx")
    return _mint_session_token("testadmin@iieg.gob.mx")


@pytest.fixture
def non_admin_token(client):
    """Token de un usuario autenticado pero SIN rol de administrador."""
    client.post(
        "/auth/register",
        json={
            "email": "plainuser@iieg.gob.mx",
            "full_name": "Plain User",
            "password": "testpass123",
        },
    )
    client.cookies.clear()
    return _mint_session_token("plainuser@iieg.gob.mx")


@pytest.fixture
def admin_user(client, admin_token):
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    return response.json()["user"]
