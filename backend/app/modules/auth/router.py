import asyncio
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from sqlmodel import Session

from app.core import panel_session
from app.core.config import settings
from app.core.dependencies.auth import (
    _resolve_token,
    get_current_panel_user,
    get_optional_panel_user,
    get_panel_session,
)
from app.core.dependencies.db import get_db
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError, TooManyRequestsError
from app.core.rate_limit import enforce_rate_limit
from app.core.redis import get_redis
from app.core.token_blacklist import revoke_jti
from app.modules.audit.service import AuditService
from app.modules.auth.schemas import (
    AccountDescriptor,
    AuthLogin,
    AuthRegister,
    AuthTokenResponse,
    PanelSessionResponse,
    SessionView,
    SetActiveRequest,
)
from app.modules.auth.service import AuthService, RefreshReuseError, build_callback_url
from app.modules.authorization.service import AuthorizationService

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _enforce_rate_limit_audited(
    redis: Redis,
    key: str,
    max_requests: int,
    window: int,
    audit: AuditService,
    request: Request,
    endpoint: str,
) -> None:
    """Igual que `enforce_rate_limit`, pero deja registro en AuditLog al dispararse
    el límite (señal de fuerza bruta visible junto a login/token, no solo un 429
    silencioso)."""
    try:
        await enforce_rate_limit(redis, key, max_requests, window)
    except TooManyRequestsError:
        audit.log(
            "rate_limit_exceeded",
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            event_metadata={"endpoint": endpoint},
        )
        raise


def _login_redirect_url(request: Request) -> str:
    """URL de login con `next=` apuntando al `/authorize` original. Reutiliza el
    patrón `next=` que ya soporta el frontend (`LoginPage.jsx`/`AuthorizePage.jsx`)
    para retomar el flujo tras autenticar — sin sesión nueva en Redis."""
    next_path = f"/authorize?{request.url.query}"
    return f"{settings.FRONTEND_URL}/login?next={quote(next_path, safe='')}"


def get_auth_service(session: Session = Depends(get_db)) -> AuthService:
    return AuthService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


def _set_session_cookie(response: Response, sid: str) -> None:
    """Fija la cookie opaca de sesión del panel. Nombre y Secure dependen del entorno
    (`__Host-` + Secure en prod; nombre distinto sin Secure en dev HTTP). SameSite=Lax
    es deliberado: la cookie debe viajar cuando un consumidor navega a `/authorize`."""
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sid,
        max_age=settings.effective_token_expire_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


async def _establish_panel_session(
    request: Request, response: Response, session: Session, redis: Redis, token: str
) -> dict:
    """Mete el JWT `typ=session` recién emitido en el contenedor (Redis) como cuenta
    activa, rota el sid (fijación de sesión) y el CSRF, y fija la cookie. Devuelve
    solo el descriptor de la cuenta activa + el CSRF (nunca el JWT)."""
    payload = await _resolve_token(token, session, redis, expected_types={"session"}, audience="minerva")
    sub = payload["sub"]
    is_admin = AuthorizationService(session).is_minerva_admin(sub)
    old_sid = request.cookies.get(settings.session_cookie_name)
    container = await panel_session.read(redis, old_sid) or panel_session.empty_container()
    panel_session.rotate_csrf(container)
    panel_session.add_account(
        container,
        sub,
        token,
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        is_admin=is_admin,
        exp=payload.get("exp", 0),
        jti=payload.get("jti"),
    )
    sid = await panel_session.rotate_sid(redis, old_sid, container)
    _set_session_cookie(response, sid)
    return {"active": panel_session.descriptor(sub, container["accounts"][sub]), "csrf": container["csrf"]}


async def _revoke_account_token(redis: Redis, account: dict | None) -> None:
    """Blacklistea el `jti` del token de una cuenta hasta que habría expirado."""
    if not account:
        return
    ttl = int(account.get("exp", 0) - datetime.now(timezone.utc).timestamp())
    await revoke_jti(redis, account.get("jti"), max(ttl, 1))


@router.post("/register", response_model=PanelSessionResponse, status_code=201)
async def register(
    data: AuthRegister,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    if not settings.MINERVA_ENABLE_PUBLIC_REGISTER:
        raise ForbiddenError(detail="El registro público está deshabilitado; contacta a un administrador")
    result = service.register(data)
    audit.log("manual_register_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
    return await _establish_panel_session(request, response, session, redis, result["access_token"])


@router.post("/login", response_model=PanelSessionResponse)
async def login(
    data: AuthLogin,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await _enforce_rate_limit_audited(
        redis,
        f"minerva:rl:login:{request.client.host}",
        settings.RATE_LIMIT_LOGIN_MAX,
        settings.RATE_LIMIT_LOGIN_WINDOW,
        audit,
        request,
        "login",
    )
    try:
        result = service.login(data.email, data.password)
        audit.log("manual_login_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
        return await _establish_panel_session(request, response, session, redis, result["access_token"])
    except Exception:
        audit.log(
            "manual_login_failed",
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            event_metadata={"email": data.email},
        )
        raise


@router.get("/session", response_model=SessionView)
async def get_session(ps: dict = Depends(get_panel_session)):
    """Estado del selector multi-cuenta (cuentas del navegador + activa + CSRF). Fuente
    de verdad del selector: el navegador ya no guarda tokens. Tolera no tener cuenta
    activa (logout suave) para poder seguir pintando el selector."""
    return panel_session.session_view(ps["container"])


@router.post("/session/active", response_model=AccountDescriptor)
async def set_active_account(
    data: SetActiveRequest,
    ps: dict = Depends(get_panel_session),
    redis: Redis = Depends(get_redis),
):
    """Cambia la cuenta activa del navegador (dentro del contenedor de sesión)."""
    container = ps["container"]
    if not panel_session.set_active(container, data.sub):
        raise NotFoundError(detail="La cuenta no está iniciada en este navegador")
    await panel_session.write(redis, ps["sid"], container)
    return panel_session.descriptor(data.sub, container["accounts"][data.sub])


@router.post("/logout")
async def logout(
    request: Request,
    ps: dict = Depends(get_panel_session),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
):
    """Logout suave (estilo Google): sale de la cuenta activa pero conserva las cuentas
    del navegador y sus tokens (para volver a entrar sin re-teclear). NO revoca el jti:
    para invalidar de verdad están "quitar cuenta" y "cerrar todas las sesiones"."""
    container = ps["container"]
    active = container.get("active")
    panel_session.soft_logout(container)
    await panel_session.write(redis, ps["sid"], container)
    audit.log(
        "logout",
        actor_user_id=active,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
    )
    return {"message": "Sesión cerrada"}


@router.delete("/session/accounts/{sub}")
async def remove_account(
    sub: str,
    ps: dict = Depends(get_panel_session),
    redis: Redis = Depends(get_redis),
):
    """Quita una cuenta del dispositivo y revoca su token (blacklist del jti). Las
    demás cuentas del navegador siguen intactas."""
    container = ps["container"]
    account = panel_session.remove_account(container, sub)
    await _revoke_account_token(redis, account)
    await panel_session.write(redis, ps["sid"], container)
    return {"removed": account is not None}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    ps: dict = Depends(get_panel_session),
    redis: Redis = Depends(get_redis),
):
    """Cierra TODAS las cuentas del navegador: revoca cada jti, destruye el contenedor
    en Redis y borra la cookie."""
    container = ps["container"]
    for account in container["accounts"].values():
        await _revoke_account_token(redis, account)
    await panel_session.destroy(redis, ps["sid"])
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"message": "Todas las sesiones cerradas"}


@router.get("/me")
def me(
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_panel_user),
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
    prompt: str | None = Query(None),
    max_age: int | None = Query(None),
    service: AuthService = Depends(get_auth_service),
    current_user: dict | None = Depends(get_optional_panel_user),
    redis: Redis = Depends(get_redis),
    audit: AuditService = Depends(get_audit_service),
):
    """Inicia el flujo `/authorize`. Modo A: la cookie de sesión del panel viaja en
    la navegación directa (SameSite=Lax) y resuelve la cuenta activa. Modo B: un
    sistema externo redirige aquí el navegador sin sesión — se redirige a login y se
    retoma con `?next=` tras autenticar (mismo patrón que ya usa `AuthorizePage.jsx`)."""
    await _enforce_rate_limit_audited(
        redis,
        f"minerva:rl:authorize:{request.client.host}",
        settings.RATE_LIMIT_AUTHORIZE_MAX,
        settings.RATE_LIMIT_AUTHORIZE_WINDOW,
        audit,
        request,
        "authorize",
    )
    # Valida client_id/redirect_uri ANTES de cualquier redirect (incluso sin
    # sesión): nunca se redirige a un destino no confiable (evita open redirect).
    service.validate_client_and_redirect(client_id, redirect_uri)

    # Solo se soporta el flujo de código (lo que ya declara el discovery). El error
    # vuelve al cliente por redirect, no como 400: para eso el destino se validó arriba.
    if response_type != "code":
        return RedirectResponse(build_callback_url(redirect_uri, error="unsupported_response_type", state=state))

    if current_user is None:
        if prompt == "none":
            return RedirectResponse(build_callback_url(redirect_uri, error="login_required", state=state))
        return RedirectResponse(_login_redirect_url(request))

    redirect_url, reauth_reason = service.authorize(
        client_id,
        redirect_uri,
        current_user["sub"],
        state,
        scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        prompt=prompt,
        max_age=max_age,
    )
    if reauth_reason == "access_denied":
        return RedirectResponse(build_callback_url(redirect_uri, error="access_denied", state=state))
    if reauth_reason is not None:
        if prompt == "none":
            return RedirectResponse(build_callback_url(redirect_uri, error="login_required", state=state))
        return RedirectResponse(_login_redirect_url(request))
    assert redirect_url is not None  # garantizado: solo es None junto con reauth_reason
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
    prompt: str | None = Query(None),
    max_age: int | None = Query(None),
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_panel_user),
    redis: Redis = Depends(get_redis),
    audit: AuditService = Depends(get_audit_service),
):
    """Variante JSON de /authorize para el frontend SPA.

    Devuelve la URL de redirección (con el `code`) en lugar de un RedirectResponse,
    porque un SPA no puede leer el header `Location` de un redirect cross-origin.
    El frontend hace `window.location` con esta URL. Es Modo A puro: la SPA ya tiene
    sesión de panel (cookie) antes de llamar aquí (la exige, no usa la variante opcional).
    """
    await _enforce_rate_limit_audited(
        redis,
        f"minerva:rl:authorize:{request.client.host}",
        settings.RATE_LIMIT_AUTHORIZE_MAX,
        settings.RATE_LIMIT_AUTHORIZE_WINDOW,
        audit,
        request,
        "authorize_url",
    )
    # Mismo contrato que /authorize: valida el destino antes de devolver una URL de
    # error hacia él. `service.authorize` lo revalida, pero corre demasiado tarde.
    service.validate_client_and_redirect(client_id, redirect_uri)
    if response_type != "code":
        return {"redirect_url": build_callback_url(redirect_uri, error="unsupported_response_type", state=state)}

    redirect_url, reauth_reason = service.authorize(
        client_id,
        redirect_uri,
        current_user["sub"],
        state,
        scope,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        prompt=prompt,
        max_age=max_age,
    )
    if reauth_reason == "access_denied":
        return {"redirect_url": build_callback_url(redirect_uri, error="access_denied", state=state)}
    if reauth_reason is not None:
        if prompt == "none":
            return {"redirect_url": build_callback_url(redirect_uri, error="login_required", state=state)}
        # La SPA sigue esta URL igual que ya hace con la del code: reusa el mismo
        # contrato de respuesta ({"redirect_url": ...}), sin cambios en el frontend.
        return {"redirect_url": _login_redirect_url(request)}
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


async def _blacklist_jtis_then_commit(service: AuthService, redis: Redis, jtis: list[str]) -> None:
    """Fail-closed para los flujos que revocan/rotan tokens: blacklistea los access_jti en
    Redis y solo entonces confirma PostgreSQL. Si Redis falla, rollback (PG intacto) y
    propaga; si PG falla después, quedan jtis blacklisteados de más (fallo seguro).

    commit/rollback van a threadpool: son E/S síncrona de PostgreSQL y esta función se
    ejecuta en un endpoint async, con el lock de fila de la rotación aún abierto durante
    el await a Redis. Bloquear el event loop aquí impediría que otra request concurrente
    (bloqueada esperando ese mismo lock) libere el loop para completarse."""
    try:
        for jti in jtis:
            await revoke_jti(redis, jti, settings.MINERVA_ACCESS_TOKEN_TTL_MINUTES * 60)
    except Exception:
        await asyncio.to_thread(service.session.rollback)
        raise
    await asyncio.to_thread(service.session.commit)


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
        client_secret = body.get("client_secret")  # opcional: ausente en clientes públicos
        refresh_token = body.get("refresh_token")
        if not client_id or not refresh_token:
            raise BadRequestError(detail="Faltan parámetros requeridos para refrescar el token")
        # Fail-closed: la rotación (marcar rotado + emitir el nuevo refresh) queda pendiente
        # en PG; se blacklistea el access_jti viejo en Redis y solo entonces se confirma. Si
        # Redis falla, rollback → el refresh original NO queda rotado a medias (el cliente
        # reintenta limpio). En reúso, se blacklistean los jtis de la familia antes de confirmar.
        # A threadpool: el reclamo (FOR UPDATE NOWAIT + UPDATE) toma un lock de fila en PG que
        # queda abierto hasta el commit posterior a Redis; ejecutarlo síncrono sobre el event
        # loop bloquearía TODO el loop mientras espera ese lock, impidiendo que la request que
        # ya lo tiene (esperando en el await a Redis de arriba) pueda avanzar a comitear. NOWAIT
        # hace además que un contendiente concurrente falle al instante (RefreshRotationInProgressError,
        # 409, sin tocar la familia) en vez de bloquear su propio hilo del threadpool esperando
        # el lock; solo un reúso genuino de un token ya rotado revoca la familia (RefreshReuseError).
        try:
            result, revoked_jtis = await asyncio.to_thread(
                service.rotate_refresh_token, client_id, refresh_token, client_secret=client_secret, commit=False
            )
        except RefreshReuseError as reuse:
            await _blacklist_jtis_then_commit(service, redis, reuse.blacklist_jtis)
            raise
        await _blacklist_jtis_then_commit(service, redis, revoked_jtis)
        audit.log("token_refresh_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
        return result

    if grant_type != "authorization_code":
        raise BadRequestError(detail="grant_type no soportado; use authorization_code o refresh_token")

    client_id = body.get("client_id")
    client_secret = body.get("client_secret")  # opcional: ausente en clientes públicos
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")
    if not all([client_id, code, redirect_uri]):
        raise BadRequestError(detail="Faltan parámetros requeridos para el canje del código")

    result = service.exchange_token(
        client_id, code, redirect_uri, client_secret=client_secret, code_verifier=body.get("code_verifier")
    )
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
    client_secret = body.get("client_secret")  # opcional: ausente en clientes públicos
    token = body.get("token") or body.get("refresh_token")
    if not client_id or not token:
        raise BadRequestError(detail="Faltan parámetros requeridos para revocar el token")

    # Fail-closed: revoca la familia en PG (pendiente), blacklistea los access_jti en Redis
    # y solo entonces confirma (ver _blacklist_jtis_then_commit).
    revoked_jtis = service.revoke_refresh_token(client_id, token, client_secret=client_secret, commit=False)
    await _blacklist_jtis_then_commit(service, redis, revoked_jtis)
    audit.log("token_revoke", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
    return {"revoked": True}


@router.post("/refresh", response_model=PanelSessionResponse)
async def refresh_token(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_panel_user),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    # Reemite el token de sesión de la cuenta activa (480 min) y actualiza el
    # contenedor (rota sid + CSRF); las demás cuentas del navegador se conservan.
    # Autentica por la cookie de panel: un access/dev de consumidor no puede escalar (R2).
    result = service.reissue_session_token(current_user)
    return await _establish_panel_session(request, response, session, redis, result["access_token"])
