"""Casos de uso OIDC y reglas de sesión local."""

from fastapi import HTTPException, Request, status
from minerva_sdk import MinervaOIDC

from minerva_example.modules.auth.repository import AuthRepository


class AuthService:
    def __init__(self):
        self.repository = AuthRepository()
        self.oidc = MinervaOIDC()

    def begin_login(self, prompt: str | None):
        authorization = self.oidc.authorization_request(prompt=prompt)
        self.repository.save_pending(authorization.state, authorization.code_verifier)
        return authorization

    def consume_verifier(self, cookie_state: str | None, state: str) -> str | None:
        if cookie_state != state:
            return None
        return self.repository.consume_pending(state)

    def get_session(self, request: Request) -> dict | None:
        return self.repository.get_session(request)

    def require_access_token(self, request: Request) -> str:
        session = self.get_session(request)
        if not session or not session.get("access_token"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión con Minerva")
        return session["access_token"]

    async def exchange_code(self, code: str, verifier: str) -> dict:
        return await self.oidc.exchange_code(code, verifier)

    def create_session(self, tokens: dict) -> str:
        return self.repository.create_session(tokens)

    async def refresh(self, session: dict) -> None:
        session.update(await self.oidc.refresh(session["refresh_token"]))

    async def logout(self, request: Request) -> None:
        session = self.repository.pop_session(request)
        if session and session.get("refresh_token"):
            await self.oidc.revoke(session["refresh_token"])


auth_service = AuthService()
