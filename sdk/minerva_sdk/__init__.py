"""SDK mínimo de Minerva para sistemas consumidores (FastAPI).

Uso típico::

    from minerva_sdk.fastapi import require_permission

    @router.post("/oficios")
    def crear_oficio(user=Depends(require_permission("godin.oficios.create"))):
        return {"message": "Oficio creado", "user": user["email"]}
"""

from minerva_sdk.config import MinervaSettings, settings
from minerva_sdk.fastapi import get_current_user, require_permission

__all__ = ["MinervaSettings", "settings", "get_current_user", "require_permission"]
__version__ = "0.1.0"
