from datetime import datetime, timezone

from sqlmodel import Session, select

from app.modules.applications.models import Application, RedirectURI
from app.modules.audit.models import AuditLog
from app.modules.auth.models import AuthCode, RefreshToken
from app.modules.devkit.models import ManifestImport
from app.modules.groups.models import GroupRole, UserRole
from app.modules.permissions.models import Permission, RolePermission
from app.modules.roles.models import Role


class ApplicationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, app_id: str) -> Application | None:
        return self.session.get(Application, app_id)

    def get_by_slug(self, slug: str) -> Application | None:
        statement = select(Application).where(Application.slug == slug)
        return self.session.exec(statement).first()

    def get_by_client_id(self, client_id: str) -> Application | None:
        statement = select(Application).where(Application.client_id == client_id)
        return self.session.exec(statement).first()

    def list_all(self, offset: int = 0, limit: int = 100) -> tuple[list[Application], int]:
        statement = select(Application).offset(offset).limit(limit)
        items = self.session.exec(statement).all()
        total = self.session.exec(select(Application)).all()
        return items, len(total)

    def create(self, app: Application) -> Application:
        self.session.add(app)
        self.session.commit()
        self.session.refresh(app)
        return app

    def update(self, app: Application) -> Application:
        app.updated_at = datetime.now(timezone.utc)
        self.session.add(app)
        self.session.commit()
        self.session.refresh(app)
        return app

    def delete(self, app: Application) -> None:
        """Elimina la aplicación y todo lo derivado de ella.

        Borra en cascada manualmente (las FKs no declaran ON DELETE CASCADE):
        redirect URIs, permisos, roles, sus vínculos rol-permiso, las
        asignaciones de esos roles a usuarios y grupos, el historial de
        importaciones de manifiesto y los tokens OIDC emitidos (auth_codes y
        refresh_tokens, ambos con FK a `applications.client_id`). Los registros
        de auditoría se conservan: se les pone `application_id = None`. Es una
        operación destructiva e irreversible.

        Se hace `flush()` por niveles de dependencia para forzar el orden de los
        DELETE: sin `relationship()` declaradas, la unit of work de SQLAlchemy no
        ordena el borrado entre tablas y violaría las FKs en PostgreSQL.
        """
        roles = self.session.exec(select(Role).where(Role.application_id == app.id)).all()
        permissions = self.session.exec(select(Permission).where(Permission.application_id == app.id)).all()

        # Nivel 1: vínculos y asignaciones que dependen de roles/permisos de la app.
        for role in roles:
            for link in self.session.exec(select(RolePermission).where(RolePermission.role_id == role.id)).all():
                self.session.delete(link)
            for user_role in self.session.exec(select(UserRole).where(UserRole.role_id == role.id)).all():
                self.session.delete(user_role)
            for group_role in self.session.exec(select(GroupRole).where(GroupRole.role_id == role.id)).all():
                self.session.delete(group_role)
        # Vínculos rol-permiso que apuntan a permisos de la app (por si quedaron
        # ligados a roles de otra aplicación).
        for perm in permissions:
            for link in self.session.exec(select(RolePermission).where(RolePermission.permission_id == perm.id)).all():
                self.session.delete(link)
        self.session.flush()

        # Nivel 2: roles, permisos, redirect URIs e historial (referencian a la app).
        for role in roles:
            self.session.delete(role)
        for perm in permissions:
            self.session.delete(perm)
        for uri in self.session.exec(select(RedirectURI).where(RedirectURI.application_id == app.id)).all():
            self.session.delete(uri)
        for record in self.session.exec(select(ManifestImport).where(ManifestImport.application_id == app.id)).all():
            self.session.delete(record)
        # Tokens OIDC emitidos: FK a applications.client_id (no a id).
        for code in self.session.exec(select(AuthCode).where(AuthCode.client_id == app.client_id)).all():
            self.session.delete(code)
        for token in self.session.exec(select(RefreshToken).where(RefreshToken.client_id == app.client_id)).all():
            self.session.delete(token)
        # Los registros de auditoría se conservan: solo se desliga la app (FK a applications.id).
        for log in self.session.exec(select(AuditLog).where(AuditLog.application_id == app.id)).all():
            log.application_id = None
            self.session.add(log)
        self.session.flush()

        # Nivel 3: la aplicación.
        self.session.delete(app)
        self.session.commit()


class RedirectURIRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_application(self, app_id: str) -> list[RedirectURI]:
        statement = select(RedirectURI).where(RedirectURI.application_id == app_id)
        return self.session.exec(statement).all()

    def get_by_uri(self, app_id: str, uri: str) -> RedirectURI | None:
        statement = select(RedirectURI).where(
            RedirectURI.application_id == app_id,
            RedirectURI.uri == uri,
        )
        return self.session.exec(statement).first()

    def create(self, redirect_uri: RedirectURI) -> RedirectURI:
        self.session.add(redirect_uri)
        self.session.commit()
        self.session.refresh(redirect_uri)
        return redirect_uri

    def delete(self, redirect_uri: RedirectURI) -> None:
        self.session.delete(redirect_uri)
        self.session.commit()
