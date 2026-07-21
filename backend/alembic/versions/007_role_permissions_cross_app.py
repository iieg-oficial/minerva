"""Borra vinculos rol-permiso cruzados entre aplicaciones y los bloquea a futuro (issue #38)

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

    # Un CHECK no puede consultar otras tablas; un trigger es el mecanismo minimo para
    # que PostgreSQL rechace por si solo los vinculos cruzados que el service ya valida
    # (defensa en profundidad contra un INSERT/UPDATE directo que se salte la capa de app).
    op.execute("""
        CREATE OR REPLACE FUNCTION check_role_permission_same_app() RETURNS trigger AS $$
        BEGIN
            IF (SELECT application_id FROM roles WHERE id = NEW.role_id)
               <> (SELECT application_id FROM permissions WHERE id = NEW.permission_id) THEN
                RAISE EXCEPTION 'role_permissions: el rol y el permiso deben pertenecer a la misma aplicacion';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER role_permissions_same_app
        BEFORE INSERT OR UPDATE ON role_permissions
        FOR EACH ROW EXECUTE FUNCTION check_role_permission_same_app();
    """)

    # El trigger anterior protege role_permissions, pero no evita que un UPDATE directo
    # mueva un rol o un permiso a otra aplicacion y deje un vinculo cruzado ya existente
    # sin que nadie lo valide. application_id es inmutable por diseno (la app duena de un
    # rol/permiso no cambia); bloquearlo en la base es el cambio minimo que cierra esa via.
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_application_id_change() RETURNS trigger AS $$
        BEGIN
            IF NEW.application_id <> OLD.application_id THEN
                RAISE EXCEPTION '%: application_id es inmutable', TG_TABLE_NAME;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER roles_application_id_immutable
        BEFORE UPDATE ON roles
        FOR EACH ROW EXECUTE FUNCTION forbid_application_id_change();
    """)
    op.execute("""
        CREATE TRIGGER permissions_application_id_immutable
        BEFORE UPDATE ON permissions
        FOR EACH ROW EXECUTE FUNCTION forbid_application_id_change();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS permissions_application_id_immutable ON permissions")
    op.execute("DROP TRIGGER IF EXISTS roles_application_id_immutable ON roles")
    op.execute("DROP FUNCTION IF EXISTS forbid_application_id_change()")
    op.execute("DROP TRIGGER IF EXISTS role_permissions_same_app ON role_permissions")
    op.execute("DROP FUNCTION IF EXISTS check_role_permission_same_app()")
    # Los vinculos cruzados borrados en el upgrade no se pueden restaurar.
