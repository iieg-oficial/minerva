"""Cuentas de servicio para el grant client_credentials

`users.kind` distingue a las personas (`human`) de las cuentas de servicio (`service`):
la identidad de una aplicación confidencial que pide tokens máquina a máquina.
`users.service_application_id` liga cada cuenta de servicio con su aplicación (1:1).
Una cuenta de servicio nunca tiene contraseña.

Revision ID: 014_service_principals
Revises: 013_credential_destination
Create Date: 2026-10-16
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "014_service_principals"
down_revision: Union[str, None] = "013_credential_destination"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("kind", sa.String(length=20), nullable=False, server_default=sa.text("'human'")))
    op.add_column(
        "users",
        sa.Column("service_application_id", sa.String(), sa.ForeignKey("applications.id"), nullable=True),
    )
    op.create_unique_constraint("uq_users_service_application_id", "users", ["service_application_id"])
    op.create_check_constraint("ck_users_kind", "users", "kind IN ('human', 'service')")
    op.create_check_constraint(
        "ck_users_service_without_password", "users", "kind <> 'service' OR hashed_password IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_service_without_password", "users", type_="check")
    op.drop_constraint("ck_users_kind", "users", type_="check")
    op.drop_constraint("uq_users_service_application_id", "users", type_="unique")
    op.drop_column("users", "service_application_id")
    op.drop_column("users", "kind")
