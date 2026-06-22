from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from sqlmodel import Session

from app.core.config import settings
from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.core.exceptions import BadRequestError
from app.core.rate_limit import enforce_rate_limit
from app.core.redis import get_redis
from app.core.token_blacklist import revoke_jti
from app.modules.audit.service import AuditService
from app.modules.auth.schemas import AuthLogin, AuthRegister, AuthTokenResponse
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_auth_service(session: Session = Depends(get_db)) -> AuthService:
    return AuthService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


@router.post("/register", response_model=AuthTokenResponse, status_code=201)
def register(
    data: AuthRegister,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = service.register(data)
    audit.log("manual_register_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
    return result


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    data: AuthLogin,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
):
    await enforce_rate_limit(
        redis,
        f"minerva:rl:login:{request.client.host}",
        settings.RATE_LIMIT_LOGIN_MAX,
        settings.RATE_LIMIT_LOGIN_WINDOW,
    )
    try:
        result = service.login(data.email, data.password)
        audit.log("manual_login_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
        return result
    except Exception:
        audit.log(
            "manual_login_failed",
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            event_metadata={"email": data.email},
        )
        raise


@router.post("/logout")
def logout(
    request: Request,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
    current_user: dict = Depends(get_current_user),
):
    audit.log(
        "logout",
        actor_user_id=current_user.get("sub"),
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
    )
    return {"message": "Sesión cerrada"}


@router.get("/me")
def me(
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
):
    return service.get_me(current_user["sub"])


@router.get("/google/login")
def google_login():
    if not settings.GOOGLE_CLIENT_ID:
        return JSONResponse(
            {"detail": "Google OAuth no configurado. Configure GOOGLE_CLIENT_ID en .env"}, status_code=501
        )
    authorize_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={settings.GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=openid%20profile%20email"
        f"&hd={settings.ALLOWED_GOOGLE_DOMAIN}"
    )
    return RedirectResponse(authorize_url)


@router.get("/google/callback")
def google_callback(code: str):
    return JSONResponse(
        {"detail": "Google callback pendiente de implementación. TODO: integrar authlib para intercambio de tokens."},
        status_code=501,
    )


@router.get("/authorize")
async def authorize(
    request: Request,
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: str = Query(...),
    scope: str = Query("openid profile email"),
    response_type: str = Query("code"),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    nonce: str | None = Query(None),
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
):
    await enforce_rate_limit(
        redis,
        f"minerva:rl:authorize:{request.client.host}",
        settings.RATE_LIMIT_AUTHORIZE_MAX,
        settings.RATE_LIMIT_AUTHORIZE_WINDOW,
    )
    redirect_url = service.authorize(
        client_id,
        redirect_uri,
        current_user["sub"],
        state,
        scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
    )
    return RedirectResponse(redirect_url)


@router.get("/authorize/url")
async def authorize_url(
    request: Request,
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: str = Query(...),
    scope: str = Query("openid profile email"),
    response_type: str = Query("code"),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    nonce: str | None = Query(None),
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
):
    """Variante JSON de /authorize para el frontend SPA.

    Devuelve la URL de redirección (con el `code`) en lugar de un RedirectResponse,
    porque un SPA no puede leer el header `Location` de un redirect cross-origin.
    El frontend hace `window.location` con esta URL.
    """
    await enforce_rate_limit(
        redis,
        f"minerva:rl:authorize:{request.client.host}",
        settings.RATE_LIMIT_AUTHORIZE_MAX,
        settings.RATE_LIMIT_AUTHORIZE_WINDOW,
    )
    redirect_url = service.authorize(
        client_id,
        redirect_uri,
        current_user["sub"],
        state,
        scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
    )
    return {"redirect_url": redirect_url}


async def _read_token_request(request: Request) -> dict:
    """Lee el cuerpo del canje aceptando el estándar OIDC (form-urlencoded) y el
    JSON legacy que ya usaba el frontend. El form-urlencoded se parsea a mano para
    no depender de python-multipart."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return await request.json()
    raw = (await request.body()).decode("utf-8")
    return {key: values[0] for key, values in parse_qs(raw).items()}


@router.post("/token", response_model=AuthTokenResponse)
async def token_exchange(
    request: Request,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
):
    body = await _read_token_request(request)
    grant_type = body.get("grant_type", "authorization_code")

    if grant_type == "refresh_token":
        client_id = body.get("client_id")
        client_secret = body.get("client_secret")
        refresh_token = body.get("refresh_token")
        if not all([client_id, client_secret, refresh_token]):
            raise BadRequestError(detail="Faltan parámetros requeridos para refrescar el token")
        result, revoked_jtis = service.rotate_refresh_token(client_id, client_secret, refresh_token)
        for jti in revoked_jtis:
            await revoke_jti(redis, jti, settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES * 60)
        audit.log("token_refresh_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
        return result

    if grant_type != "authorization_code":
        raise BadRequestError(detail="grant_type no soportado; use authorization_code o refresh_token")

    client_id = body.get("client_id")
    client_secret = body.get("client_secret")
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    if not all([client_id, client_secret, code, redirect_uri]):
        raise BadRequestError(detail="Faltan parámetros requeridos para el canje del código")

    result = service.exchange_token(client_id, client_secret, code, redirect_uri, body.get("code_verifier"))
    audit.log("token_exchange_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
    return result


@router.post("/revoke")
async def revoke_token(
    request: Request,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
):
    """Revocación de refresh token (RFC 7009). Revoca toda la familia y blacklista
    los access tokens asociados. Responde 200 aunque el token no exista."""
    body = await _read_token_request(request)
    client_id = body.get("client_id")
    client_secret = body.get("client_secret")
    token = body.get("token") or body.get("refresh_token")
    if not all([client_id, client_secret, token]):
        raise BadRequestError(detail="Faltan parámetros requeridos para revocar el token")

    revoked_jtis = service.revoke_refresh_token(client_id, client_secret, token)
    for jti in revoked_jtis:
        await revoke_jti(redis, jti, settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES * 60)
    audit.log("token_revoke", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
    return {"revoked": True}


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh_token(
    request: Request,
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_user),
):
    return service.reissue_session_token(current_user)
