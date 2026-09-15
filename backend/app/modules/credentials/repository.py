from datetime import datetime, timezone
from typing import cast

from sqlalchemy import CursorResult
from sqlmodel import Session, col, select, update

from app.modules.credentials.models import CredentialToken


class CredentialTokenRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, token: CredentialToken, commit: bool = True) -> CredentialToken:
        self.session.add(token)
        self.session.commit() if commit else self.session.flush()
        return token

    def get_by_hash(self, token_hash: str) -> CredentialToken | None:
        return self.session.exec(select(CredentialToken).where(CredentialToken.token_hash == token_hash)).first()

    def invalidate_unused_for_user(self, user_id: str) -> None:
        """Da por usados los enlaces pendientes del usuario: se reemplazan por uno nuevo."""
        self.session.execute(
            update(CredentialToken)
            .where(col(CredentialToken.user_id) == user_id, col(CredentialToken.used_at).is_(None))
            .values(used_at=datetime.now(timezone.utc))
        )
        self.session.flush()

    def claim(self, token_id: str) -> bool:
        """Reclama el enlace de forma atómica (mismo patrón que `AuthCodeRepository.mark_used`).
        False si otro canje concurrente ya lo tomó. Deja el reclamo pendiente de commit."""
        result = cast(
            CursorResult,
            self.session.execute(
                update(CredentialToken)
                .where(col(CredentialToken.id) == token_id, col(CredentialToken.used_at).is_(None))
                .values(used_at=datetime.now(timezone.utc))
            ),
        )
        self.session.flush()
        return result.rowcount == 1
