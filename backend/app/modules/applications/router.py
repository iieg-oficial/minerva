from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.core.exceptions import BadRequestError
from app.modules.applications.schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationWithSecrets,
    RedirectURICreate,
    RedirectURIRead,
)
from app.modules.applications.service import ApplicationService
from app.modules.devkit.manifest import ManifestLoader
from app.modules.devkit.schemas import ManifestImportResult
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/applications", tags=["Applications"], dependencies=[Depends(require_minerva_admin)])


def get_application_service(session: Session = Depends(get_db)) -> ApplicationService:
    return ApplicationService(session)


@router.get("", response_model=PaginatedResponse[ApplicationRead])
def list_applications(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_user),
):
    apps, total = service.list_applications(offset, limit)
    return PaginatedResponse.create(apps, total)


@router.post("", response_model=ApplicationWithSecrets, status_code=201)
def create_application(
    data: ApplicationCreate,
    request: Request,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.create_application(data)


@router.post("/import-manifest", response_model=ManifestImportResult)
async def import_manifest(
    file: UploadFile = File(..., description="Archivo manifest.minerva.yml"),
    session: Session = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    """Importa (o recarga) un manifiesto de permisos/roles de un sistema.

    Hace upsert de la aplicación, sus permisos y roles a partir del YAML, por lo
    que sirve tanto para dar de alta un sistema como para volver a cargar sus
    permisos cuando el manifiesto cambia.
    """
    content = (await file.read()).decode("utf-8")
    if not content.strip():
        raise BadRequestError(detail="El manifiesto está vacío")
    source = file.filename or "manifest.minerva.yml"
    return ManifestLoader(session).import_manifest(content, source)


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: str,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.get_application(application_id)


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: str,
    data: ApplicationUpdate,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.update_application(application_id, data)


@router.post("/{application_id}/regenerate-secret", response_model=ApplicationWithSecrets)
def regenerate_secret(
    application_id: str,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_user),
):
    """Genera un nuevo client_secret (se muestra una sola vez). El client_id no cambia."""
    return service.regenerate_secret(application_id)


@router.post("/{application_id}/redirect-uris", response_model=RedirectURIRead, status_code=201)
def add_redirect_uri(
    application_id: str,
    data: RedirectURICreate,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.add_redirect_uri(application_id, data)


@router.get("/{application_id}/redirect-uris", response_model=list[RedirectURIRead])
def list_redirect_uris(
    application_id: str,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_user),
):
    return service.list_redirect_uris(application_id)
