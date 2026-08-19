"""Identidad, permisos y casos de uso del portal."""

from fastapi import Request
from minerva_sdk import check_permission, get_permissions, validate_access_token

from minerva_example.modules.auth.service import auth_service
from minerva_example.modules.portal.repository import PortalRepository


class PortalService:
    def __init__(self):
        self.repository = PortalRepository()

    async def current_user(self, request: Request) -> dict:
        return await validate_access_token(auth_service.require_access_token(request))

    async def authorize(self, request: Request, permission: str) -> dict:
        return await check_permission(auth_service.require_access_token(request), permission)

    async def describe_session(self, request: Request) -> dict:
        session = auth_service.get_session(request)
        if not session:
            return {"authenticated": False}
        user = await validate_access_token(session["access_token"])
        permissions = sorted(await get_permissions(session["access_token"]))
        return {
            "authenticated": True,
            "user": {
                "sub": user["sub"],
                "email": user.get("email"),
                "name": user.get("name"),
                "roles": user.get("roles", []),
            },
            "permissions": permissions,
        }

    async def permissions(self, request: Request) -> list[str]:
        return sorted(await get_permissions(auth_service.require_access_token(request)))


portal_service = PortalService()


async def current_user(request: Request) -> dict:
    return await portal_service.current_user(request)


def require_permission(permission: str):
    async def dependency(request: Request) -> dict:
        return await portal_service.authorize(request, permission)

    return dependency
