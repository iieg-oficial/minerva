"""Tests del seed idempotente (R17): reconcilia cada recurso por separado y repara
estado parcial aunque el admin-user ya exista."""

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import hash_password
from app.main import seed_admin
from app.modules.applications.models import Application
from app.modules.groups.models import UserRole
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role
from app.modules.users.models import User
from tests.conftest import test_engine

PERM_SLUGS = {
    "minerva.users.manage",
    "minerva.applications.manage",
    "minerva.roles.manage",
    "minerva.permissions.manage",
    "minerva.groups.manage",
    "minerva.audit.view",
}


def _admin_only(session: Session) -> User:
    """Estado parcial del bug: el admin-user existe pero la app minerva (y su rol,
    permisos y asignación) fue borrada desde el panel."""
    admin = User(
        email=settings.ADMIN_EMAIL,
        full_name="Administrador Minerva",
        hashed_password=hash_password(settings.ADMIN_PASSWORD),
        status="active",
        domain="iieg.gob.mx",
    )
    session.add(admin)
    session.commit()
    return admin


def test_seed_reconstruye_estado_con_solo_admin_presente():
    with Session(test_engine) as session:
        admin = _admin_only(session)

        seed_admin(session)
        session.commit()

        app = session.exec(select(Application).where(Application.slug == "minerva")).first()
        assert app is not None, "el seed debe reconstruir la app minerva borrada"

        role = session.exec(select(Role).where(Role.application_id == app.id, Role.slug == "minerva.admin")).first()
        assert role is not None

        perms = session.exec(select(Permission).where(Permission.application_id == app.id)).all()
        assert {p.slug for p in perms} == PERM_SLUGS
        links = session.exec(select(RolePermission).where(RolePermission.role_id == role.id)).all()
        assert len(links) == len(PERM_SLUGS)

        ur = session.exec(select(UserRole).where(UserRole.user_id == admin.id, UserRole.role_id == role.id)).first()
        assert ur is not None, "el admin debe recuperar su rol"


def test_seed_es_idempotente():
    with Session(test_engine) as session:
        seed_admin(session)
        session.commit()
        seed_admin(session)
        session.commit()

        assert len(session.exec(select(Application).where(Application.slug == "minerva")).all()) == 1
        roles = session.exec(select(Role).where(Role.slug == "minerva.admin")).all()
        assert len(roles) == 1
        assert len(session.exec(select(Permission)).all()) == len(PERM_SLUGS)
        assert len(session.exec(select(RolePermission)).all()) == len(PERM_SLUGS)
        assert len(session.exec(select(UserRole)).all()) == 1


def test_seed_reconstruye_link_permiso_huerfano():
    """Estado parcial hermano: rol borrado y recreado sin borrar la app → los permisos
    sobreviven pero sus links al rol no. El seed reconstruye los RolePermission."""
    with Session(test_engine) as session:
        seed_admin(session)
        session.commit()

        role = session.exec(select(Role).where(Role.slug == "minerva.admin")).first()
        for link in session.exec(select(RolePermission).where(RolePermission.role_id == role.id)).all():
            session.delete(link)
        session.commit()

        seed_admin(session)
        session.commit()

        links = session.exec(select(RolePermission).where(RolePermission.role_id == role.id)).all()
        assert len(links) == len(PERM_SLUGS), "el seed debe reconstruir los links rol↔permiso"
