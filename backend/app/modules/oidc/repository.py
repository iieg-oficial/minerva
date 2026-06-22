from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.oidc.models import SigningKey


class SigningKeyRepository:
    """Acceso a datos de las claves de firma."""

    def __init__(self, session: Session):
        self.session = session

    def get_active(self) -> SigningKey | None:
        return self.session.exec(select(SigningKey).where(SigningKey.status == "active")).first()

    def get_by_kid(self, kid: str) -> SigningKey | None:
        return self.session.exec(select(SigningKey).where(SigningKey.kid == kid)).first()

    def list_publishable(self) -> list[SigningKey]:
        """Claves que deben publicarse en el JWKS: la activa y las retiradas.

        Las retiradas se mantienen mientras puedan existir tokens vigentes firmados
        con ellas; su purga definitiva es responsabilidad de la rotación.
        """
        return list(self.session.exec(select(SigningKey).where(SigningKey.status.in_(["active", "retired"]))).all())

    def create(self, key: SigningKey) -> SigningKey:
        self.session.add(key)
        self.session.commit()
        self.session.refresh(key)
        return key

    def mark_retired(self, key: SigningKey) -> SigningKey:
        key.status = "retired"
        key.rotated_at = datetime.now(timezone.utc)
        self.session.add(key)
        self.session.commit()
        self.session.refresh(key)
        return key

    def purge_retired_before(self, cutoff: datetime) -> int:
        """Borra claves retiradas cuya rotación ocurrió antes de `cutoff`. Solo se
        deben purgar una vez pasada la ventana de solapamiento (vida máxima de un
        access/id token firmado con esa clave) para no invalidar tokens vigentes."""
        keys = self.session.exec(
            select(SigningKey).where(SigningKey.status == "retired", SigningKey.rotated_at < cutoff)
        ).all()
        for key in keys:
            self.session.delete(key)
        self.session.commit()
        return len(keys)
