from sqlmodel import Session

from app.core.constants import delegate_permission
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.modules.applications.models import Application
from app.modules.credentials.schemas import CredentialLink
from app.modules.credentials.service import CredentialService
from app.modules.delegated.schemas import (
    DelegatedRoleRead,
    DelegatedUserCreate,
    DelegatedUserCreated,
    DelegatedUserRead,
    DelegatedUserRole,
)
from app.modules.groups.models import UserRole
from app.modules.groups.repository import GroupRoleRepository, GroupUserRepository, UserRoleRepository
from app.modules.permissions.repository import RolePermissionRepository
from app.modules.roles.models import Role
from app.modules.roles.repository import RoleRepository
from app.modules.users.models import USER_KIND_HUMAN, User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService

# Una persona fuera de la aplicación se responde igual que una inexistente: el delegado
# no debe poder sondear quién existe en Minerva.
NOT_IN_APP_DETAIL = "Usuario no encontrado en esta aplicación"
OTHER_APPS_DETAIL = (
    "La persona tiene acceso a otras aplicaciones; su contraseña la restablece un administrador de Minerva"
)


class DelegatedService:
    """Administración de una sola aplicación en nombre de una persona delegada.

    Las reglas contra escalamiento viven aquí y cada una tiene su test:
    no se toca a sí misma, no asigna ni retira roles que den administración delegada,
    y solo restablece cuentas cuyos roles sean todos de esta aplicación."""

    def __init__(self, session: Session, application: Application):
        self.session = session
        self.app = application
        self.user_repo = UserRepository(session)
        self.role_repo = RoleRepository(session)
        self.user_role_repo = UserRoleRepository(session)
        self.group_user_repo = GroupUserRepository(session)
        self.group_role_repo = GroupRoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    def _app_roles(self) -> list[Role]:
        return self.role_repo.list_by_application(self.app.id)

    def _is_delegate_role(self, role: Role) -> bool:
        slug = delegate_permission(self.app.slug)
        return any(p.slug == slug for p in self.role_perm_repo.list_permissions_by_role(role.id))

    def _group_roles(self, user_id: str) -> list[Role]:
        roles: list[Role] = []
        for gid in self.group_user_repo.list_groups_for_user(user_id):
            roles.extend(self.group_role_repo.list_roles_for_group(gid))
        return roles

    def _roles_in_app(self, user_id: str) -> list[DelegatedUserRole]:
        direct = {r.id: r for r in self.user_role_repo.list_roles_for_user(user_id) if r.application_id == self.app.id}
        inherited = {
            r.id: r for r in self._group_roles(user_id) if r.application_id == self.app.id and r.id not in direct
        }
        return [DelegatedUserRole(id=r.id, slug=r.slug, name=r.name, via="direct") for r in direct.values()] + [
            DelegatedUserRole(id=r.id, slug=r.slug, name=r.name, via="group") for r in inherited.values()
        ]

    def _read(self, user: User) -> DelegatedUserRead:
        return DelegatedUserRead(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            roles=self._roles_in_app(user.id),
        )

    def _get_member(self, user_id: str) -> User:
        user = self.user_repo.get_by_id(user_id)
        if user is None or user.kind != USER_KIND_HUMAN or not self._roles_in_app(user_id):
            raise NotFoundError(detail=NOT_IN_APP_DETAIL)
        return user

    def list_roles(self) -> list[DelegatedRoleRead]:
        return [
            DelegatedRoleRead(
                id=r.id,
                slug=r.slug,
                name=r.name,
                description=r.description,
                delegable=not self._is_delegate_role(r),
            )
            for r in self._app_roles()
        ]

    def list_users(self, email: str | None = None) -> list[DelegatedUserRead]:
        """Con `email`, búsqueda exacta: sirve para saber si la persona ya existe antes de
        darla de alta, aunque todavía no tenga roles aquí. Sin él, solo las personas con
        algún rol de la aplicación."""
        if email:
            user = self.user_repo.get_by_email(email)
            if user is None or user.kind != USER_KIND_HUMAN:
                return []
            return [self._read(user)]
        ids: set[str] = set()
        for role in self._app_roles():
            ids.update(u.id for u in self.user_role_repo.list_users_for_role(role.id))
            for gid in self.group_role_repo.list_groups_for_role(role.id):
                ids.update(self.group_user_repo.list_users_in_group(gid))
        users = [u for u in (self.user_repo.get_by_id(i) for i in ids) if u and u.kind == USER_KIND_HUMAN]
        return [self._read(u) for u in sorted(users, key=lambda u: u.email)]

    def _check_assignable(self, role_ids: list[str]) -> list[Role]:
        roles = []
        for role_id in dict.fromkeys(role_ids):
            role = self.role_repo.get_by_id(role_id)
            if role is None or role.application_id != self.app.id:
                raise BadRequestError(detail="El rol no pertenece a esta aplicación")
            if self._is_delegate_role(role):
                raise ForbiddenError(detail="Los roles de administración delegada solo los asigna Minerva")
            roles.append(role)
        return roles

    def create_user(self, actor_id: str, data: DelegatedUserCreate) -> DelegatedUserCreated:
        """Alta por invitación con sus roles de esta aplicación. Si el correo ya existe no
        se toca la cuenta: la persona puede tener roles en otras aplicaciones y su alta no
        le corresponde a este delegado. Los roles se fijan después con `set_roles`."""
        existing = self.user_repo.get_by_email(data.email)
        if existing is not None:
            if existing.kind != USER_KIND_HUMAN:
                raise BadRequestError(detail="El correo pertenece a una cuenta de servicio")
            return DelegatedUserCreated(**self._read(existing).model_dump(), created=False)
        roles = self._check_assignable(data.role_ids)
        user = UserService(self.session).create_user(
            UserCreate(email=data.email, full_name=data.full_name), commit=False
        )
        for role in roles:
            self.user_role_repo.add(UserRole(user_id=user.id, role_id=role.id), commit=False)
        link = self._issue(actor_id, user.id)
        created = self.user_repo.get_by_id(user.id)
        assert created is not None
        return DelegatedUserCreated(**self._read(created).model_dump(), created=True, credential_link=link)

    def set_roles(self, actor_id: str, user_id: str, role_ids: list[str]) -> tuple[DelegatedUserRead, dict]:
        """Fija los roles directos de esta aplicación. Los heredados de un grupo y los de
        administración delegada quedan como están. Devuelve el detalle para auditoría."""
        if user_id == actor_id:
            raise ForbiddenError(detail="No puedes cambiar tus propios roles")
        user = self.user_repo.get_by_id(user_id)
        if user is None or user.kind != USER_KIND_HUMAN:
            raise NotFoundError(detail=NOT_IN_APP_DETAIL)
        wanted = {r.id for r in self._check_assignable(role_ids)}
        current = {r.id: r for r in self.user_role_repo.list_roles_for_user(user_id) if r.application_id == self.app.id}
        editable = {rid for rid, r in current.items() if not self._is_delegate_role(r)}
        added = sorted(wanted - editable)
        removed = sorted(editable - wanted)
        for rid in added:
            self.user_role_repo.add(UserRole(user_id=user_id, role_id=rid), commit=False)
        for rid in removed:
            link = self.user_role_repo.get(user_id, rid)
            if link is not None:
                self.user_role_repo.remove(link, commit=False)
        self.session.flush()
        return self._read(user), {"added": added, "removed": removed}

    def _issue(self, actor_id: str, user_id: str) -> CredentialLink:
        credentials = CredentialService(self.session)
        destination = next((d for d in credentials.destinations(user_id) if d.id == self.app.id), None)
        return credentials.issue_link(
            user_id,
            created_by=actor_id,
            commit=False,
            application_id=destination.id if destination else None,
        )

    def issue_link(self, actor_id: str, user_id: str) -> CredentialLink:
        """Invitación de una cuenta pendiente o restablecimiento de una activa. El reset
        solo procede si todos los roles de la persona son de esta aplicación: si no, el
        delegado podría tomar la cuenta de alguien con acceso a otras, Minerva incluida."""
        user = self._get_member(user_id)
        if user.status != "pending":
            all_roles = self.user_role_repo.list_roles_for_user(user_id) + self._group_roles(user_id)
            if any(r.application_id != self.app.id for r in all_roles):
                raise ForbiddenError(detail=OTHER_APPS_DETAIL)
        return self._issue(actor_id, user_id)
