import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.modules.auth.models import AuthCode


class AuthCodeRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_code(self, client_id: str, user_id: str, redirect_uri: str, scope: str | None = None) -> AuthCode:
        code = str(uuid.uuid4())
        auth_code = AuthCode(
            code=code,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scope=scope,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        self.session.add(auth_code)
        self.session.commit()
        return auth_code

    def get_by_code(self, code: str) -> AuthCode | None:
        statement = select(AuthCode).where(AuthCode.code == code, AuthCode.used.is_(False))
        return self.session.exec(statement).first()

    def mark_used(self, auth_code: AuthCode) -> None:
        auth_code.used = True
        self.session.add(auth_code)
        self.session.commit()
