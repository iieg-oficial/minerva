"""Manifest Loader del Minerva Dev Kit.

Lee archivos `manifest.minerva.yml` y hace upsert de aplicación, permisos,
roles, relación rol-permiso y un registro de importación.

Reglas de validación (ver `docs/integracion.md`, sección 2):
  * `application.code` debe existir.
  * Los permisos deben seguir la convención `{application_code}.{resource}.{action}`.
  * Los roles no pueden referenciar permisos inexistentes en el manifiesto.
  * El manifiesto no puede incluir permisos de otra aplicación.
"""

import hashlib
import re
import uuid

import yaml
from sqlmodel import Session

from app.core.exceptions import BadRequestError
from app.core.security import hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.applications.repository import ApplicationRepository, RedirectURIRepository
from app.modules.devkit.models import ManifestImport
from app.modules.devkit.schemas import ManifestImportResult
from app.modules.permissions.models import Permission, RolePermission
from app.modules.permissions.repository import PermissionRepository, RolePermissionRepository
from app.modules.roles.models import Role
from app.modules.roles.repository import RoleRepository

_PERMISSION_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _role_slug(application_code: str, role_name: str) -> str:
    normalized = _SLUG_RE.sub("-", role_name.strip().lower()).strip("-")
    return f"{application_code}.{normalized}"


def parse_manifest(content: str) -> dict:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:  # pragma: no cover - depende del input
        raise BadRequestError(detail=f"YAML inválido: {exc}")
    if not isinstance(data, dict):
        raise BadRequestError(detail="El manifiesto debe ser un objeto YAML")
    return data


def validate_manifest(data: dict) -> str:
    """Valida el manifiesto y devuelve el `application.code`."""
    application = data.get("application")
    if not isinstance(application, dict):
        raise BadRequestError(detail="El manifiesto debe incluir la sección `application`")

    code = application.get("code")
    if not code or not isinstance(code, str):
        raise BadRequestError(detail="`application.code` es obligatorio")
    if not re.match(r"^[a-z0-9_]+$", code):
        raise BadRequestError(detail="`application.code` debe ser minúsculas/números/guion_bajo")

    permissions = data.get("permissions") or []
    if not isinstance(permissions, list):
        raise BadRequestError(detail="`permissions` debe ser una lista")

    permission_keys: set[str] = set()
    for perm in permissions:
        if not isinstance(perm, dict) or not perm.get("key"):
            raise BadRequestError(detail="Cada permiso requiere `key`")
        key = perm["key"]
        if not _PERMISSION_RE.match(key):
            raise BadRequestError(
                detail=f"El permiso `{key}` no sigue la convención {{application_code}}.{{resource}}.{{action}}"
            )
        if not key.startswith(f"{code}."):
            raise BadRequestError(detail=f"El permiso `{key}` no pertenece a la aplicación `{code}`")
        permission_keys.add(key)

    roles = data.get("roles") or []
    if not isinstance(roles, list):
        raise BadRequestError(detail="`roles` debe ser una lista")

    for role in roles:
        if not isinstance(role, dict) or not role.get("name"):
            raise BadRequestError(detail="Cada rol requiere `name`")
        for key in role.get("permissions") or []:
            if key not in permission_keys:
                raise BadRequestError(detail=f"El rol `{role['name']}` referencia un permiso inexistente: `{key}`")

    return code


class ManifestLoader:
    def __init__(self, session: Session):
        self.session = session
        self.app_repo = ApplicationRepository(session)
        self.redirect_repo = RedirectURIRepository(session)
        self.perm_repo = PermissionRepository(session)
        self.role_repo = RoleRepository(session)
        self.role_perm_repo = RolePermissionRepository(session)

    def import_manifest(self, content: str, source: str = "manifest.minerva.yml") -> ManifestImportResult:
        data = parse_manifest(content)
        code = validate_manifest(data)
        checksum = hashlib.sha256(content.encode()).hexdigest()

        application = data["application"]
        permissions = data.get("permissions") or []
        roles = data.get("roles") or []

        # --- Aplicación (upsert) ------------------------------------------
        app = self.app_repo.get_by_slug(code)
        created_application = False
        raw_secret: str | None = None
        if not app:
            created_application = True
            raw_secret = str(uuid.uuid4())
            app = Application(
                name=application.get("name", code),
                slug=code,
                description=application.get("description"),
                homepage_url=application.get("base_url"),
                client_id=str(uuid.uuid4()),
                client_secret_hash=hash_secret(raw_secret),
                status="active",
            )
            self.session.add(app)
            self.session.flush()
        else:
            if application.get("name"):
                app.name = application["name"]
            if application.get("description") is not None:
                app.description = application["description"]
            if application.get("base_url"):
                app.homepage_url = application["base_url"]
            self.session.add(app)
            self.session.flush()

        # --- Redirect URIs (upsert) ---------------------------------------
        for uri in application.get("redirect_uris") or []:
            existing = self.redirect_repo.get_by_uri(app.id, uri)
            if not existing:
                self.session.add(RedirectURI(application_id=app.id, uri=uri, environment="development"))
        self.session.flush()

        # --- Permisos (upsert) --------------------------------------------
        perm_by_key: dict[str, Permission] = {}
        permissions_upserted = 0
        for perm in permissions:
            key = perm["key"]
            existing = self.perm_repo.get_by_slug(app.id, key)
            if existing:
                if perm.get("name"):
                    existing.name = perm["name"]
                if perm.get("description") is not None:
                    existing.description = perm["description"]
                self.session.add(existing)
                perm_by_key[key] = existing
            else:
                new_perm = Permission(
                    application_id=app.id,
                    name=perm.get("name", key),
                    slug=key,
                    description=perm.get("description"),
                )
                self.session.add(new_perm)
                perm_by_key[key] = new_perm
                permissions_upserted += 1
        self.session.flush()

        # --- Roles + relación rol-permiso (upsert) ------------------------
        roles_upserted = 0
        role_permissions_linked = 0
        for role in roles:
            slug = _role_slug(code, role["name"])
            existing_role = self.role_repo.get_by_slug(app.id, slug)
            if existing_role:
                existing_role.name = role["name"]
                if role.get("description") is not None:
                    existing_role.description = role["description"]
                self.session.add(existing_role)
                role_obj = existing_role
            else:
                role_obj = Role(
                    application_id=app.id,
                    name=role["name"],
                    slug=slug,
                    description=role.get("description"),
                )
                self.session.add(role_obj)
                roles_upserted += 1
            self.session.flush()

            for key in role.get("permissions") or []:
                perm_obj = perm_by_key[key]
                link = self.role_perm_repo.get(role_obj.id, perm_obj.id)
                if not link:
                    self.session.add(RolePermission(role_id=role_obj.id, permission_id=perm_obj.id))
                    role_permissions_linked += 1
        self.session.flush()

        # --- Registro de importación --------------------------------------
        record = ManifestImport(
            application_id=app.id,
            application_code=code,
            source=source,
            checksum=checksum,
            status="success",
            message=f"{len(permissions)} permisos, {len(roles)} roles",
            permissions_count=len(permissions),
            roles_count=len(roles),
        )
        self.session.add(record)
        self.session.commit()

        return ManifestImportResult(
            application_id=app.id,
            application_code=code,
            created_application=created_application,
            permissions_upserted=permissions_upserted,
            roles_upserted=roles_upserted,
            role_permissions_linked=role_permissions_linked,
            import_id=record.id,
            client_id=app.client_id if created_application else None,
            client_secret=raw_secret,
        )
