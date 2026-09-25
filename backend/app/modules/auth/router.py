import asyncio
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import parse_qs, quote, urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
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
from app.core.exceptions import (
    AppException,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
)
from app.core.rate_limit import enforce_rate_limit
from app.core.redis import get_redis
from app.core.token_blacklist import revoke_jti
from app.modules.audit.service import AuditService
from app.modules.auth import login_throttle
from app.modules.auth.schemas import (
    AccountDescriptor,
    AuthLogin,
    AuthorizeQuery,
    AuthRegister,
    AuthTokenResponse,
    PanelSessionResponse,
    PasswordChange,
    SessionView,
    SetActiveRequest,
)
from app.modules.auth.service import (
    AuthService,
    PasswordChangeRequired,
    RefreshReuseError,
    build_callback_url,
    session_auth_time,
)
from app.modules.authorization.service import AuthorizationService
from app.modules.credentials.schemas import CredentialInspection, CredentialSet, CredentialTokenIn
from app.modules.credentials.service import CredentialService
from app.modules.users.invalidation import apply_with_invalidation
from app.modules.users.service import UserService

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
        _audit_rate_limit(audit, request, {"endpoint": endpoint})
        raise


def _audit_rate_limit(audit: AuditService, request: Request, metadata: dict) -> None:
    audit.log(
        "rate_limit_exceeded",
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        event_metadata=metadata,
    )


def _login_redirect_url(query: str) -> str:
    """URL de login con `next=` apuntando al `/authorize` original. Reutiliza el
    patrón `next=` que ya soporta el frontend (`LoginPage.jsx`/`AuthorizePage.jsx`)
    para retomar el flujo tras autenticar — sin sesión nueva en Redis.

    `query` se recibe en vez de leerse del `Request` porque en el POST form la query
    string está vacía: los parámetros vienen en el cuerpo y hay que re-serializarlos."""
    next_path = f"/authorize?{query}"
    return f"{settings.FRONTEND_URL}/login?next={quote(next_path, safe='')}"


def _account_selector_url(query: str) -> str:
    return f"{settings.FRONTEND_URL}/authorize?{query}"


def get_auth_service(session: Session = Depends(get_db)) -> AuthService:
    return AuthService(session)


def get_audit_service(session: Session = Depends(get_db)) -> AuditService:
    return AuditService(session)


def get_credential_service(session: Session = Depends(get_db)) -> CredentialService:
    return CredentialService(session)


def get_user_service(session: Session = Depends(get_db)) -> UserService:
    return UserService(session)


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
    # Dos niveles: por IP (umbral alto, ver RATE_LIMIT_LOGIN_IP_MAX en config) y por cuenta,
    # que es el que frena la fuerza bruta aunque todos compartan IP detrás del WAF.
    await _enforce_rate_limit_audited(
        redis,
        f"minerva:rl:login:{request.client.host}",
        settings.RATE_LIMIT_LOGIN_IP_MAX,
        settings.RATE_LIMIT_LOGIN_IP_WINDOW,
        audit,
        request,
        "login",
    )
    try:
        await login_throttle.enforce(redis, data.email)
    except TooManyRequestsError:
        _audit_rate_limit(audit, request, {"endpoint": "login_account", "email": data.email})
        raise
    try:
        result = service.login(data.email, data.password)
    except PasswordChangeRequired as exc:
        # La contraseña fue correcta: el contador de la cuenta se limpia igual que en un éxito.
        await login_throttle.clear(redis, data.email)
        audit.log(
            "manual_login_password_change_required",
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            event_metadata={"email": data.email},
        )
        # Sin cookie ni sesión: la SPA lleva a /activar con este token para fijar la nueva.
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Debes cambiar tu contraseña antes de continuar",
                "code": "password_change_required",
                "credential_token": exc.credential_token,
            },
        )
    except Exception as exc:
        # Solo los rechazos del dominio (credenciales, cuenta inactiva) suman al contador de
        # la cuenta; una falla de infraestructura no es un intento contra la contraseña.
        if isinstance(exc, AppException):
            await login_throttle.record(redis, data.email)
        audit.log(
            "manual_login_failed",
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            event_metadata={"email": data.email},
        )
        raise
    await login_throttle.clear(redis, data.email)
    audit.log("manual_login_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent"))
    return await _establish_panel_session(request, response, session, redis, result["access_token"])


@router.get("/session", response_model=SessionView)
async def get_session(ps: dict = Depends(get_panel_session)):
    """Estado del selector multi-cuenta (cuentas del navegador + activa + CSRF). Fuente
    de verdad del selector: el navegador ya no guarda tokens. Tolera no tener cuenta
    activa (tras cerrar sesión) para poder seguir pintando el selector."""
    return panel_session.session_view(ps["container"])


async def _account_session_alive(session: Session, redis: Redis, account: dict) -> bool:
    """Si el token guardado de una cuenta sigue valiendo: no vencido, no revocado y sin
    corte por usuario (cambio de contraseña, status). Mismo criterio que el panel."""
    if not panel_session.has_live_token(account):
        return False
    try:
        await _resolve_token(account["token"], session, redis, expected_types={"session"}, audience="minerva")
    except ValueError:
        return False
    return True


@router.post("/session/active", response_model=AccountDescriptor)
async def set_active_account(
    data: SetActiveRequest,
    ps: dict = Depends(get_panel_session),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Cambia la cuenta activa del navegador sin pedir contraseña, solo si la sesión de esa
    cuenta sigue viva (multi-cuenta). Una cuenta cerrada con «Cerrar sesión», vencida o
    invalidada responde 409: la SPA pide la contraseña y entra por `/auth/login`."""
    container = ps["container"]
    account = container["accounts"].get(data.sub)
    if account is None:
        raise NotFoundError(detail="La cuenta no está iniciada en este navegador")
    if not await _account_session_alive(session, redis, account):
        # Se descarta el token muerto para que el selector la muestre como cerrada.
        panel_session.sign_out(container, data.sub)
        await panel_session.write(redis, ps["sid"], container)
        raise ConflictError(detail="La sesión de esta cuenta está cerrada; ingresa tu contraseña para continuar")
    panel_session.set_active(container, data.sub)
    await panel_session.write(redis, ps["sid"], container)
    return panel_session.descriptor(data.sub, container["accounts"][data.sub])


@router.post("/logout")
async def logout(
    request: Request,
    ps: dict = Depends(get_panel_session),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
):
    """Cierra la sesión de la cuenta activa y revoca su token (blacklist del `jti`). La
    cuenta sigue en el selector para reingresar sin teclear el correo, pero volver a ella
    pide contraseña: en un equipo compartido, quien llega después no entra como la persona
    anterior. Las demás cuentas del navegador no se tocan y siguen activables."""
    container = ps["container"]
    active = container.get("active")
    if active:
        await _revoke_account_token(redis, panel_session.sign_out(container, active))
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


async def _enforce_credential_rate_limit(redis: Redis, audit: AuditService, request: Request) -> None:
    await _enforce_rate_limit_audited(
        redis,
        f"minerva:rl:credential:{request.client.host}",
        settings.RATE_LIMIT_CREDENTIAL_MAX,
        settings.RATE_LIMIT_CREDENTIAL_WINDOW,
        audit,
        request,
        "credential",
    )


@router.post("/credential/inspect", response_model=CredentialInspection)
async def inspect_credential(
    data: CredentialTokenIn,
    request: Request,
    credentials: CredentialService = Depends(get_credential_service),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
):
    """Valida un enlace de credencial antes de pedir la contraseña: para qué es y de quién
    (correo enmascarado). Es POST y no GET para que el token no quede en logs de acceso."""
    await _enforce_credential_rate_limit(redis, audit, request)
    return credentials.inspect(data.token)


@router.post("/credential")
async def set_credential(
    data: CredentialSet,
    request: Request,
    credentials: CredentialService = Depends(get_credential_service),
    audit: AuditService = Depends(get_audit_service),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Fija la contraseña con un enlace de un solo uso (invitación, restablecimiento o cambio
    obligatorio). Exento de CSRF: la prueba es el token del enlace, no la sesión. Invalida
    las sesiones previas del usuario; para entrar, se inicia sesión con la contraseña nueva."""
    await _enforce_credential_rate_limit(redis, audit, request)
    token = credentials.consume(data.token, data.password, commit=False)
    audit.log(
        "credential_set",
        actor_user_id=token.user_id,
        target_type="user",
        target_id=token.user_id,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        event_metadata={"purpose": token.purpose},
        commit=False,
    )
    await apply_with_invalidation(session, redis, token.user_id)
    return {"message": "Contraseña establecida"}


@router.post("/password")
async def change_password(
    data: PasswordChange,
    request: Request,
    users: UserService = Depends(get_user_service),
    audit: AuditService = Depends(get_audit_service),
    current_user: dict = Depends(get_current_panel_user),
    ps: dict = Depends(get_panel_session),
    session: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Cambio de contraseña del propio usuario (exige la actual). Invalida todas sus sesiones
    y refresh tokens —también la de este navegador— y saca su cuenta del contenedor: se
    vuelve a entrar con la contraseña nueva. Las demás cuentas del navegador no se tocan."""
    sub = current_user["sub"]
    await _enforce_rate_limit_audited(
        redis,
        f"minerva:rl:password:{sub}",
        settings.RATE_LIMIT_LOGIN_MAX,
        settings.RATE_LIMIT_LOGIN_WINDOW,
        audit,
        request,
        "password",
    )
    users.change_own_password(sub, data.current_password, data.new_password, commit=False)
    audit.log(
        "password_change_self",
        actor_user_id=sub,
        target_type="user",
        target_id=sub,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        commit=False,
    )
    await apply_with_invalidation(session, redis, sub)
    container = ps["container"]
    panel_session.remove_account(container, sub)
    await panel_session.write(redis, ps["sid"], container)
    return {"message": "Contraseña actualizada; inicia sesión de nuevo"}


@router.get("/me")
def me(
    service: AuthService = Depends(get_auth_service),
    current_user: dict = Depends(get_current_panel_user),
):
    return service.get_me(current_user["sub"])


async def _authorize_target_url(
    request: Request,
    params: AuthorizeQuery,
    service: AuthService,
    current_user: dict | None,
    redis: Redis,
    audit: AuditService,
    *,
    endpoint: str,
    login_query: str,
) -> str:
    """Flujo del Authorization Endpoint, compartido por los tres handlers (GET, POST
    form y la variante JSON del panel). Devuelve la URL a la que hay que mandar al
    navegador —el callback con `code`, el callback con `error=` o el login— y cada
    handler decide si la envuelve en un redirect o en JSON.

    `endpoint` es solo la etiqueta de rate limit/auditoría; `login_query` es lo que se
    reinyecta en el `next=` cuando hay que pasar por el login."""
    await _enforce_rate_limit_audited(
        redis,
        f"minerva:rl:authorize:{request.client.host}",
        settings.RATE_LIMIT_AUTHORIZE_MAX,
        settings.RATE_LIMIT_AUTHORIZE_WINDOW,
        audit,
        request,
        endpoint,
    )
    # Valida client_id/redirect_uri ANTES de cualquier redirect (incluso sin
    # sesión): nunca se redirige a un destino no confiable (evita open redirect).
    service.validate_client_and_redirect(params.client_id, params.redirect_uri)

    # Solo se soporta el flujo de código (lo que ya declara el discovery). El error
    # vuelve al cliente por redirect, no como 400: para eso el destino se validó arriba.
    if params.response_type != "code":
        return build_callback_url(params.redirect_uri, error="unsupported_response_type", state=params.state)

    if params.prompt == "select_account":
        return _account_selector_url(login_query)

    if current_user is None:
        if params.prompt == "none":
            return build_callback_url(params.redirect_uri, error="login_required", state=params.state)
        return _login_redirect_url(login_query)

    redirect_url, reauth_reason = service.authorize(
        params.client_id,
        params.redirect_uri,
        current_user["sub"],
        params.state,
        params.scope,
        code_challenge=params.code_challenge,
        code_challenge_method=params.code_challenge_method,
        nonce=params.nonce,
        prompt=params.prompt,
        max_age=params.max_age,
        auth_time=session_auth_time(current_user),
    )
    if reauth_reason == "access_denied":
        return build_callback_url(params.redirect_uri, error="access_denied", state=params.state)
    if reauth_reason is not None:
        if params.prompt == "none":
            return build_callback_url(params.redirect_uri, error="login_required", state=params.state)
        return _login_redirect_url(login_query)
    assert redirect_url is not None  # garantizado: solo es None junto con reauth_reason
    return redirect_url


@router.get("/authorize")
async def authorize(
    request: Request,
    params: Annotated[AuthorizeQuery, Query()],
    service: AuthService = Depends(get_auth_service),
    current_user: dict | None = Depends(get_optional_panel_user),
    redis: Redis = Depends(get_redis),
    audit: AuditService = Depends(get_audit_service),
):
    """Inicia el flujo `/authorize`. Modo A: la cookie de sesión del panel viaja en
    la navegación directa (SameSite=Lax) y resuelve la cuenta activa. Modo B: un
    sistema externo redirige aquí el navegador sin sesión — se redirige a login y se
    retoma con `?next=` tras autenticar (mismo patrón que ya usa `AuthorizePage.jsx`)."""
    url = await _authorize_target_url(
        request, params, service, current_user, redis, audit, endpoint="authorize", login_query=request.url.query
    )
    return RedirectResponse(url)


@router.post("/authorize")
async def authorize_post(
    request: Request,
    service: AuthService = Depends(get_auth_service),
    current_user: dict | None = Depends(get_optional_panel_user),
    redis: Redis = Depends(get_redis),
    audit: AuditService = Depends(get_audit_service),
):
    """Mismo Authorization Endpoint por POST `form-urlencoded`: OIDC Core 3.1.2.1 lo
    exige junto al GET. Los parámetros viajan en el cuerpo y siguen exactamente el
    mismo camino; lo único propio del POST es de dónde salen.

    Se responde **303** (no el 307 por defecto del GET) para que el navegador siga el
    callback con GET en vez de re-enviar el POST al consumidor.

    Nota operativa: la cookie de panel es `SameSite=Lax`, así que un POST cross-site
    —el caso real de un consumidor— **no la lleva** y el usuario pasa por el login con
    `next=`, aunque tenga sesión abierta. Por eso el `next=` se arma con los parámetros
    del form: la query string de un POST está vacía."""
    form = await _read_form_body(request)
    try:
        params = AuthorizeQuery(**form)
    except ValidationError as exc:
        # Mismo 422 y mismo cuerpo que devuelve FastAPI cuando al GET le falta un parámetro.
        raise RequestValidationError(exc.errors()) from exc
    url = await _authorize_target_url(
        request, params, service, current_user, redis, audit, endpoint="authorize", login_query=urlencode(form)
    )
    return RedirectResponse(url, status_code=303)


@router.get("/authorize/url")
async def authorize_url(
    request: Request,
    params: Annotated[AuthorizeQuery, Query()],
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
    La SPA sigue la URL de login igual que la del `code`: mismo contrato de respuesta.
    """
    url = await _authorize_target_url(
        request, params, service, current_user, redis, audit, endpoint="authorize_url", login_query=request.url.query
    )
    return {"redirect_url": url}


async def _read_form_body(request: Request) -> dict:
    """Lee el cuerpo de los endpoints OIDC que reciben `form-urlencoded` (`/authorize`
    por POST, `/token`, `/revoke`), aceptando también el JSON legacy que ya usaba el
    frontend. El form-urlencoded se parsea a mano para no depender de python-multipart."""
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


def _oauth_error_response(exc: AppException) -> JSONResponse:
    """Contrato de error OAuth de /auth/token (RFC 6749 §5.2, issue #78): siempre 400
    (aquí el cliente nunca se autentica vía header Authorization, así que el 401
    opcional de invalid_client no aplica). `detail` se conserva junto a
    `error`/`error_description` para no romper a quien ya parseaba solo `detail`."""
    return JSONResponse(
        status_code=400,
        content={"error": exc.oauth_error, "error_description": exc.detail, "detail": exc.detail},
    )


@router.post("/token", response_model=AuthTokenResponse)
async def token_exchange(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    audit: AuditService = Depends(get_audit_service),
    redis: Redis = Depends(get_redis),
):
    body = await _read_form_body(request)
    grant_type = body.get("grant_type", "authorization_code")

    try:
        if grant_type == "refresh_token":
            client_id = body.get("client_id")
            client_secret = body.get("client_secret")  # opcional: ausente en clientes públicos
            refresh_token = body.get("refresh_token")
            if not client_id or not refresh_token:
                raise BadRequestError(
                    detail="Faltan parámetros requeridos para refrescar el token", oauth_error="invalid_request"
                )
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
            audit.log(
                "token_refresh_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent")
            )
        elif grant_type == "authorization_code":
            client_id = body.get("client_id")
            client_secret = body.get("client_secret")  # opcional: ausente en clientes públicos
            code = body.get("code")
            redirect_uri = body.get("redirect_uri")
            if not all([client_id, code, redirect_uri]):
                raise BadRequestError(
                    detail="Faltan parámetros requeridos para el canje del código", oauth_error="invalid_request"
                )
            result = service.exchange_token(
                client_id, code, redirect_uri, client_secret=client_secret, code_verifier=body.get("code_verifier")
            )
            audit.log(
                "token_exchange_success", ip_address=request.client.host, user_agent=request.headers.get("user-agent")
            )
        else:
            raise BadRequestError(
                detail="grant_type no soportado; use authorization_code o refresh_token",
                oauth_error="unsupported_grant_type",
            )
    except AppException as exc:
        if exc.oauth_error is None:
            raise
        return _oauth_error_response(exc)

    # RFC 6749 §5.1: toda respuesta exitosa del token endpoint lleva tokens y no debe
    # cachearse (issue #79). Un solo punto para ambos grants, tras converger aquí.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
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
    body = await _read_form_body(request)
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
