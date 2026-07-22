from fastapi import Depends
from sqlmodel import Session

from app.core.dependencies.auth import get_current_panel_user
from app.core.dependencies.db import get_db
from app.core.exceptions import ForbiddenError
from app.modules.authorization.service import AuthorizationService


async def require_minerva_admin(
    current_user: dict = Depends(get_current_panel_user),
    session: Session = Depends(get_db),
) -> dict:
    """Exige que el usuario autenticado sea administrador global de Minerva.

    Protege los endpoints de gestión del panel (usuarios, aplicaciones, roles,
    permisos, grupos, auditoría). Autentica por la cookie de sesión del panel
    (contenedor en Redis, `typ=session`): no basta con estar autenticado ni vale un
    access de consumidor cuyo sujeto sea admin.
    """
    service = AuthorizationService(session)
    if not service.is_minerva_admin(current_user["sub"]):
        raise ForbiddenError(detail="Requiere rol de administrador de Minerva")
    return current_user
