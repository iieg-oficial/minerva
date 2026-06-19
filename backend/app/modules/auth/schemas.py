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


class AuthorizeQuery(BaseModel):
    client_id: str
    redirect_uri: str
    state: str
    scope: str = "openid profile email"
    response_type: str = "code"
