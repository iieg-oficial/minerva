from pydantic import BaseModel


class AuthRegister(BaseModel):
    email: str
    full_name: str
    password: str


class AuthLogin(BaseModel):
    email: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


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
