from pydantic import BaseModel, EmailStr, Field


class AuthRegister(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1)
    password: str = Field(min_length=8)


class AuthLogin(BaseModel):
    email: str
    password: str


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
    expired: bool


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
    client_id: str
    redirect_uri: str
    state: str
    scope: str = "openid profile email"
    response_type: str = "code"
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    nonce: str | None = None
