"""Grant `client_credentials`: cuentas de servicio de aplicaciones confidenciales.

Cubre el token máquina a máquina (`typ=service`), los errores OAuth del grant, los
candados que impiden que una cuenta de servicio actúe como persona o administre
Minerva, el alta por el panel y lo que queda de la cuenta al borrar su aplicación.
"""

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.core.exceptions import BadRequestError, ForbiddenError
from app.core.security import decode_token_rs256, hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.audit.models import AuditLog
from app.modules.auth.service import AuthService
from app.modules.authorization.service import AuthorizationService
from app.modules.credentials.service import CredentialService
from app.modules.devkit.schemas import DevLoginRequest
from app.modules.devkit.service import DevKitService
from app.modules.groups.models import Group, GroupUser, UserRole
from app.modules.groups.service import GroupService
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate
from app.modules.users.service import UserService
from tests.conftest import _grant_minerva_admin, test_engine

CLIENT_SECRET = "secreto-del-cliente-cc"
REDIRECT_URI = "https://destino.example.com/callback"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ctx(client, admin_token):
    """Cliente confidencial `cliente-cc` con cuenta de servicio y el rol `lector` en la
    aplicación `destino-cc`, que concede `destino-cc.reportes.view`."""
    with Session(test_engine) as session:
        caller = Application(
            name="Cliente CC", slug="cliente-cc", client_secret_hash=hash_secret(CLIENT_SECRET), status="active"
        )
        target = Application(
            name="Destino CC", slug="destino-cc", client_secret_hash=hash_secret("destino"), status="active"
        )
        public = Application(name="Publica CC", slug="publica-cc", status="active")
        session.add_all([caller, target, public])
        session.flush()
        session.add(RedirectURI(application_id=target.id, uri=REDIRECT_URI, environment="production"))
        role = Role(application_id=target.id, name="Lector", slug="lector")
        perm = Permission(application_id=target.id, name="Ver reportes", slug="destino-cc.reportes.view")
        session.add_all([role, perm])
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=perm.id))
        session.commit()
        ids = {
            "caller_id": caller.id,
            "client_id": caller.client_id,
            "target_id": target.id,
            "target_client_id": target.client_id,
            "public_id": public.id,
            "public_client_id": public.client_id,
            "role_id": role.id,
        }

    resp = client.post(f"/applications/{ids['caller_id']}/service-principal", headers=_auth(admin_token))
    assert resp.status_code == 201, resp.text
    ids["svc_id"] = resp.json()["id"]
    resp = client.post(f"/groups/users/{ids['svc_id']}/roles/{ids['role_id']}", headers=_auth(admin_token))
    assert resp.status_code == 201, resp.text
    ids["admin_token"] = admin_token
    return ids


def _token(client, ctx: dict, **overrides):
    data = {
        "grant_type": "client_credentials",
        "client_id": ctx["client_id"],
        "client_secret": CLIENT_SECRET,
        "audience": "destino-cc",
    }
    data.update(overrides)
    return client.post("/auth/token", data={k: v for k, v in data.items() if v is not None})


def _assert_oauth_error(resp, error: str) -> dict:
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == error
    assert body["error_description"]
    return body


def _set(model, row_id: str, **fields) -> None:
    with Session(test_engine) as session:
        row = session.get(model, row_id)
        for key, value in fields.items():
            setattr(row, key, value)
        session.add(row)
        session.commit()


# --- Camino feliz -------------------------------------------------------------


def test_emite_token_de_servicio(client, ctx):
    resp = _token(client, ctx, scope="lo-que-sea")
    assert resp.status_code == 200, resp.text
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["pragma"] == "no-cache"
    body = resp.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES * 60

    jwks = client.get("/.well-known/jwks.json").json()
    claims = decode_token_rs256(body["access_token"], jwks, audience="destino-cc", issuer=settings.effective_jwt_issuer)
    assert claims["sub"] == ctx["svc_id"]
    assert claims["typ"] == "service"
    assert claims["client_id"] == ctx["client_id"]
    assert claims["azp"] == ctx["client_id"]
    assert claims["roles"] == ["lector"]
    assert claims["permissions"] == ["destino-cc.reportes.view"]
    assert claims["scope"] == ""
    assert claims["email"] == "cliente-cc@service.minerva.invalid"
    assert claims["name"] == "Cuenta de servicio de Cliente CC"
    assert claims["preferred_username"] == "svc-cliente-cc"
    assert claims["jti"]
    assert claims["exp"] - claims["iat"] == settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES * 60

    with Session(test_engine) as session:
        log = session.exec(select(AuditLog).where(AuditLog.action == "token_client_credentials_success")).one()
    assert log.actor_user_id == ctx["svc_id"]
    assert log.application_id == ctx["target_id"]
    assert log.event_metadata["client_id"] == ctx["client_id"]
    assert log.event_metadata["audience"] == "destino-cc"
    assert log.event_metadata["jti"] == claims["jti"]


def test_token_de_servicio_no_vale_en_userinfo_ni_en_el_dev_kit(client, ctx):
    token = _token(client, ctx).json()["access_token"]
    assert client.get("/userinfo", headers=_auth(token)).status_code == 401
    assert client.get("/api/v1/me/permissions?application=destino-cc", headers=_auth(token)).status_code == 401


def test_filtra_roles_reservados_de_minerva(client, ctx):
    with Session(test_engine) as session:
        reserved = Role(application_id=ctx["target_id"], name="Colado", slug="minerva.colado")
        session.add(reserved)
        session.flush()
        session.add(UserRole(user_id=ctx["svc_id"], role_id=reserved.id))
        session.commit()
    token = _token(client, ctx).json()["access_token"]
    jwks = client.get("/.well-known/jwks.json").json()
    assert decode_token_rs256(token, jwks, audience="destino-cc")["roles"] == ["lector"]


# --- Errores del grant ----------------------------------------------------------


@pytest.mark.parametrize("missing", ["client_id", "audience"])
def test_parametros_faltantes(client, ctx, missing):
    _assert_oauth_error(_token(client, ctx, **{missing: None}), "invalid_request")


def test_secret_incorrecto(client, ctx):
    resp = _token(client, ctx, client_secret="otro-secreto")
    _assert_oauth_error(resp, "invalid_client")
    assert "otro-secreto" not in resp.text


def test_secret_faltante(client, ctx):
    _assert_oauth_error(_token(client, ctx, client_secret=None), "invalid_client")


def test_cliente_desconocido(client, ctx):
    _assert_oauth_error(_token(client, ctx, client_id="no-existe"), "invalid_client")


def test_cliente_inactivo(client, ctx):
    _set(Application, ctx["caller_id"], status="inactive")
    _assert_oauth_error(_token(client, ctx), "invalid_client")


def test_cliente_publico(client, ctx):
    body = _assert_oauth_error(
        _token(client, ctx, client_id=ctx["public_client_id"], client_secret=None), "unauthorized_client"
    )
    assert body["error_description"] == "El grant client_credentials requiere un cliente confidencial"


def test_cliente_sin_cuenta_de_servicio(client, ctx):
    with Session(test_engine) as session:
        other = Application(name="Otro", slug="otro-cc", client_secret_hash=hash_secret(CLIENT_SECRET))
        session.add(other)
        session.commit()
        other_client_id = other.client_id
    body = _assert_oauth_error(_token(client, ctx, client_id=other_client_id), "unauthorized_client")
    assert body["error_description"] == "La aplicación no tiene una cuenta de servicio activa"


def test_cuenta_de_servicio_inactiva(client, ctx):
    resp = client.patch(
        f"/users/{ctx['svc_id']}/status", json={"status": "inactive"}, headers=_auth(ctx["admin_token"])
    )
    assert resp.status_code == 200, resp.text
    _assert_oauth_error(_token(client, ctx), "unauthorized_client")


def test_audiencia_desconocida(client, ctx):
    _assert_oauth_error(_token(client, ctx, audience="no-existe"), "invalid_target")


def test_audiencia_inactiva(client, ctx):
    _set(Application, ctx["target_id"], status="inactive")
    _assert_oauth_error(_token(client, ctx), "invalid_target")


def test_audiencia_minerva(client, ctx):
    body = _assert_oauth_error(_token(client, ctx, audience="minerva"), "invalid_target")
    assert body["error_description"] == "Las cuentas de servicio no pueden pedir tokens para Minerva"


def test_audiencia_sin_roles(client, ctx):
    body = _assert_oauth_error(_token(client, ctx, audience="publica-cc"), "invalid_target")
    assert body["error_description"] == "La cuenta de servicio no tiene roles en la aplicación destino"


def test_rate_limit(client, ctx, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTHORIZE_MAX", 2)
    assert _token(client, ctx).status_code == 200
    assert _token(client, ctx).status_code == 200
    assert _token(client, ctx).status_code == 429
    with Session(test_engine) as session:
        log = session.exec(select(AuditLog).where(AuditLog.action == "rate_limit_exceeded")).one()
    assert log.event_metadata["endpoint"] == "token_client_credentials"


# --- Candados de la cuenta de servicio --------------------------------------------


def test_no_inicia_sesion_con_contrasena(ctx):
    with Session(test_engine) as session:
        svc = session.get(User, ctx["svc_id"])
        with pytest.raises(BadRequestError, match="Credenciales inválidas"):
            UserService(session).authenticate(svc.email, "cualquiera")


def test_no_recibe_enlaces_de_credencial(client, ctx):
    with Session(test_engine) as session:
        service = CredentialService(session)
        with pytest.raises(BadRequestError, match="Las cuentas de servicio no tienen contraseña"):
            service.issue_token(ctx["svc_id"], "reset")
        with pytest.raises(BadRequestError, match="Las cuentas de servicio no tienen contraseña"):
            service.issue_link(ctx["svc_id"])
    resp = client.post(f"/users/{ctx['svc_id']}/credential-link", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 400


def test_no_pasa_por_authorize(ctx):
    with Session(test_engine) as session:
        with pytest.raises(ForbiddenError, match="Usuario inactivo"):
            AuthService(session).authorize(ctx["target_client_id"], REDIRECT_URI, ctx["svc_id"], "s", "openid")


def test_no_es_admin_de_minerva_aunque_tenga_el_rol(client, ctx):
    _grant_minerva_admin("cliente-cc@service.minerva.invalid")
    with Session(test_engine) as session:
        assert AuthorizationService(session).is_minerva_admin(ctx["svc_id"]) is False


def test_no_recibe_roles_de_minerva(client, ctx):
    _grant_minerva_admin("testadmin@iieg.gob.mx")
    with Session(test_engine) as session:
        minerva = session.exec(select(Application).where(Application.slug == "minerva")).one()
        admin_role = session.exec(select(Role).where(Role.application_id == minerva.id)).one()
        with pytest.raises(BadRequestError, match="Una cuenta de servicio no puede recibir roles de Minerva"):
            GroupService(session).assign_role_to_user(ctx["svc_id"], admin_role.id)
        role_id = admin_role.id
    resp = client.post(f"/groups/users/{ctx['svc_id']}/roles/{role_id}", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 400


def test_no_entra_a_grupos(ctx):
    with Session(test_engine) as session:
        group = Group(name="Grupo CC", slug="grupo-cc")
        session.add(group)
        session.commit()
        with pytest.raises(BadRequestError):
            GroupService(session).add_user_to_group(group.id, ctx["svc_id"])


def test_no_cambia_de_correo_pero_si_de_estado(ctx):
    with Session(test_engine) as session:
        service = UserService(session)
        with pytest.raises(BadRequestError, match="correo de una cuenta de servicio"):
            service.update_user(ctx["svc_id"], UserUpdate(email="persona@iieg.gob.mx"))
    with Session(test_engine) as session:
        updated = UserService(session).update_user(ctx["svc_id"], UserUpdate(status="suspended"))
    assert updated.status == "suspended"
    assert updated.kind == "service"


def test_no_hace_dev_login(client, ctx, monkeypatch):
    """Por HTTP ya lo frena `EmailStr` (el TLD `.invalid` es de uso especial); el candado
    del service es la segunda barrera si ese esquema cambia."""
    monkeypatch.setattr(settings, "MINERVA_ENABLE_DEV_LOGIN", True)
    resp = client.post("/api/v1/auth/dev-login", json={"email": "cliente-cc@service.minerva.invalid"})
    assert resp.status_code == 422
    request = DevLoginRequest.model_construct(email="cliente-cc@service.minerva.invalid", full_name=None)
    with Session(test_engine) as session:
        with pytest.raises(ForbiddenError, match="Usuario inactivo"):
            DevKitService(session).dev_login(request)


# --- Panel de administración ----------------------------------------------------


def test_lectura_de_la_cuenta_de_servicio(client, ctx):
    resp = client.get(f"/applications/{ctx['caller_id']}/service-principal", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ctx["svc_id"]
    assert body["kind"] == "service"
    assert body["service_application_id"] == ctx["caller_id"]
    assert body["status"] == "active"
    with Session(test_engine) as session:
        assert session.get(User, ctx["svc_id"]).hashed_password is None
        log = session.exec(select(AuditLog).where(AuditLog.action == "application_service_principal_enable")).one()
    assert log.target_id == ctx["svc_id"]
    assert log.application_id == ctx["caller_id"]


def test_lectura_sin_cuenta_de_servicio_es_404(client, ctx):
    resp = client.get(f"/applications/{ctx['target_id']}/service-principal", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 404


def test_alta_duplicada_es_409(client, ctx):
    resp = client.post(f"/applications/{ctx['caller_id']}/service-principal", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 409


def test_el_listado_distingue_clientes_publicos(client, ctx):
    resp = client.get("/applications", headers=_auth(ctx["admin_token"]))
    by_slug = {a["slug"]: a for a in resp.json()["items"]}
    assert by_slug["publica-cc"]["is_public"] is True
    assert by_slug["cliente-cc"]["is_public"] is False


def test_alta_en_cliente_publico_es_400(client, ctx):
    resp = client.post(f"/applications/{ctx['public_id']}/service-principal", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Solo los clientes confidenciales pueden tener cuenta de servicio"


def test_alta_en_aplicacion_inexistente_es_404(client, admin_token):
    resp = client.post("/applications/no-existe/service-principal", headers=_auth(admin_token))
    assert resp.status_code == 404


def test_alta_exige_admin(client, ctx, non_admin_token):
    url = f"/applications/{ctx['target_id']}/service-principal"
    assert client.post(url, headers=_auth(non_admin_token)).status_code == 403
    assert client.get(url, headers=_auth(non_admin_token)).status_code == 403
    assert client.post(url).status_code == 401


def test_borrar_la_aplicacion_conserva_la_cuenta_inactiva(client, ctx):
    with Session(test_engine) as session:
        group = Group(name="Grupo previo", slug="grupo-previo")
        session.add(group)
        session.flush()
        session.add(GroupUser(group_id=group.id, user_id=ctx["svc_id"]))
        session.commit()
    assert _token(client, ctx).status_code == 200

    resp = client.delete(f"/applications/{ctx['caller_id']}", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 204

    with Session(test_engine) as session:
        svc = session.get(User, ctx["svc_id"])
        assert svc is not None
        assert svc.status == "inactive"
        assert svc.service_application_id is None
        assert svc.email != "cliente-cc@service.minerva.invalid"
        assert session.exec(select(UserRole).where(UserRole.user_id == svc.id)).all() == []
        assert session.exec(select(GroupUser).where(GroupUser.user_id == svc.id)).all() == []
        log = session.exec(select(AuditLog).where(AuditLog.action == "token_client_credentials_success")).one()
        assert log.actor_user_id == svc.id

    # Una aplicación nueva con el mismo slug puede tener su propia cuenta de servicio.
    with Session(test_engine) as session:
        again = Application(name="Cliente CC", slug="cliente-cc", client_secret_hash=hash_secret(CLIENT_SECRET))
        session.add(again)
        session.commit()
        again_id = again.id
    resp = client.post(f"/applications/{again_id}/service-principal", headers=_auth(ctx["admin_token"]))
    assert resp.status_code == 201
    assert resp.json()["email"] == "cliente-cc@service.minerva.invalid"
