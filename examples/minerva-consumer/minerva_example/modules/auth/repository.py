"""Acceso al almacén de estados OIDC y sesiones locales."""

import secrets

from fastapi import Request

from minerva_example.core import database
from minerva_example.modules.auth.consts import SESSION_COOKIE


class AuthRepository:
    def save_pending(self, state: str, verifier: str) -> None:
        database.pending[state] = verifier

    def consume_pending(self, state: str) -> str | None:
        return database.pending.pop(state, None)

    def get_session(self, request: Request) -> dict | None:
        session_id = request.cookies.get(SESSION_COOKIE)
        return database.sessions.get(session_id) if session_id else None

    def create_session(self, tokens: dict) -> str:
        session_id = secrets.token_urlsafe(32)
        database.sessions[session_id] = tokens
        return session_id

    def pop_session(self, request: Request) -> dict | None:
        session_id = request.cookies.get(SESSION_COOKIE)
        return database.sessions.pop(session_id, None) if session_id else None
