"""Branding por aplicación en la pantalla de login (issue #12)

Revision ID: 006_application_branding
Revises: 005_refresh_tokens
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "006_application_branding"
down_revision: Union[str, None] = "005_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("applications", sa.Column("logo_url", sa.String(length=2048), nullable=True))
    op.add_column("applications", sa.Column("brand_color", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "brand_color")
    op.drop_column("applications", "logo_url")
    op.drop_column("applications", "display_name")
