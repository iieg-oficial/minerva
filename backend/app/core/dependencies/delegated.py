from dataclasses import dataclass

from fastapi import Depends, Header
from sqlmodel import Session

from app.core.constants import MINERVA_APP_SLUG, delegate_permission
from app.core.dependencies.auth import get_current_access_user
from app.core.dependencies.db import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import verify_secret
from app.modules.applications.models import Application
from app.modules.applications.service import ApplicationService
from app.modules.authorization.service import AuthorizationService
from app.modules.users.models import USER_KIND_HUMAN
from app.modules.users.repository import UserRepository


@dataclass(frozen=True)
class DelegatedContext:
    """Quién pide (la persona del access token) y para qué aplicación (la del client)."""

    actor_id: str
    application: Application


def _authenticate_client(service: ApplicationService, client_id: str | None, client_secret: str | None) -> Application:
    """El client tiene que ser confidencial: el secret es la prueba de que la llamada viene
    del backend de la aplicación y no de quien tenga en la mano un access filtrado."""
    if not client_id or not client_secret:
        raise UnauthorizedError(detail="Faltan las credenciales de la aplicación")
    app = service.get_application_by_client_id(client_id)
    if app is None or app.status != "active" or app.client_secret_hash is None:
        raise UnauthorizedError(detail="Credenciales de la aplicación inválidas")
    if not verify_secret(client_secret, app.client_secret_hash):
        raise UnauthorizedError(detail="Credenciales de la aplicación inválidas")
    return app


async def require_app_delegate(
    access: dict = Depends(get_current_access_user),
    x_client_id: str | None = Header(default=None),
    x_client_secret: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> DelegatedContext:
    """Administración delegada de una aplicación, en nombre de la persona que la pide.

    Exige dos pruebas: el access token de la persona (`Authorization: Bearer`) y las
    credenciales del client confidencial (`X-Client-Id`, `X-Client-Secret`). La aplicación
    sobre la que se opera es la del client y tiene que coincidir con el `aud` del token:
    nunca sale de la URL, así que no se puede pedir nada sobre otra aplicación.

    El permiso `{app}.access.manage` se consulta en la base, no en los claims del token:
    retirarlo surte efecto en la siguiente llamada y no a los 15 minutos."""
    app = _authenticate_client(ApplicationService(session), x_client_id, x_client_secret)
    if app.slug == MINERVA_APP_SLUG:
        raise ForbiddenError(detail="Minerva no se administra por delegación")
    if access.get("aud") != app.slug:
        raise ForbiddenError(detail="El token no corresponde a la aplicación que hace la llamada")

    actor_id = access["sub"]
    actor = UserRepository(session).get_by_id(actor_id)
    if actor is None or actor.kind != USER_KIND_HUMAN or actor.status != "active":
        raise ForbiddenError(detail="La cuenta no puede administrar la aplicación")
    check = AuthorizationService(session).check_permission(actor_id, app.slug, delegate_permission(app.slug))
    if not check["allowed"]:
        raise ForbiddenError(detail=f"Requiere el permiso {delegate_permission(app.slug)}")
    return DelegatedContext(actor_id=actor_id, application=app)
