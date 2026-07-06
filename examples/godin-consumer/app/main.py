"""Ejemplo mínimo de sistema consumidor de Minerva: login con PKCE (cliente
público, sin client_secret), canje del código y un endpoint protegido con
`require_permission` del SDK. Ver README.md de esta carpeta para el flujo
de prueba manual completo.
"""

import base64
import hashlib
import secrets

import httpx
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from minerva_sdk.fastapi import get_current_user, require_permission

from app.config import settings

app = FastAPI(title="Godín (ejemplo de integración con Minerva)")

# Almacén en memoria para el `code_verifier` por `state`. Solo para demo: un
# consumidor real lo guarda en la sesión del usuario, no en un dict global.
_pkce_store: dict[str, str] = {}


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@app.get("/login")
def login():
    """Inicia el flujo Authorization Code + PKCE contra Minerva."""
    verifier = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(16)
    _pkce_store[state] = verifier

    url = (
        f"{settings.issuer_url}/auth/authorize"
        f"?client_id={settings.client_id}"
        f"&redirect_uri={settings.redirect_uri}"
        f"&response_type=code"
        f"&scope=openid profile email"
        f"&state={state}"
        f"&code_challenge={_code_challenge(verifier)}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(url)


@app.get("/callback")
async def callback(state: str, code: str | None = None, error: str | None = None):
    """Canjea el código por tokens. Sin `client_secret`: el cliente es público,
    PKCE es lo único que liga el código al `/login` que lo originó."""
    verifier = _pkce_store.pop(state, None)
    # Minerva solo emite `code` si el usuario tiene al menos un rol en esta app. Si no,
    # regresa error=access_denied (OAuth2) sin `code`. `code` es opcional para poder
    # distinguir ese caso en vez de fallar con 422 por parámetro faltante.
    if error or not code:
        return JSONResponse(
            status_code=403,
            content={
                "error": error or "invalid_request",
                "mensaje": "No tienes acceso a esta aplicación. Solicítalo a un administrador de Minerva.",
            },
        )
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.post(
            f"{settings.issuer_url}/auth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.client_id,
                "code": code,
                "redirect_uri": settings.redirect_uri,
                "code_verifier": verifier,
            },
        )
        resp.raise_for_status()
    # Demo: en un consumidor real, esto se guarda en la sesión/cookie del
    # usuario, no se devuelve crudo al navegador.
    return resp.json()


@app.get("/whoami")
async def whoami(user: dict = Depends(get_current_user)):
    """Identidad resuelta del access token (RS256/JWKS, sin secreto compartido)."""
    return {"sub": user["sub"], "email": user.get("email"), "name": user.get("name")}


@app.get("/protegido")
def protegido(user: dict = Depends(require_permission("godin.oficios.create"))):
    """Solo responde si el usuario tiene el permiso `godin.oficios.create` en
    Minerva — validado en tiempo real, nunca por rol local."""
    return {"mensaje": "acceso concedido", "user": user["email"]}
