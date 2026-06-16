from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlmodel import Session

from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.applications.schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationWithSecrets,
)
from app.modules.applications.service import ApplicationService
from app.modules.devkit.schemas import (
    AccessAssignmentCreate,
    AccessAssignmentRead,
    DevLoginRequest,
    ManifestImportResult,
    MePermissionsResponse,
    MeResponse,
    TokenResponse,
)
from app.modules.devkit.service import DevKitService
from app.modules.permissions.schemas import PermissionCreate, PermissionRead
from app.modules.permissions.service import PermissionService
from app.modules.roles.schemas import RoleCreate, RoleRead, RoleUpdate
from app.modules.roles.service import RoleService
from app.modules.users.schemas import UserCreate, UserRead, UserUpdate
from app.modules.users.service import UserService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/api/v1", tags=["Minerva Dev Kit"])


def get_devkit_service(session: Session = Depends(get_db)) -> DevKitService:
    return DevKitService(session)


def _resolve_application_id(session: Session, application_id: str | None, application_code: str | None) -> str:
    """Permite identificar la aplicación por id o por `code` (slug)."""
    if application_id:
        return application_id
    if application_code:
        app = ApplicationService(session).get_application_by_slug(application_code)
        if not app:
            raise NotFoundError(detail=f"Aplicación `{application_code}` no encontrada")
        return app.id
    raise BadRequestError(detail="Debe indicar application_id o application_code")


# --- Auth dev ---------------------------------------------------------------
@router.post("/auth/dev-login", response_model=TokenResponse)
def dev_login(data: DevLoginRequest, service: DevKitService = Depends(get_devkit_service)):
    return service.dev_login(data)


# --- Me ---------------------------------------------------------------------
@router.get("/me", response_model=MeResponse)
def me(
    service: DevKitService = Depends(get_devkit_service),
    current_user: dict = Depends(get_current_user),
):
    return service.get_me(current_user["sub"])


@router.get("/me/permissions", response_model=MePermissionsResponse)
def me_permissions(
    application: str = Query(..., description="Código (slug) de la aplicación"),
    service: DevKitService = Depends(get_devkit_service),
    current_user: dict = Depends(get_current_user),
):
    return service.get_me_permissions(current_user["sub"], application)


# --- Applications -----------------------------------------------------------
@router.get("/applications", response_model=PaginatedResponse[ApplicationRead])
def list_applications(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    apps, total = ApplicationService(session).list_applications(offset, limit)
    return PaginatedResponse.create(apps, total)


@router.post("/applications", response_model=ApplicationWithSecrets, status_code=201)
def create_application(
    data: ApplicationCreate,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return ApplicationService(session).create_application(data)


@router.get("/applications/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: str,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return ApplicationService(session).get_application(application_id)


@router.patch("/applications/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: str,
    data: ApplicationUpdate,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return ApplicationService(session).update_application(application_id, data)


# --- Users ------------------------------------------------------------------
@router.get("/users", response_model=PaginatedResponse[UserRead])
def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    users, total = UserService(session).list_users(offset, limit)
    return PaginatedResponse.create(users, total)


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(
    data: UserCreate,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return UserService(session).create_user(data)


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: str,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return UserService(session).get_user(user_id)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    data: UserUpdate,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return UserService(session).update_user(user_id, data)


# --- Roles ------------------------------------------------------------------
@router.get("/roles", response_model=PaginatedResponse[RoleRead])
def list_roles(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    application_id: str | None = Query(None),
    application_code: str | None = Query(None),
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    service = RoleService(session)
    if application_id or application_code:
        app_id = _resolve_application_id(session, application_id, application_code)
        roles = service.list_roles_by_application(app_id)
        return PaginatedResponse.create(roles, len(roles))
    roles, total = service.list_roles(offset, limit)
    return PaginatedResponse.create(roles, total)


@router.post("/roles", response_model=RoleRead, status_code=201)
def create_role(
    data: RoleCreate,
    application_id: str | None = Query(None),
    application_code: str | None = Query(None),
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    app_id = _resolve_application_id(session, application_id, application_code)
    return RoleService(session).create_role(app_id, data)


@router.get("/roles/{role_id}", response_model=RoleRead)
def get_role(
    role_id: str,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return RoleService(session).get_role(role_id)


@router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(
    role_id: str,
    data: RoleUpdate,
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    return RoleService(session).update_role(role_id, data)


# --- Permissions ------------------------------------------------------------
@router.get("/permissions", response_model=PaginatedResponse[PermissionRead])
def list_permissions(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    application_id: str | None = Query(None),
    application_code: str | None = Query(None),
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    service = PermissionService(session)
    if application_id or application_code:
        app_id = _resolve_application_id(session, application_id, application_code)
        perms = service.list_permissions_by_application(app_id)
        return PaginatedResponse.create(perms, len(perms))
    perms, total = service.list_permissions(offset, limit)
    return PaginatedResponse.create(perms, total)


@router.post("/permissions", response_model=PermissionRead, status_code=201)
def create_permission(
    data: PermissionCreate,
    application_id: str | None = Query(None),
    application_code: str | None = Query(None),
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    app_id = _resolve_application_id(session, application_id, application_code)
    return PermissionService(session).create_permission(app_id, data)


# --- Access assignments -----------------------------------------------------
@router.get("/access-assignments", response_model=list[AccessAssignmentRead])
def list_access_assignments(
    user_id: str | None = Query(None),
    application: str | None = Query(None, description="Filtrar por código de aplicación"),
    service: DevKitService = Depends(get_devkit_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.list_access_assignments(user_id, application)


@router.post("/access-assignments", response_model=AccessAssignmentRead, status_code=201)
def create_access_assignment(
    data: AccessAssignmentCreate,
    service: DevKitService = Depends(get_devkit_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.create_access_assignment(data.user_id, data.role_id)


@router.delete("/access-assignments/{assignment_id}", status_code=204)
def delete_access_assignment(
    assignment_id: str,
    service: DevKitService = Depends(get_devkit_service),
    _current_user: dict = Depends(get_current_user),
):
    service.delete_access_assignment(assignment_id)


# --- Manifests --------------------------------------------------------------
@router.post("/manifests/import", response_model=ManifestImportResult)
async def import_manifest(
    request: Request,
    file: UploadFile | None = File(default=None),
    service: DevKitService = Depends(get_devkit_service),
    _current_user: dict = Depends(get_current_user),
):
    """Importa un `manifest.minerva.yml`.

    Acepta el manifiesto como archivo (`multipart/form-data`, campo `file`) o
    como cuerpo de texto plano (`text/yaml` / `application/x-yaml`).
    """
    if file is not None:
        content = (await file.read()).decode("utf-8")
        source = file.filename or "manifest.minerva.yml"
    else:
        body = await request.body()
        if not body:
            raise BadRequestError(detail="No se recibió ningún manifiesto")
        content = body.decode("utf-8")
        source = "manifest.minerva.yml"
    return service.import_manifest(content, source)
