"""Flujo OIDC de consumidor sin repetir PKCE, URLs ni payloads en cada sistema."""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from minerva_sdk.config import MinervaSettings, settings


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    code_verifier: str


class MinervaOIDCError(RuntimeError):
    def __init__(self, error: str, description: str, status_code: int | None = None):
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code


class MinervaOIDC:
    """Cliente pequeño para login, refresh y logout de una aplicación web."""

    def __init__(self, config: MinervaSettings | None = None):
        self.config = config or settings

    def authorization_request(
        self,
        *,
        prompt: str | None = None,
        scope: str = "openid profile email",
    ) -> AuthorizationRequest:
        self.config.validate(login=True)
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if prompt:
            params["prompt"] = prompt
        return AuthorizationRequest(
            url=f"{self.config.issuer_url.rstrip('/')}/auth/authorize?{urlencode(params)}",
            state=state,
            code_verifier=verifier,
        )

    async def exchange_code(self, code: str, code_verifier: str) -> dict:
        return await self._post(
            "/auth/token",
            {
                "grant_type": "authorization_code",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "code": code,
                "redirect_uri": self.config.redirect_uri,
                "code_verifier": code_verifier,
            },
        )

    async def refresh(self, refresh_token: str) -> dict:
        return await self._post(
            "/auth/token",
            {
                "grant_type": "refresh_token",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "refresh_token": refresh_token,
            },
        )

    async def revoke(self, refresh_token: str) -> None:
        await self._post(
            "/auth/revoke",
            {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "token": refresh_token,
            },
        )

    async def _post(self, path: str, data: dict[str, str]) -> dict:
        self.config.validate(login=True)
        payload = {key: value for key, value in data.items() if value}
        try:
            async with httpx.AsyncClient(timeout=self.config.request_timeout) as client:
                response = await client.post(f"{self.config.issuer_url.rstrip('/')}{path}", data=payload)
        except httpx.HTTPError as exc:
            raise MinervaOIDCError("connection_error", f"No se pudo conectar con Minerva: {exc}") from exc
        if response.is_success:
            return response.json()
        try:
            body = response.json()
        except ValueError:
            body = {}
        raise MinervaOIDCError(
            body.get("error", "minerva_error"),
            body.get("error_description") or body.get("detail") or f"Minerva respondió HTTP {response.status_code}",
            response.status_code,
        )
