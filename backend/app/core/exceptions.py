from fastapi import HTTPException, status

BEARER_REALM: str = "minerva"
# Contrato público: fijas (no derivadas del `detail`), sin revelar la causa y sin acentos (header ASCII).
BEARER_ERROR_DESCRIPTIONS: dict[str, str] = {
    "invalid_token": "El token de acceso es invalido, expiro o fue revocado",
    "insufficient_scope": "El token no esta autorizado para el recurso solicitado",
}


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
        oauth_error: str | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        # Código OAuth (RFC 6749 §5.2, p. ej. "invalid_grant"): opcional, solo lo usa
        # el handler de /auth/token (issue #78) para armar `error`/`error_description`
        # sin cambiar el `status_code`/clase que ya usa el resto del backend.
        self.oauth_error = oauth_error


class NotFoundError(AppException):
    def __init__(self, detail: str = "Recurso no encontrado", oauth_error: str | None = None):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail, oauth_error=oauth_error)


class UnauthorizedError(AppException):
    def __init__(
        self,
        detail: str = "No autenticado",
        oauth_error: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers=headers, oauth_error=oauth_error
        )


class ForbiddenError(AppException):
    def __init__(
        self,
        detail: str = "Acceso denegado",
        oauth_error: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail, headers=headers, oauth_error=oauth_error)


class BearerUnauthorizedError(UnauthorizedError):
    """401 de un endpoint que autentica por Bearer. Siempre emite challenge: sin
    `error` cuando no vino credencial, con `invalid_token` cuando vino y no sirve.
    Los 401 de la sesión por cookie del panel usan `UnauthorizedError` a secas."""

    def __init__(self, detail: str, error: str | None = None):
        super().__init__(detail=detail, headers=bearer_challenge(error))


class InsufficientScopeError(ForbiddenError):
    """403 de un endpoint Bearer: la credencial es válida pero no alcanza para el
    recurso. `required_scope` es el alcance que el cliente debería obtener."""

    def __init__(self, detail: str, required_scope: str | None = None):
        super().__init__(detail=detail, headers=bearer_challenge("insufficient_scope", scope=required_scope))


class BadRequestError(AppException):
    def __init__(self, detail: str = "Solicitud inválida", oauth_error: str | None = None):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail, oauth_error=oauth_error)


class ConflictError(AppException):
    def __init__(self, detail: str = "Conflicto", oauth_error: str | None = None):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail, oauth_error=oauth_error)


class TooManyRequestsError(AppException):
    def __init__(self, detail: str = "Demasiadas solicitudes. Intente más tarde.", retry_after: int | None = None):
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, headers=headers)


def bearer_challenge(error: str | None = None, scope: str | None = None) -> dict[str, str]:
    """Arma el header `WWW-Authenticate` del esquema Bearer (RFC 6750 §3).

    Sin credencial no se emite código de error (el cliente solo sabe que hace falta
    autenticarse); con credencial inválida o insuficiente sí. `scope` nombra el
    alcance requerido, que RFC 6750 §3.1 pide incluir en `insufficient_scope`.

    No lo llames directo: usa `BearerUnauthorizedError` / `InsufficientScopeError`,
    que garantizan que ningún error Bearer salga sin challenge.
    """
    params = [f'realm="{BEARER_REALM}"']
    if error is not None:
        params.append(f'error="{error}"')
        params.append(f'error_description="{BEARER_ERROR_DESCRIPTIONS[error]}"')
    if scope is not None:
        params.append(f'scope="{scope}"')
    return {"WWW-Authenticate": "Bearer " + ", ".join(params)}
