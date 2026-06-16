import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.core.database import get_session
from app.core.dependencies.db import get_db
from app.core.models import import_models
from app.main import app

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
    return response.json()["access_token"]


@pytest.fixture
def admin_user(client, admin_token):
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    return response.json()["user"]
