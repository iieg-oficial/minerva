"""Protección CSRF (synchronizer token) + validación de Origin para el panel.

La sesión del panel es stateful (cookie opaca + contenedor en Redis), así que una
petición mutante que llegue con esa cookie desde otro sitio (CSRF) debe rechazarse.
Se exige el token CSRF de la sesión en `X-CSRF-Token` y, como defensa en profundidad
(no confiar solo en SameSite), que el `Origin` coincida con el frontend.

El control se aplica en un solo punto —este middleware— en vez de anotar decenas de
rutas admin. Solo actúa sobre peticiones que **traen la cookie de panel**: los
endpoints OAuth de consumidor son server-to-server (sin esa cookie) y no se ven
afectados. `# ponytail: gate por presencia de cookie; consumidores quedan fuera solos`.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core import panel_session
from app.core.config import settings
from app.core.redis import get_redis

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Rutas que NO exigen token CSRF aunque lleguen con cookie: crean/renuevan la sesión
# (su autenticación son credenciales, no la sesión previa) o son OAuth de consumidor.
# `/auth/authorize` entra por su POST form (OIDC Core 3.1.2.1): lo emite el consumidor
# desde su propia página, que no puede conocer nuestro token CSRF. No abre un hueco: la
# cookie de panel es SameSite=Lax y no viaja en un POST cross-site, la comprobación de
# `Origin` de arriba se sigue aplicando, y la defensa del consumidor contra login-CSRF
# es su `state`.
_CSRF_EXEMPT_PREFIXES = ("/auth/login", "/auth/register", "/auth/token", "/auth/revoke", "/auth/authorize")


async def panel_csrf_middleware(request: Request, call_next):
    if request.method in _UNSAFE_METHODS:
        sid = request.cookies.get(settings.session_cookie_name)
        if sid:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != settings.FRONTEND_URL.rstrip("/"):
                return JSONResponse({"detail": "Origin no permitido"}, status_code=403)
            if not request.url.path.startswith(_CSRF_EXEMPT_PREFIXES):
                container = await panel_session.read(get_redis(), sid)
                if container is None or not panel_session.csrf_valid(container, request.headers.get("x-csrf-token")):
                    return JSONResponse({"detail": "Token CSRF inválido o ausente"}, status_code=403)
    return await call_next(request)
