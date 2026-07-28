from fastapi import HTTPException, status


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
    def __init__(self, detail: str = "No autenticado", oauth_error: str | None = None):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, oauth_error=oauth_error)


class ForbiddenError(AppException):
    def __init__(self, detail: str = "Acceso denegado", oauth_error: str | None = None):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail, oauth_error=oauth_error)


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
