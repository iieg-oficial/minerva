"""HTTP del módulo de portal."""

from fastapi import APIRouter, Depends, HTTPException, Request
from minerva_sdk import settings

from minerva_example.core import config
from minerva_example.modules.portal.consts import DOCUMENTS_CREATE, DOCUMENTS_VIEW, SYSTEM_MANAGE
from minerva_example.modules.portal.service import current_user, portal_service, require_permission

router = APIRouter(prefix="/api", tags=["Consumidor"])


@router.get("/config")
async def config_status():
    return config.integration_status()


@router.get("/session")
async def session_status(request: Request):
    try:
        return await portal_service.describe_session(request)
    except HTTPException as exc:
        return {"authenticated": False, "error": str(exc.detail)}


@router.get("/whoami")
async def whoami(user: dict = Depends(current_user)):
    return {"sub": user["sub"], "email": user.get("email"), "name": user.get("name"), "roles": user.get("roles", [])}


@router.get("/permissions")
async def permissions(request: Request):
    return {"application": settings.application_code, "permissions": await portal_service.permissions(request)}


@router.get("/documents")
async def view_documents(user: dict = Depends(require_permission(DOCUMENTS_VIEW))):
    return {
        "message": f"Documentos visibles para {user.get('email') or user['sub']}",
        "items": portal_service.repository.list_documents(),
    }


@router.post("/documents")
async def create_document(user: dict = Depends(require_permission(DOCUMENTS_CREATE))):
    return {
        "message": "Documento de ejemplo creado",
        "item": {"folio": "PD-2026-NUEVO", "created_by": user.get("email") or user["sub"]},
    }


@router.get("/admin")
async def administer(user: dict = Depends(require_permission(SYSTEM_MANAGE))):
    return {
        "message": "Acceso administrativo concedido",
        "user": user.get("email") or user["sub"],
        "stats": portal_service.repository.get_admin_stats(),
    }
