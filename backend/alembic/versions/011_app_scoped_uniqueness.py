"""Unicidad por aplicación en roles, permisos y redirect URIs (issue #76)

`roles.slug`, `permissions.slug` y `redirect_uris.uri` no tenían ningún constraint que
impidiera dos filas para la misma `(application_id, slug/uri)`: las altas por API y la
importación de manifiestos hacían "select-then-insert" (comprueban con un SELECT y
luego insertan) sin que la base lo garantizara, así que dos requests concurrentes
podían dejar duplicados.

Antes de crear cada constraint hay que conciliar los duplicados que ya existan, o no
se puede construir (mismo criterio que la migración 009): se conserva la fila más
antigua de cada grupo (`created_at`/`id` como desempate; `redirect_uris` no tiene
`created_at`, así que ordena solo por `id`) y las demás se eliminan. Los roles y
permisos duplicados tienen tablas dependientes con PK compuesta
(`role_permissions`, `user_roles`, `group_roles`): antes de repuntar sus filas a la
canónica se borran los vínculos del duplicado que ya existen en la canónica (para no
violar esa PK), y el resto se repunta. `redirect_uris` no tiene dependientes.

Revision ID: 011_app_scoped_uniqueness
Revises: 010_drop_provider_subject
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "011_app_scoped_uniqueness"
down_revision: Union[str, None] = "010_drop_provider_subject"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dedupe_roles() -> None:
    op.execute("""
        CREATE TEMP TABLE roles_ranked AS
        SELECT id, application_id, slug,
               ROW_NUMBER() OVER (PARTITION BY application_id, slug ORDER BY created_at ASC, id ASC) AS rn
        FROM roles
    """)
    op.execute("""
        CREATE TEMP TABLE roles_dedup_map AS
        SELECT dup.id AS dup_id, keep.id AS keep_id
        FROM roles_ranked dup
        JOIN roles_ranked keep ON keep.application_id = dup.application_id AND keep.slug = dup.slug AND keep.rn = 1
        WHERE dup.rn > 1
    """)

    op.execute("""
        DELETE FROM role_permissions rp USING roles_dedup_map m
        WHERE rp.role_id = m.dup_id
          AND EXISTS (
              SELECT 1 FROM role_permissions rp2
              WHERE rp2.role_id = m.keep_id AND rp2.permission_id = rp.permission_id
          )
    """)
    op.execute("UPDATE role_permissions rp SET role_id = m.keep_id FROM roles_dedup_map m WHERE rp.role_id = m.dup_id")

    op.execute("""
        DELETE FROM user_roles ur USING roles_dedup_map m
        WHERE ur.role_id = m.dup_id
          AND EXISTS (
              SELECT 1 FROM user_roles ur2
              WHERE ur2.user_id = ur.user_id AND ur2.role_id = m.keep_id
          )
    """)
    op.execute("UPDATE user_roles ur SET role_id = m.keep_id FROM roles_dedup_map m WHERE ur.role_id = m.dup_id")

    op.execute("""
        DELETE FROM group_roles gr USING roles_dedup_map m
        WHERE gr.role_id = m.dup_id
          AND EXISTS (
              SELECT 1 FROM group_roles gr2
              WHERE gr2.group_id = gr.group_id AND gr2.role_id = m.keep_id
          )
    """)
    op.execute("UPDATE group_roles gr SET role_id = m.keep_id FROM roles_dedup_map m WHERE gr.role_id = m.dup_id")

    op.execute("DELETE FROM roles r USING roles_dedup_map m WHERE r.id = m.dup_id")
    op.execute("DROP TABLE roles_dedup_map")
    op.execute("DROP TABLE roles_ranked")


def _dedupe_permissions() -> None:
    op.execute("""
        CREATE TEMP TABLE permissions_ranked AS
        SELECT id, application_id, slug,
               ROW_NUMBER() OVER (PARTITION BY application_id, slug ORDER BY created_at ASC, id ASC) AS rn
        FROM permissions
    """)
    op.execute("""
        CREATE TEMP TABLE permissions_dedup_map AS
        SELECT dup.id AS dup_id, keep.id AS keep_id
        FROM permissions_ranked dup
        JOIN permissions_ranked keep
            ON keep.application_id = dup.application_id AND keep.slug = dup.slug AND keep.rn = 1
        WHERE dup.rn > 1
    """)

    op.execute("""
        DELETE FROM role_permissions rp USING permissions_dedup_map m
        WHERE rp.permission_id = m.dup_id
          AND EXISTS (
              SELECT 1 FROM role_permissions rp2
              WHERE rp2.role_id = rp.role_id AND rp2.permission_id = m.keep_id
          )
    """)
    op.execute("""
        UPDATE role_permissions rp SET permission_id = m.keep_id
        FROM permissions_dedup_map m WHERE rp.permission_id = m.dup_id
    """)

    op.execute("DELETE FROM permissions p USING permissions_dedup_map m WHERE p.id = m.dup_id")
    op.execute("DROP TABLE permissions_dedup_map")
    op.execute("DROP TABLE permissions_ranked")


def _dedupe_redirect_uris() -> None:
    op.execute("""
        CREATE TEMP TABLE redirect_uris_ranked AS
        SELECT id, application_id, uri,
               ROW_NUMBER() OVER (PARTITION BY application_id, uri ORDER BY id ASC) AS rn
        FROM redirect_uris
    """)
    op.execute("DELETE FROM redirect_uris WHERE id IN (SELECT id FROM redirect_uris_ranked WHERE rn > 1)")
    op.execute("DROP TABLE redirect_uris_ranked")


def upgrade() -> None:
    _dedupe_roles()
    _dedupe_permissions()
    _dedupe_redirect_uris()

    op.create_unique_constraint("uq_roles_application_id_slug", "roles", ["application_id", "slug"])
    op.create_unique_constraint("uq_permissions_application_id_slug", "permissions", ["application_id", "slug"])
    op.create_unique_constraint("uq_redirect_uris_application_id_uri", "redirect_uris", ["application_id", "uri"])


def downgrade() -> None:
    op.drop_constraint("uq_redirect_uris_application_id_uri", "redirect_uris", type_="unique")
    op.drop_constraint("uq_permissions_application_id_slug", "permissions", type_="unique")
    op.drop_constraint("uq_roles_application_id_slug", "roles", type_="unique")
    # Los duplicados conciliados en el upgrade no se pueden restaurar.
