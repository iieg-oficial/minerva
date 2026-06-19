"""Manifest imports table (Minerva Dev Kit)

Revision ID: 002_manifest_imports
Revises: 001_initial
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "002_manifest_imports"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manifest_imports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("application_id", sa.String(), nullable=True),
        sa.Column("application_code", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("permissions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("roles_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manifest_imports_application_id", "manifest_imports", ["application_id"])
    op.create_index("ix_manifest_imports_application_code", "manifest_imports", ["application_code"])


def downgrade() -> None:
    op.drop_index("ix_manifest_imports_application_code", table_name="manifest_imports")
    op.drop_index("ix_manifest_imports_application_id", table_name="manifest_imports")
    op.drop_table("manifest_imports")
