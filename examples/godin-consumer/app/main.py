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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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


# --- Modo popup (opt-in con response_mode=web_message) --------------------
# En vez de sacar al usuario con un redirect full-page, abrimos el login de
# Minerva en un popup. Minerva completa el flujo y devuelve el `code` al opener
# vía postMessage (con targetOrigin fijado al redirect_uri), sin navegar la app.
# No requiere cambios en el SDK ni en Minerva-backend.

_POPUP_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Godín · login popup</title></head>
<body style="font-family:system-ui;max-width:640px;margin:3rem auto">
  <h1>Godín — login en popup</h1>
  <button id="login" style="font-size:1rem;padding:.6rem 1rem">Iniciar sesión (popup)</button>
  <pre id="out" style="background:#f4f4f4;padding:1rem;margin-top:1rem;white-space:pre-wrap"></pre>
  <script>
    // Origen de Minerva-web: solo aceptamos postMessage de aquí.
    const MINERVA_ORIGIN = new URL("__WEB_URL__").origin;
    const AUTH_URL = "__AUTH_URL__";
    const out = document.getElementById("out");

    window.addEventListener("message", async (e) => {
      // Validación de origen: descarta mensajes de cualquier otra ventana.
      if (e.origin !== MINERVA_ORIGIN || e.data?.source !== "minerva") return;
      if (e.data.error) {
        out.textContent = "Acceso denegado: " + e.data.error +
          "\\nSolicita acceso a un administrador de Minerva.";
        return;
      }
      // El opener recibe el `code`; el canje se hace server-to-server.
      const resp = await fetch("/popup/exchange", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({code: e.data.code, state: e.data.state}),
      });
      out.textContent = "Tokens:\\n" + JSON.stringify(await resp.json(), null, 2);
    });

    document.getElementById("login").onclick = () => {
      window.open(AUTH_URL, "minerva-login", "width=480,height=680");
    };
  </script>
</body></html>"""


@app.get("/popup", response_class=HTMLResponse)
def popup():
    """Sirve una página mínima que abre el login de Minerva en un popup."""
    verifier = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(16)
    _pkce_store[state] = verifier
    auth_url = (
        f"{settings.web_url}/authorize"
        f"?client_id={settings.client_id}"
        f"&redirect_uri={settings.redirect_uri}"
        f"&response_type=code"
        f"&scope=openid profile email"
        f"&state={state}"
        f"&code_challenge={_code_challenge(verifier)}"
        f"&code_challenge_method=S256"
        f"&response_mode=web_message"  # <-- opt-in al modo popup
    )
    html = _POPUP_HTML.replace("__WEB_URL__", settings.web_url).replace("__AUTH_URL__", auth_url)
    return HTMLResponse(html)


@app.post("/popup/exchange")
async def popup_exchange(payload: dict):
    """Canjea el `code` recibido por postMessage. El `verifier` se busca por
    `state` en el almacén PKCE, igual que en `/callback` (que aquí no se usa)."""
    state = payload.get("state")
    code = payload.get("code")
    verifier = _pkce_store.pop(state, None)
    if not code or not verifier:
        return JSONResponse(status_code=400, content={"error": "invalid_request"})
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
