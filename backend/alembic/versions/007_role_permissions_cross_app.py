"""Borra vinculos rol-permiso cruzados entre aplicaciones (issue #38)

Revision ID: 007_role_permissions_cross_app
Revises: 006_application_branding
Create Date: 2026-07-20
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007_role_permissions_cross_app"
down_revision: Union[str, None] = "006_application_branding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
        WHERE EXISTS (
            SELECT 1 FROM roles r, permissions p
            WHERE r.id = role_permissions.role_id
              AND p.id = role_permissions.permission_id
              AND r.application_id <> p.application_id
        )
    """)


def downgrade() -> None:
    # No-op: no se pueden restaurar los vinculos borrados.
    pass
