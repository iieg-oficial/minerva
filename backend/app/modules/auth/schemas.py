from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.shared.validators import NewPassword, validate_password_max_bytes


class AuthRegister(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=6, max_length=255)
    password: Annotated[str, Field(min_length=8), AfterValidator(validate_password_max_bytes)]


class AuthLogin(BaseModel):
    email: str
    password: Annotated[str, AfterValidator(validate_password_max_bytes)]


class PasswordChange(BaseModel):
    current_password: Annotated[str, AfterValidator(validate_password_max_bytes)]
    new_password: NewPassword


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    id_token: str | None = None  # OIDC: identidad del usuario (solo con scope openid)
    scope: str | None = None
    refresh_token: str | None = None  # se rota en cada uso (RFC 6749 §10.4)


# --- Sesión del panel (BFF) ------------------------------------------------
# El panel ya no recibe el JWT: solo descriptores no sensibles + el token CSRF.
class AccountDescriptor(BaseModel):
    sub: str
    email: str
    name: str
    is_admin: bool
    exp: int
    # Sin sesión viva (vencida o cerrada): volver a ella pide contraseña.
    expired: bool
    # Se cerró con «Cerrar sesión»: sigue en el selector, pero su token ya se revocó.
    signed_out: bool = False


class PanelSessionResponse(BaseModel):
    """Respuesta de login/register/refresh del panel: la cuenta activa y el token
    CSRF. El sid opaco viaja en la cookie HttpOnly, nunca en el cuerpo."""

    active: AccountDescriptor | None
    csrf: str


class SessionView(BaseModel):
    """Estado del selector multi-cuenta: cuentas del navegador + activa + CSRF."""

    accounts: list[AccountDescriptor]
    active: AccountDescriptor | None
    csrf: str


class SetActiveRequest(BaseModel):
    sub: str


class TokenExchange(BaseModel):
    client_id: str
    client_secret: str
    code: str
    redirect_uri: str
    code_verifier: str | None = None  # PKCE (RFC 7636)


class AuthorizeQuery(BaseModel):
    """Parámetros del Authorization Endpoint. Los comparten los tres handlers: el GET,
    el POST form (OIDC Core 3.1.2.1) y la variante JSON que consume el panel."""

    client_id: str
    redirect_uri: str
    state: str
    scope: str = "openid profile email"
    response_type: str = "code"
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    nonce: str | None = None
    prompt: str | None = None
    max_age: int | None = None
