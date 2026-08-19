from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlmodel import Session

from app.core.dependencies.admin import require_minerva_admin
from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.core.exceptions import BadRequestError
from app.modules.applications.schemas import (
    ApplicationBranding,
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationWithSecrets,
    RedirectURICreate,
    RedirectURIRead,
)
from app.modules.applications.service import ApplicationService
from app.modules.audit.service import AuditService
from app.modules.devkit.manifest import ManifestLoader, parse_manifest, validate_manifest
from app.modules.devkit.schemas import ManifestImportResult
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/applications", tags=["Applications"], dependencies=[Depends(require_minerva_admin)])

# Router público (sin autenticación): la pantalla de login necesita el branding de
# la app solicitante antes de que el usuario tenga sesión. Solo expone datos no sensibles.
public_router = APIRouter(prefix="/public", tags=["Public"])


def _audit_request_operation(
    audit: AuditService,
    request: Request,
    current_user: dict,
    action: str,
    target_type: str,
    target_id: str | None,
    result: str,
    application_id: str | None = None,
    **metadata: object,
) -> None:
    audit.log(
        action,
        actor_user_id=current_user["sub"],
        target_type=target_type,
        target_id=target_id,
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": result, **metadata},
    )


def get_application_service(session: Session = Depends(get_db)) -> ApplicationService:
    return ApplicationService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


@public_router.get("/apps/{client_id}/branding", response_model=ApplicationBranding)
def get_app_branding(
    client_id: str,
    service: ApplicationService = Depends(get_application_service),
):
    """Branding público de una aplicación por client_id, para personalizar el login."""
    return service.get_branding(client_id)


@router.get("", response_model=PaginatedResponse[ApplicationRead])
def list_applications(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    apps, total = service.list_applications(offset, limit)
    return PaginatedResponse.create(apps, total)


@router.post("", response_model=ApplicationWithSecrets, status_code=201)
def create_application(
    data: ApplicationCreate,
    request: Request,
    service: ApplicationService = Depends(get_application_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.create_application(data, commit=False)
    audit.log(
        "application_create",
        actor_user_id=_current_user["sub"],
        target_type="application",
        target_id=result.id,
        application_id=result.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result


@router.post("/import-manifest", response_model=ManifestImportResult)
async def import_manifest(
    request: Request,
    file: UploadFile = File(..., description="Archivo manifest.minerva.yml"),
    session: Session = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    current_user: dict = Depends(get_current_panel_user),
):
    """Importa (o recarga) un manifiesto de permisos/roles de un sistema.

    Hace upsert de la aplicación, sus permisos y roles a partir del YAML, por lo
    que sirve tanto para dar de alta un sistema como para volver a cargar sus
    permisos cuando el manifiesto cambia.
    """
    source = file.filename or "manifest.minerva.yml"
    try:
        content = (await file.read()).decode("utf-8")
        if not content.strip():
            raise BadRequestError(detail="El manifiesto está vacío")
        result = ManifestLoader(session).import_manifest(content, source, commit=False)
    except Exception as exc:
        session.rollback()
        _audit_request_operation(
            audit, request, current_user, "manifest_import", "manifest", source, "failure", error=type(exc).__name__
        )
        raise
    _audit_request_operation(
        audit,
        request,
        current_user,
        "manifest_import",
        "application",
        result.application_id,
        "success",
        application_id=result.application_id,
        source=source,
    )
    return result


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: str,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.get_application(application_id)


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: str,
    data: ApplicationUpdate,
    request: Request,
    service: ApplicationService = Depends(get_application_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    result = service.update_application(application_id, data, commit=False)
    audit.log(
        "application_update",
        actor_user_id=_current_user["sub"],
        target_type="application",
        target_id=application_id,
        application_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )
    return result


@router.delete("/{application_id}", status_code=204)
def delete_application(
    application_id: str,
    request: Request,
    service: ApplicationService = Depends(get_application_service),
    audit: AuditService = Depends(get_audit_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    """Elimina la aplicación con sus permisos, roles, redirect URIs y asignaciones."""
    service.delete_application(application_id, commit=False)
    audit.log(
        "application_delete",
        actor_user_id=_current_user["sub"],
        target_type="application",
        target_id=application_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"result": "success"},
    )


@router.post("/{application_id}/import-manifest", response_model=ManifestImportResult)
async def update_application_manifest(
    application_id: str,
    request: Request,
    file: UploadFile = File(..., description="Archivo manifest.minerva.yml"),
    service: ApplicationService = Depends(get_application_service),
    session: Session = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    current_user: dict = Depends(get_current_panel_user),
):
    """Recarga el manifiesto de una aplicación existente (upsert de permisos/roles).

    A diferencia del import global, exige que el `application.code` del manifiesto
    coincida con el slug de la aplicación, para no modificar otra app por error.
    """
    source = file.filename or "manifest.minerva.yml"
    try:
        app = service.get_application(application_id)
        content = (await file.read()).decode("utf-8")
        if not content.strip():
            raise BadRequestError(detail="El manifiesto está vacío")
        code = validate_manifest(parse_manifest(content))
        if code != app.slug:
            raise BadRequestError(detail=f"El manifiesto pertenece a `{code}` pero la aplicación es `{app.slug}`")
        result = ManifestLoader(session).import_manifest(content, source, commit=False)
    except Exception as exc:
        session.rollback()
        _audit_request_operation(
            audit,
            request,
            current_user,
            "manifest_import",
            "application",
            application_id,
            "failure",
            error=type(exc).__name__,
            source=source,
        )
        raise
    _audit_request_operation(
        audit,
        request,
        current_user,
        "manifest_import",
        "application",
        application_id,
        "success",
        application_id=application_id,
        source=source,
    )
    return result


@router.post("/{application_id}/regenerate-secret", response_model=ApplicationWithSecrets)
def regenerate_secret(
    application_id: str,
    request: Request,
    service: ApplicationService = Depends(get_application_service),
    session: Session = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    current_user: dict = Depends(get_current_panel_user),
):
    """Genera un nuevo client_secret (se muestra una sola vez). El client_id no cambia."""
    try:
        result = service.regenerate_secret(application_id, commit=False)
    except Exception as exc:
        session.rollback()
        _audit_request_operation(
            audit,
            request,
            current_user,
            "application_secret_regenerate",
            "application",
            application_id,
            "failure",
            error=type(exc).__name__,
        )
        raise
    _audit_request_operation(
        audit,
        request,
        current_user,
        "application_secret_regenerate",
        "application",
        application_id,
        "success",
        application_id=application_id,
    )
    return result


@router.post("/{application_id}/redirect-uris", response_model=RedirectURIRead, status_code=201)
def add_redirect_uri(
    application_id: str,
    data: RedirectURICreate,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.add_redirect_uri(application_id, data)


@router.get("/{application_id}/redirect-uris", response_model=list[RedirectURIRead])
def list_redirect_uris(
    application_id: str,
    service: ApplicationService = Depends(get_application_service),
    _current_user: dict = Depends(get_current_panel_user),
):
    return service.list_redirect_uris(application_id)
