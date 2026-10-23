"""Administración delegada por aplicación (#201).

Un consumidor confidencial administra los usuarios y roles de SU aplicación en nombre de
la persona que lo pide: access token de la persona + credenciales del client. Cubre la
guarda (las dos pruebas, el `aud`, el permiso `{app}.access.manage`) y las cuatro reglas
contra escalamiento: no tocarse a sí mismo, no repartir ni retirar la administración
delegada, resetear solo cuentas exclusivas de la app y no salir de la propia aplicación.
"""

import pytest
from sqlmodel import Session, select

from app.core.security import create_access_token_rs256, hash_secret
from app.modules.applications.models import Application
from app.modules.audit.models import AuditLog
from app.modules.groups.models import Group, GroupRole, GroupUser, UserRole
from app.modules.oidc.service import OIDCService
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import test_engine

SECRET = "secreto-mariachi-t"
OTHER_SECRET = "secreto-vine-t"


def _user(session: Session, email: str, status: str = "active") -> User:
    user = User(email=email, full_name=f"Persona {email.split('@')[0]}", status=status)
    session.add(user)
    session.flush()
    return user


def _role(session: Session, app_id: str, slug: str, perm_slug: str | None = None) -> Role:
    role = Role(application_id=app_id, name=slug.capitalize(), slug=slug)
    session.add(role)
    session.flush()
    if perm_slug:
        perm = Permission(application_id=app_id, name=perm_slug, slug=perm_slug)
        session.add(perm)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    return role


@pytest.fixture
def ctx(client):
    """`mariachi-t` con los roles `editor` y `delegado` (este último con
    `mariachi-t.access.manage`), `vine-t` con `lector`, y cuatro personas:
    la delegada, una exclusiva de mariachi-t, una con roles en las dos apps y una sin roles."""
    with Session(test_engine) as session:
        app_row = Application(
            name="Mariachi T",
            slug="mariachi-t",
            client_secret_hash=hash_secret(SECRET),
            status="active",
            homepage_url="https://portalito.iieg/mariachi/",
        )
        other = Application(name="Vine T", slug="vine-t", client_secret_hash=hash_secret(OTHER_SECRET), status="active")
        session.add_all([app_row, other])
        session.flush()
        editor = _role(session, app_row.id, "editor", "mariachi-t.capas.update")
        delegado = _role(session, app_row.id, "delegado", "mariachi-t.access.manage")
        lector = _role(session, other.id, "lector", "vine-t.asistencias.view")

        delegate = _user(session, "delegada@iieg.gob.mx")
        solo = _user(session, "solo@iieg.gob.mx")
        mixed = _user(session, "mixta@iieg.gob.mx")
        outsider = _user(session, "fuera@iieg.gob.mx")
        session.add_all(
            [
                UserRole(user_id=delegate.id, role_id=delegado.id),
                UserRole(user_id=solo.id, role_id=editor.id),
                UserRole(user_id=mixed.id, role_id=editor.id),
                UserRole(user_id=mixed.id, role_id=lector.id),
                UserRole(user_id=outsider.id, role_id=lector.id),
            ]
        )
        group = Group(name="Capturistas", slug="capturistas")
        session.add(group)
        session.flush()
        grouped = _user(session, "grupo@iieg.gob.mx")
        session.add_all(
            [GroupUser(group_id=group.id, user_id=grouped.id), GroupRole(group_id=group.id, role_id=editor.id)]
        )
        session.commit()

        oidc = OIDCService(session)
        oidc.ensure_active_signing_key()
        kid, pem = oidc.get_active_private_pem()
        return {
            "kid": kid,
            "pem": pem,
            "client_id": app_row.client_id,
            "other_client_id": other.client_id,
            "app_id": app_row.id,
            "editor": editor.id,
            "delegado": delegado.id,
            "lector": lector.id,
            "delegate": delegate.id,
            "solo": solo.id,
            "mixed": mixed.id,
            "outsider": outsider.id,
            "grouped": grouped.id,
        }


def _access(ctx: dict, user_id: str, aud: str = "mariachi-t") -> str:
    return create_access_token_rs256(
        user_id=user_id,
        email="x@iieg.gob.mx",
        name="X",
        kid=ctx["kid"],
        private_key_pem=ctx["pem"],
        application_slug=aud,
    )


def _headers(ctx: dict, user_key: str = "delegate", aud: str = "mariachi-t", secret: str = SECRET, client_id=None):
    return {
        "Authorization": f"Bearer {_access(ctx, ctx[user_key], aud)}",
        "X-Client-Id": client_id or ctx["client_id"],
        "X-Client-Secret": secret,
    }


# --- La guarda ----------------------------------------------------------------


def test_sin_credenciales_del_client_responde_401(client, ctx):
    headers = {"Authorization": f"Bearer {_access(ctx, ctx['delegate'])}"}
    assert client.get("/delegated/roles", headers=headers).status_code == 401


def test_secret_incorrecto_responde_401(client, ctx):
    assert client.get("/delegated/roles", headers=_headers(ctx, secret="otro")).status_code == 401


def test_token_de_otra_aplicacion_responde_403(client, ctx):
    resp = client.get("/delegated/roles", headers=_headers(ctx, aud="vine-t"))
    assert resp.status_code == 403


def test_client_de_otra_app_no_alcanza_la_del_token(client, ctx):
    headers = _headers(ctx, aud="mariachi-t", secret=OTHER_SECRET, client_id=ctx["other_client_id"])
    assert client.get("/delegated/roles", headers=headers).status_code == 403


def test_sin_permiso_delegado_responde_403(client, ctx):
    assert client.get("/delegated/roles", headers=_headers(ctx, user_key="solo")).status_code == 403


def test_permiso_retirado_surte_efecto_sin_esperar_al_token(client, ctx):
    headers = _headers(ctx)
    with Session(test_engine) as session:
        link = session.exec(
            select(UserRole).where(UserRole.user_id == ctx["delegate"], UserRole.role_id == ctx["delegado"])
        ).first()
        session.delete(link)
        session.commit()
    assert client.get("/delegated/roles", headers=headers).status_code == 403


# --- Lectura -------------------------------------------------------------------


def test_roles_marcan_los_de_administracion_delegada(client, ctx):
    resp = client.get("/delegated/roles", headers=_headers(ctx))
    assert resp.status_code == 200
    delegable = {r["slug"]: r["delegable"] for r in resp.json()}
    assert delegable == {"editor": True, "delegado": False}


def test_lista_solo_personas_de_la_app_con_su_origen(client, ctx):
    resp = client.get("/delegated/users", headers=_headers(ctx))
    assert resp.status_code == 200
    by_email = {u["email"]: u for u in resp.json()}
    assert "fuera@iieg.gob.mx" not in by_email
    assert {r["slug"] for r in by_email["mixta@iieg.gob.mx"]["roles"]} == {"editor"}
    assert by_email["grupo@iieg.gob.mx"]["roles"][0]["via"] == "group"


def test_busqueda_por_correo_encuentra_a_quien_aun_no_tiene_roles(client, ctx):
    resp = client.get("/delegated/users", params={"email": "fuera@iieg.gob.mx"}, headers=_headers(ctx))
    assert resp.status_code == 200
    assert resp.json()[0]["roles"] == []


# --- Alta ----------------------------------------------------------------------


def test_alta_invita_con_roles_y_queda_auditada(client, ctx):
    data = {"email": "nueva@iieg.gob.mx", "full_name": "Persona Nueva", "role_ids": [ctx["editor"]]}
    resp = client.post("/delegated/users", json=data, headers=_headers(ctx))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] is True
    assert body["status"] == "pending"
    assert body["credential_link"]["purpose"] == "invite"
    assert body["credential_link"]["application"]["id"] == ctx["app_id"]
    assert [r["slug"] for r in body["roles"]] == ["editor"]
    with Session(test_engine) as session:
        log = session.exec(select(AuditLog).where(AuditLog.action == "user_create")).first()
        assert log.actor_user_id == ctx["delegate"]
        assert log.event_metadata["via"] == "delegated"
        assert log.event_metadata["client_id"] == ctx["client_id"]


def test_alta_de_correo_existente_no_toca_la_cuenta(client, ctx):
    data = {"email": "fuera@iieg.gob.mx", "full_name": "Otro Nombre", "role_ids": [ctx["editor"]]}
    resp = client.post("/delegated/users", json=data, headers=_headers(ctx))
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is False
    assert body["credential_link"] is None
    assert body["roles"] == []


def test_alta_con_rol_delegado_se_rechaza(client, ctx):
    data = {"email": "otra@iieg.gob.mx", "full_name": "Persona Otra", "role_ids": [ctx["delegado"]]}
    assert client.post("/delegated/users", json=data, headers=_headers(ctx)).status_code == 403


# --- Roles: reglas contra escalamiento -------------------------------------------


def test_regla_1_no_cambia_sus_propios_roles(client, ctx):
    resp = client.put(f"/delegated/users/{ctx['delegate']}/roles", json={"role_ids": []}, headers=_headers(ctx))
    assert resp.status_code == 403


def test_regla_2_no_reparte_administracion_delegada(client, ctx):
    resp = client.put(
        f"/delegated/users/{ctx['solo']}/roles", json={"role_ids": [ctx["delegado"]]}, headers=_headers(ctx)
    )
    assert resp.status_code == 403


def test_regla_2_no_retira_administracion_delegada(client, ctx):
    with Session(test_engine) as session:
        session.add(UserRole(user_id=ctx["solo"], role_id=ctx["delegado"]))
        session.commit()
    resp = client.put(f"/delegated/users/{ctx['solo']}/roles", json={"role_ids": []}, headers=_headers(ctx))
    assert resp.status_code == 200
    assert {r["slug"] for r in resp.json()["roles"]} == {"delegado"}


def test_regla_4_no_asigna_roles_de_otra_aplicacion(client, ctx):
    resp = client.put(
        f"/delegated/users/{ctx['solo']}/roles", json={"role_ids": [ctx["lector"]]}, headers=_headers(ctx)
    )
    assert resp.status_code == 400


def test_quitar_acceso_deja_intactos_los_roles_de_otras_apps(client, ctx):
    resp = client.put(f"/delegated/users/{ctx['mixed']}/roles", json={"role_ids": []}, headers=_headers(ctx))
    assert resp.status_code == 200
    assert resp.json()["roles"] == []
    with Session(test_engine) as session:
        roles = session.exec(select(UserRole).where(UserRole.user_id == ctx["mixed"])).all()
        assert [r.role_id for r in roles] == [ctx["lector"]]
        log = session.exec(select(AuditLog).where(AuditLog.action == "user_roles_set")).first()
        assert log.event_metadata["removed"] == [ctx["editor"]]


def test_dar_acceso_a_quien_ya_existia(client, ctx):
    resp = client.put(
        f"/delegated/users/{ctx['outsider']}/roles", json={"role_ids": [ctx["editor"]]}, headers=_headers(ctx)
    )
    assert resp.status_code == 200
    assert [r["slug"] for r in resp.json()["roles"]] == ["editor"]


# --- Enlaces de credencial ------------------------------------------------------


def test_regla_3_reset_de_cuenta_exclusiva(client, ctx):
    resp = client.post(f"/delegated/users/{ctx['solo']}/credential-link", headers=_headers(ctx))
    assert resp.status_code == 201, resp.text
    assert resp.json()["purpose"] == "reset"


def test_regla_3_no_resetea_cuentas_con_acceso_a_otras_apps(client, ctx):
    resp = client.post(f"/delegated/users/{ctx['mixed']}/credential-link", headers=_headers(ctx))
    assert resp.status_code == 403


def test_regla_3_cuenta_la_herencia_por_grupo(client, ctx):
    with Session(test_engine) as session:
        group = Group(name="Vine", slug="vine-grupo")
        session.add(group)
        session.flush()
        session.add_all(
            [GroupUser(group_id=group.id, user_id=ctx["solo"]), GroupRole(group_id=group.id, role_id=ctx["lector"])]
        )
        session.commit()
    resp = client.post(f"/delegated/users/{ctx['solo']}/credential-link", headers=_headers(ctx))
    assert resp.status_code == 403


def test_invitacion_pendiente_aunque_tenga_otras_apps(client, ctx):
    with Session(test_engine) as session:
        user = session.get(User, ctx["mixed"])
        user.status = "pending"
        session.add(user)
        session.commit()
    resp = client.post(f"/delegated/users/{ctx['mixed']}/credential-link", headers=_headers(ctx))
    assert resp.status_code == 201
    assert resp.json()["purpose"] == "invite"


def test_enlace_para_alguien_fuera_de_la_app_responde_404(client, ctx):
    resp = client.post(f"/delegated/users/{ctx['outsider']}/credential-link", headers=_headers(ctx))
    assert resp.status_code == 404
