import pytest
from sqlmodel import Session, select

from app.modules.applications.models import Application
from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.users.models import User
from tests.conftest import test_engine

_MANIFEST = """
application:
  code: audited_manifest
  name: Audited Manifest
permissions: []
roles: []
"""


def test_user_and_application_mutations_are_audited(client, admin_token, admin_user):
    headers = {"Authorization": f"Bearer {admin_token}"}

    user = client.post(
        "/users",
        json={"email": "audited@iieg.gob.mx", "full_name": "Audited User", "password": "pass123456"},
        headers=headers,
    ).json()
    assert client.patch(f"/users/{user['id']}", json={"full_name": "Updated User"}, headers=headers).status_code == 200
    assert client.patch(f"/users/{user['id']}/status", json={"status": "inactive"}, headers=headers).status_code == 200

    app = client.post("/applications", json={"name": "Audited App", "slug": "audited-app"}, headers=headers).json()
    assert client.patch(f"/applications/{app['id']}", json={"name": "Updated App"}, headers=headers).status_code == 200
    assert client.post(f"/applications/{app['id']}/regenerate-secret", headers=headers).status_code == 200
    assert client.delete(f"/applications/{app['id']}", headers=headers).status_code == 204

    expected = {
        "user_create": ("user", user["id"]),
        "user_update": ("user", user["id"]),
        "user_status_update": ("user", user["id"]),
        "application_create": ("application", app["id"]),
        "application_update": ("application", app["id"]),
        "application_secret_regenerate": ("application", app["id"]),
        "application_delete": ("application", app["id"]),
    }
    with Session(test_engine) as session:
        logs = session.exec(select(AuditLog).where(AuditLog.action.in_(expected))).all()

    assert len(logs) == len(expected)
    for log in logs:
        assert (log.target_type, log.target_id) == expected[log.action]
        assert log.actor_user_id == admin_user["id"]
        assert log.event_metadata == {"result": "success"}


def test_failed_audit_rolls_back_business_mutations(client, admin_token, monkeypatch):
    def fail_audit(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(AuditRepository, "create", fail_audit)
    headers = {"Authorization": f"Bearer {admin_token}"}

    with pytest.raises(RuntimeError, match="boom"):
        client.post(
            "/users",
            json={"email": "rolled-back@iieg.gob.mx", "full_name": "Rolled Back", "password": "pass123456"},
            headers=headers,
        )
    with pytest.raises(RuntimeError, match="boom"):
        client.post(
            "/applications",
            json={"name": "Rolled Back App", "slug": "rolled-back-app"},
            headers=headers,
        )
    with pytest.raises(RuntimeError, match="boom"):
        client.post(
            "/applications/import-manifest",
            files={"file": ("manifest.minerva.yml", _MANIFEST, "application/yaml")},
            headers=headers,
        )

    with Session(test_engine) as session:
        assert session.exec(select(User).where(User.email == "rolled-back@iieg.gob.mx")).first() is None
        assert session.exec(select(Application).where(Application.slug == "rolled-back-app")).first() is None
        assert session.exec(select(Application).where(Application.slug == "audited_manifest")).first() is None


def test_sensitive_application_operations_audit_success_and_failure_without_credentials(
    client, admin_token, admin_user
):
    headers = {"Authorization": f"Bearer {admin_token}"}
    app = client.post("/applications", json={"name": "Secret App", "slug": "secret-app"}, headers=headers).json()

    assert (
        client.post(
            "/applications/import-manifest",
            files={"file": ("manifest.minerva.yml", _MANIFEST, "application/yaml")},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/applications/import-manifest",
            files={"file": ("broken.yml", "application: {}", "application/yaml")},
            headers=headers,
        ).status_code
        == 400
    )
    assert client.post(f"/applications/{app['id']}/regenerate-secret", headers=headers).status_code == 200
    assert client.post("/applications/missing/regenerate-secret", headers=headers).status_code == 404

    with Session(test_engine) as session:
        logs = session.exec(
            select(AuditLog).where(AuditLog.action.in_(["manifest_import", "application_secret_regenerate"]))
        ).all()

    assert sorted(log.event_metadata["result"] for log in logs) == ["failure", "failure", "success", "success"]
    assert all(log.actor_user_id == admin_user["id"] for log in logs)
    assert all("secret" not in str(log.event_metadata).lower() for log in logs)
    assert all(_MANIFEST.strip() not in str(log.event_metadata) for log in logs)
