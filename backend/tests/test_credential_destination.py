"""Destino de los enlaces de credencial: la persona termina en una aplicación que usa y no en
el panel de Minerva, al que casi nadie tiene acceso."""

from sqlmodel import Session, select

from app.modules.credentials.models import CredentialToken
from tests.conftest import test_engine
from tests.test_credentials import _admin, _create_active, _set_password, _token_from

HOMEPAGE = "https://mariachi.example.com/admin/"


def _create_app(client, admin_token, slug, homepage_url=HOMEPAGE, display_name=None):
    body = {"name": slug.capitalize(), "slug": slug, "homepage_url": homepage_url, "display_name": display_name}
    resp = client.post("/applications", json=body, headers=_admin(admin_token))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _grant(client, admin_token, app, user_id):
    role = client.post(
        f"/roles?application_id={app['id']}",
        json={"name": "Miembro", "slug": f"{app['slug']}.miembro"},
        headers=_admin(admin_token),
    ).json()
    resp = client.post(f"/groups/users/{user_id}/roles/{role['id']}", headers=_admin(admin_token))
    assert resp.status_code == 201, resp.text


def _issue(client, admin_token, user_id, application_id=None):
    body = {"application_id": application_id} if application_id else None
    return client.post(f"/users/{user_id}/credential-link", json=body, headers=_admin(admin_token))


def test_destinations_are_the_apps_the_person_uses(client, admin_token):
    user = _create_active(client, admin_token)
    mariachi = _create_app(client, admin_token, "mariachi", display_name="Mariachi")
    _grant(client, admin_token, mariachi, user["id"])
    _grant(client, admin_token, _create_app(client, admin_token, "sin-inicio", homepage_url=None), user["id"])
    _create_app(client, admin_token, "ajena")

    resp = client.get(f"/users/{user['id']}/credential-destinations", headers=_admin(admin_token))

    assert resp.status_code == 200
    assert resp.json() == [{"id": mariachi["id"], "name": "Mariachi", "homepage_url": HOMEPAGE}]


def test_link_with_destination_is_shown_on_inspect(client, admin_token):
    user = _create_active(client, admin_token)
    app = _create_app(client, admin_token, "mariachi")
    _grant(client, admin_token, app, user["id"])

    resp = _issue(client, admin_token, user["id"], app["id"])

    assert resp.status_code == 201, resp.text
    assert resp.json()["application"]["homepage_url"] == HOMEPAGE
    assert "mariachi" not in resp.json()["url"]
    inspected = client.post("/auth/credential/inspect", json={"token": _token_from(resp.json()["url"])})
    assert inspected.json()["application"] == {"id": app["id"], "name": "Mariachi", "homepage_url": HOMEPAGE}
    assert _set_password(client, _token_from(resp.json()["url"])).status_code == 200


def test_link_without_destination_keeps_working(client, admin_token):
    user = _create_active(client, admin_token)

    resp = _issue(client, admin_token, user["id"])

    assert resp.status_code == 201
    assert resp.json()["application"] is None
    inspected = client.post("/auth/credential/inspect", json={"token": _token_from(resp.json()["url"])})
    assert inspected.json()["application"] is None


def test_destination_must_be_an_app_the_person_uses(client, admin_token):
    user = _create_active(client, admin_token)
    app = _create_app(client, admin_token, "ajena")

    resp = _issue(client, admin_token, user["id"], app["id"])

    assert resp.status_code == 400
    with Session(test_engine) as session:
        assert session.exec(select(CredentialToken).where(CredentialToken.application_id == app["id"])).first() is None


def test_deleted_app_leaves_the_link_without_destination(client, admin_token):
    user = _create_active(client, admin_token)
    app = _create_app(client, admin_token, "mariachi")
    _grant(client, admin_token, app, user["id"])
    token = _token_from(_issue(client, admin_token, user["id"], app["id"]).json()["url"])

    assert client.delete(f"/applications/{app['id']}", headers=_admin(admin_token)).status_code == 204

    inspected = client.post("/auth/credential/inspect", json={"token": token})
    assert inspected.status_code == 200
    assert inspected.json()["application"] is None


def test_me_lists_the_apps_of_the_person(client, admin_token):
    me = client.get("/auth/me", headers=_admin(admin_token)).json()
    app = _create_app(client, admin_token, "mariachi")
    _grant(client, admin_token, app, me["user"]["id"])

    applications = client.get("/auth/me", headers=_admin(admin_token)).json()["applications"]

    assert [a["id"] for a in applications] == [app["id"]]


def test_destinations_require_admin(client, admin_token, non_admin_token):
    user = _create_active(client, admin_token)
    resp = client.get(
        f"/users/{user['id']}/credential-destinations", headers={"Authorization": f"Bearer {non_admin_token}"}
    )
    assert resp.status_code == 403
