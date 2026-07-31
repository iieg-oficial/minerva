from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.dependencies.auth import get_current_devkit_user
from app.core.dependencies.db import get_db
from app.modules.devkit.schemas import (
    DevLoginRequest,
    MePermissionsResponse,
    MeResponse,
    TokenResponse,
)
from app.modules.devkit.service import DevKitService

# Solo self-service para sistemas consumidores. La administración (apps, usuarios,
# roles, permisos, asignaciones, manifiestos) vive EXCLUSIVAMENTE en los routers
# canónicos protegidos con `require_minerva_admin` (applications/users/roles/
# permissions/groups). Aquí NO se replica ese CRUD: estar autenticado no basta para
# administrar (antes cualquier token válido de dev-login podía autoasignarse roles).
router = APIRouter(prefix="/api/v1", tags=["Minerva Dev Kit"])


def get_devkit_service(session: Session = Depends(get_db)) -> DevKitService:
    return DevKitService(session)


# --- Auth dev ---------------------------------------------------------------
@router.post("/auth/dev-login", response_model=TokenResponse)
def dev_login(data: DevLoginRequest, service: DevKitService = Depends(get_devkit_service)):
    return service.dev_login(data)


# --- Me ---------------------------------------------------------------------
@router.get("/me", response_model=MeResponse)
def me(
    service: DevKitService = Depends(get_devkit_service),
    current_user: dict = Depends(get_current_devkit_user),
):
    return service.get_me(current_user["sub"])


@router.get("/me/permissions", response_model=MePermissionsResponse)
def me_permissions(
    application: str = Query(..., description="Código (slug) de la aplicación"),
    service: DevKitService = Depends(get_devkit_service),
    current_user: dict = Depends(get_current_devkit_user),
):
    """Permisos del usuario autenticado, en *shape lean* (roles por nombre, permisos por slug).

    Endpoint **canónico para sistemas consumidores**: lo consume el `minerva_sdk` y se publica en el
    discovery OIDC. Para la vista interna del panel admin (objetos completos) ver
    `GET /authorization/me/permissions`.
    """
    return service.get_me_permissions(current_user, application)
