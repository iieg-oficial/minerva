from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from sqlmodel import Session

from app.core.config import settings
from app.core.dependencies.auth import get_current_user
from app.core.dependencies.db import get_db
from app.core.rate_limit import enforce_rate_limit
from app.core.redis import get_redis
from app.modules.audit.service import AuditService
from app.modules.auth.schemas import AuthLogin, AuthRegister, AuthTokenResponse, TokenExchange
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


@router.post("/token", response_model=AuthTokenResponse)
def token_exchange(
    data: TokenExchange,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
):
    result = service.exchange_token(
        data.client_id, data.client_secret, data.code, data.redirect_uri, data.code_verifier
    )
    audit.log("token_exchange_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
    return result


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh_token(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    from app.core.security import create_access_token

    token = create_access_token(
        user_id=current_user["sub"],
        email=current_user["email"],
        name=current_user.get("name", ""),
        application_slug=current_user.get("aud", ""),
        roles=current_user.get("roles", []),
        permissions=current_user.get("permissions", []),
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}
