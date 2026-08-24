import pytest
from sqlmodel import Session, select

from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.groups.models import GroupRole
from app.modules.roles.models import Role
from tests.conftest import test_engine


def test_authorization_mutations_are_audited(client, admin_token, admin_user):
    headers = {"Authorization": f"Bearer {admin_token}"}
    app = client.post("/applications", json={"name": "Audit RBAC", "slug": "audit-rbac"}, headers=headers).json()
    user = client.post(
        "/users",
        json={"email": "audit-rbac@iieg.gob.mx", "full_name": "Audit RBAC", "password": "pass123456"},
        headers=headers,
    ).json()
    role = client.post(
        f"/roles?application_id={app['id']}",
        json={"name": "Audited Role", "slug": "audit-rbac.role"},
        headers=headers,
    ).json()
    permission = client.post(
        f"/permissions?application_id={app['id']}",
        json={"name": "Audited Permission", "slug": "audit-rbac.resource.read"},
        headers=headers,
    ).json()
    group = client.post("/groups", json={"name": "Audited Group", "slug": "audited-group"}, headers=headers).json()

    assert client.patch(f"/roles/{role['id']}", json={"name": "Updated Role"}, headers=headers).status_code == 200
    assert (
        client.patch(
            f"/permissions/{permission['id']}", json={"name": "Updated Permission"}, headers=headers
        ).status_code
        == 200
    )
    assert client.patch(f"/groups/{group['id']}", json={"name": "Updated Group"}, headers=headers).status_code == 200

    links = (
        (f"/roles/{role['id']}/permissions/{permission['id']}", "post", 201),
        (f"/roles/{role['id']}/permissions/{permission['id']}", "delete", 204),
        (f"/groups/{group['id']}/users/{user['id']}", "post", 201),
        (f"/groups/{group['id']}/users/{user['id']}", "delete", 204),
        (f"/groups/{group['id']}/roles/{role['id']}", "post", 201),
        (f"/groups/{group['id']}/roles/{role['id']}", "delete", 204),
        (f"/groups/users/{user['id']}/roles/{role['id']}", "post", 201),
        (f"/groups/users/{user['id']}/roles/{role['id']}", "delete", 204),
    )
    for path, method, status in links:
        assert getattr(client, method)(path, headers=headers).status_code == status

    assert client.delete(f"/roles/{role['id']}", headers=headers).status_code == 204

    expected = {
        "role_create": ("role", role["id"], app["id"]),
        "role_update": ("role", role["id"], app["id"]),
        "role_delete": ("role", role["id"], app["id"]),
        "permission_create": ("permission", permission["id"], app["id"]),
        "permission_update": ("permission", permission["id"], app["id"]),
        "group_create": ("group", group["id"], None),
        "group_update": ("group", group["id"], None),
        "role_permission_add": ("role_permission", f"{role['id']}:{permission['id']}", app["id"]),
        "role_permission_remove": ("role_permission", f"{role['id']}:{permission['id']}", app["id"]),
        "group_user_add": ("group_user", f"{group['id']}:{user['id']}", None),
        "group_user_remove": ("group_user", f"{group['id']}:{user['id']}", None),
        "group_role_add": ("group_role", f"{group['id']}:{role['id']}", app["id"]),
        "group_role_remove": ("group_role", f"{group['id']}:{role['id']}", app["id"]),
        "user_role_add": ("user_role", f"{user['id']}:{role['id']}", app["id"]),
        "user_role_remove": ("user_role", f"{user['id']}:{role['id']}", app["id"]),
    }
    with Session(test_engine) as session:
        logs = session.exec(select(AuditLog).where(AuditLog.action.in_(expected))).all()

    assert len(logs) == len(expected)
    for log in logs:
        assert (log.target_type, log.target_id, log.application_id) == expected[log.action]
        assert log.actor_user_id == admin_user["id"]
        assert log.event_metadata == {"result": "success"}


def test_failed_audit_rolls_back_authorization_mutations(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    app = client.post("/applications", json={"name": "Rollback RBAC", "slug": "rollback-rbac"}, headers=headers).json()
    role = client.post(
        f"/roles?application_id={app['id']}",
        json={"name": "Existing Role", "slug": "rollback-rbac.existing"},
        headers=headers,
    ).json()
    group = client.post("/groups", json={"name": "Rollback Group", "slug": "rollback-group"}, headers=headers).json()

    def fail_audit(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(AuditRepository, "create", fail_audit)

    with pytest.raises(RuntimeError, match="boom"):
        client.post(
            f"/roles?application_id={app['id']}",
            json={"name": "Rolled Back Role", "slug": "rollback-rbac.rolled-back"},
            headers=headers,
        )
    with pytest.raises(RuntimeError, match="boom"):
        client.post(f"/groups/{group['id']}/roles/{role['id']}", headers=headers)

    with Session(test_engine) as session:
        assert session.exec(select(Role).where(Role.slug == "rollback-rbac.rolled-back")).first() is None
        assert (
            session.exec(
                select(GroupRole).where(GroupRole.group_id == group["id"], GroupRole.role_id == role["id"])
            ).first()
            is None
        )
