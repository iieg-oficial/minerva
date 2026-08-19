"""HTTP del módulo de autenticación."""

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from minerva_sdk import MinervaOIDCError

from minerva_example.core import config
from minerva_example.modules.auth.consts import SESSION_COOKIE, STATE_COOKIE
from minerva_example.modules.auth.service import auth_service

router = APIRouter(tags=["Autenticación"])


def redirect_error(message: str) -> RedirectResponse:
    return RedirectResponse(f"/?{urlencode({'error': message})}", status_code=303)


def clear_state(response: RedirectResponse) -> RedirectResponse:
    response.delete_cookie(STATE_COOKIE)
    return response


@router.get("/login")
async def login(prompt: str | None = "select_account"):
    try:
        authorization = auth_service.begin_login(prompt)
    except ValueError as exc:
        return redirect_error(str(exc))

    response = RedirectResponse(authorization.url)
    response.set_cookie(
        STATE_COOKIE,
        authorization.state,
        httponly=True,
        samesite="lax",
        secure=config.cookie_secure(),
        max_age=10 * 60,
    )
    return response


@router.get("/callback")
async def callback(request: Request, state: str, code: str | None = None, error: str | None = None):
    verifier = auth_service.consume_verifier(request.cookies.get(STATE_COOKIE), state)
    if not verifier:
        return clear_state(redirect_error("State inválido o ya utilizado; inicia el login nuevamente"))
    if error or not code:
        message = (
            "No tienes acceso a esta aplicación"
            if error == "access_denied"
            else f"Minerva devolvió: {error or 'sin código'}"
        )
        return clear_state(redirect_error(message))

    try:
        tokens = await auth_service.exchange_code(code, verifier)
    except (MinervaOIDCError, ValueError) as exc:
        return clear_state(redirect_error(str(exc)))

    session_id = auth_service.create_session(tokens)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        secure=config.cookie_secure(),
        max_age=60 * 60 * 8,
    )
    return clear_state(response)


@router.post("/refresh")
async def refresh(request: Request):
    session = auth_service.get_session(request)
    if not session or not session.get("refresh_token"):
        return redirect_error("No hay refresh token; inicia sesión")
    try:
        await auth_service.refresh(session)
    except MinervaOIDCError as exc:
        return redirect_error(f"No se pudo refrescar la sesión: {exc}")
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    warning = None
    try:
        await auth_service.logout(request)
    except MinervaOIDCError as exc:
        warning = f"La sesión local se cerró, pero Minerva no pudo revocar el refresh token: {exc}"
    response = redirect_error(warning) if warning else RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
