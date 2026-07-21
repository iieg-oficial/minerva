from datetime import datetime, timezone

from sqlmodel import Session, col, select, update

from app.modules.oidc.models import SigningKey


class SigningKeyRepository:
    """Acceso a datos de las claves de firma."""

    def __init__(self, session: Session):
        self.session = session

    def get_active(self) -> SigningKey | None:
        """La clave que firma. El `ORDER BY` es determinismo defensivo: la promoción
        es atómica y nunca debe dejar dos activas, pero si alguna vez las hubiera,
        firmar con la más nueva es preferible a que dependa del plan del query."""
        statement = select(SigningKey).where(SigningKey.status == "active").order_by(col(SigningKey.created_at).desc())
        return self.session.exec(statement).first()

    def get_pending(self) -> SigningKey | None:
        """La clave publicada pero que aún no firma (publish-before-use)."""
        statement = select(SigningKey).where(SigningKey.status == "pending").order_by(col(SigningKey.created_at).desc())
        return self.session.exec(statement).first()

    def get_by_kid(self, kid: str) -> SigningKey | None:
        return self.session.exec(select(SigningKey).where(SigningKey.kid == kid)).first()

    def list_publishable(self) -> list[SigningKey]:
        """Claves que deben publicarse en el JWKS: la pendiente, la activa y las retiradas.

        La `pending` se publica ANTES de firmar con ella, para que los verificadores la
        tengan en su caché cuando empiece a usarse (publish-before-use). Las retiradas
        se mantienen mientras puedan existir tokens vigentes firmados con ellas; su purga
        definitiva es responsabilidad de la rotación.
        """
        statement = select(SigningKey).where(col(SigningKey.status).in_(["pending", "active", "retired"]))
        return list(self.session.exec(statement).all())

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

    def promote(self, pending: SigningKey) -> bool:
        """Activa la clave pendiente y retira la anterior en UNA sola transacción.

        Retirar antes de promover, sin commit intermedio, evita las dos ventanas malas:
        ningún lector ve dos claves activas ni se queda sin ninguna (el `mark_retired`
        + `create` que se hacía antes sí dejaba ese hueco). El UPDATE de la pendiente es
        condicional: si otra promoción concurrente ya la reclamó, afecta 0 filas y esta
        devuelve False sin haber retirado nada, porque el rollback deshace ambos.
        """
        self.session.execute(
            update(SigningKey)
            .where(col(SigningKey.status) == "active")
            .values(status="retired", rotated_at=datetime.now(timezone.utc))
        )
        claimed = self.session.execute(
            update(SigningKey)
            .where(col(SigningKey.id) == pending.id, col(SigningKey.status) == "pending")
            .values(status="active")
        )
        if claimed.rowcount != 1:
            self.session.rollback()
            return False
        self.session.commit()
        return True

    def purge_retired_before(self, cutoff: datetime) -> int:
        """Borra claves retiradas cuya rotación ocurrió antes de `cutoff`. Solo se
        deben purgar una vez pasada la ventana de solapamiento (vida máxima de un
        access/id token firmado con esa clave) para no invalidar tokens vigentes."""
        keys = self.session.exec(
            select(SigningKey).where(col(SigningKey.status) == "retired", col(SigningKey.rotated_at) < cutoff)
        ).all()
        for key in keys:
            self.session.delete(key)
        self.session.commit()
        return len(keys)
