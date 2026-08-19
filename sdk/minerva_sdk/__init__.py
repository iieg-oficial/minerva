"""SDK mínimo de Minerva para sistemas consumidores (FastAPI).

Uso típico::

    from minerva_sdk.fastapi import require_permission

    @router.post("/oficios")
    def create_document(user=Depends(require_permission("portal_demo.documents.create"))):
        return {"message": "Oficio creado", "user": user["email"]}
"""

from minerva_sdk.config import MinervaSettings, settings
from minerva_sdk.fastapi import (
    check_permission,
    clear_caches,
    get_current_user,
    get_permissions,
    invalidate_token,
    require_permission,
    validate_access_token,
)
from minerva_sdk.oidc import AuthorizationRequest, MinervaOIDC, MinervaOIDCError

__all__ = [
    "MinervaSettings",
    "settings",
    "AuthorizationRequest",
    "MinervaOIDC",
    "MinervaOIDCError",
    "get_current_user",
    "require_permission",
    "validate_access_token",
    "get_permissions",
    "check_permission",
    "invalidate_token",
    "clear_caches",
]
__version__ = "0.3.0"
