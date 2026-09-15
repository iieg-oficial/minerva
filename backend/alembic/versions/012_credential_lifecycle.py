"""Ciclo de vida de la credencial: enlaces de un solo uso y cambio obligatorio

`credential_tokens` guarda, hasheados, los enlaces con los que una persona fija su
contraseña: invitación (alta sin credencial), restablecimiento y cambio obligatorio.
`users.password_change_required` obliga a cambiarla en el próximo ingreso.

Revision ID: 012_credential_lifecycle
Revises: 011_app_scoped_uniqueness
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "012_credential_lifecycle"
down_revision: Union[str, None] = "011_app_scoped_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("password_change_required", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_table(
        "credential_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credential_tokens_token_hash", "credential_tokens", ["token_hash"], unique=True)
    op.create_index("ix_credential_tokens_user_id", "credential_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_credential_tokens_user_id", table_name="credential_tokens")
    op.drop_index("ix_credential_tokens_token_hash", table_name="credential_tokens")
    op.drop_table("credential_tokens")
    op.drop_column("users", "password_change_required")
