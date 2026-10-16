import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

# Estados en los que se puede emitir y canjear un enlace de credencial: una cuenta inactiva o
# suspendida no fija contraseña hasta que un administrador la reactive.
LINKABLE_STATUSES = frozenset({"pending", "active"})

USER_KIND_HUMAN = "human"
# Cuenta de servicio: identidad de una aplicación confidencial para el grant
# `client_credentials`. No tiene contraseña ni sesión, solo roles en otras aplicaciones.
USER_KIND_SERVICE = "service"
# Dominio reservado (RFC 2606): un correo de cuenta de servicio nunca puede ser de una persona.
SERVICE_EMAIL_DOMAIN = "service.minerva.invalid"


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("kind IN ('human', 'service')", name="ck_users_kind"),
        CheckConstraint("kind <> 'service' OR hashed_password IS NULL", name="ck_users_service_without_password"),
        UniqueConstraint("service_application_id", name="uq_users_service_application_id"),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True, max_length=320)
    full_name: str = Field(max_length=255)
    hashed_password: str | None = Field(default=None)
    status: str = Field(default="active", max_length=20)  # active | pending | inactive | suspended
    # Obliga a fijar una contraseña propia en el próximo ingreso (p. ej. tras un reset del admin).
    password_change_required: bool = Field(default=False)
    domain: str | None = Field(default=None, max_length=255)
    kind: str = Field(default=USER_KIND_HUMAN, max_length=20)
    # Aplicación cuya cuenta de servicio es este usuario (1:1). Queda en `None` si la
    # aplicación se borra: la fila se conserva por la auditoría que la referencia.
    service_application_id: str | None = Field(default=None, foreign_key="applications.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = Field(default=None)
