import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.core.config import settings
from app.core.csrf import panel_csrf_middleware
from app.core.database import engine
from app.core.models import import_models
from app.core.redis import close_redis, init_redis
from app.core.security import hash_password, hash_secret
from app.modules.applications.models import Application, RedirectURI
from app.modules.applications.router import public_router
from app.modules.applications.router import router as applications_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.authorization.router import router as authorization_router
from app.modules.devkit.router import router as devkit_router
from app.modules.groups.models import UserRole
from app.modules.groups.router import router as groups_router
from app.modules.oidc.models import SigningKey  # noqa: F401 - registra la tabla en el metadata
from app.modules.oidc.router import userinfo_app, wellknown_app
from app.modules.oidc.service import OIDCService
from app.modules.permissions.models import Permission, RolePermission
from app.modules.permissions.router import router as permissions_router
from app.modules.roles.models import Role
from app.modules.roles.router import router as roles_router
from app.modules.users.models import User
from app.modules.users.router import router as users_router


def _seed_data() -> None:
    import_models()

    with Session(engine) as session:
        existing_admin = session.exec(select(User).where(User.email == settings.ADMIN_EMAIL)).first()
        if existing_admin:
            return

        admin_user = User(
            email=settings.ADMIN_EMAIL,
            full_name="Administrador Minerva",
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            status="active",
            domain="iieg.gob.mx",
        )
        session.add(admin_user)
        session.flush()

        minerva_app = session.exec(select(Application).where(Application.slug == "minerva")).first()
        if not minerva_app:
            raw_secret = str(uuid.uuid4())
            minerva_app = Application(
                name="Minerva",
                slug="minerva",
                description="Sistema central de identidad y acceso del IIEG",
                client_id=str(uuid.uuid4()),
                client_secret_hash=hash_secret(raw_secret),
                status="active",
            )
            session.add(minerva_app)
            session.flush()

            redirect_uri = RedirectURI(
                application_id=minerva_app.id,
                uri=f"{settings.FRONTEND_URL}/auth/callback",
                environment="development",
            )
            session.add(redirect_uri)

        admin_role = session.exec(
            select(Role).where(Role.application_id == minerva_app.id, Role.slug == "minerva.admin")
        ).first()
        if not admin_role:
            admin_role = Role(
                application_id=minerva_app.id,
                name="Administrador",
                slug="minerva.admin",
                description="Administrador global de Minerva",
            )
            session.add(admin_role)
            session.flush()

        perms_data = [
            ("minerva.users.manage", "Gestionar usuarios"),
            ("minerva.applications.manage", "Gestionar aplicaciones"),
            ("minerva.roles.manage", "Gestionar roles"),
            ("minerva.permissions.manage", "Gestionar permisos"),
            ("minerva.groups.manage", "Gestionar grupos"),
            ("minerva.audit.view", "Ver auditoría"),
        ]
        for slug, name in perms_data:
            existing_perm = session.exec(
                select(Permission).where(Permission.application_id == minerva_app.id, Permission.slug == slug)
            ).first()
            if not existing_perm:
                perm = Permission(application_id=minerva_app.id, name=name, slug=slug)
                session.add(perm)
                session.flush()
                session.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))

        existing_ur = session.exec(
            select(UserRole).where(UserRole.user_id == admin_user.id, UserRole.role_id == admin_role.id)
        ).first()
        if not existing_ur:
            session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))

        session.commit()


def _auto_import_manifests() -> None:
    """Importa automáticamente los manifiestos encontrados en
    MINERVA_MANIFESTS_PATH al arrancar (modo Dev Kit)."""
    import logging
    from pathlib import Path

    from app.modules.devkit.service import DevKitService

    logger = logging.getLogger("minerva.devkit")

    if not settings.MINERVA_AUTO_IMPORT_MANIFESTS:
        return

    manifests_dir = Path(settings.MINERVA_MANIFESTS_PATH)
    if not manifests_dir.exists():
        return

    patterns = ["*.minerva.yml", "*.minerva.yaml", "manifest.yml", "manifest.yaml"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(manifests_dir.glob(pattern)))

    for path in files:
        try:
            with Session(engine) as session:
                result = DevKitService(session).import_manifest(path.read_text(encoding="utf-8"), path.name)
            logger.info("Manifiesto importado: %s (app=%s)", path.name, result.application_code)
        except Exception as exc:  # noqa: BLE001 - el arranque no debe fallar por un manifiesto
            logger.warning("No se pudo importar el manifiesto %s: %s", path.name, exc)


def _seed_signing_key() -> None:
    """Garantiza que exista una clave de firma RS256 activa al arrancar (idempotente)."""
    import_models()
    with Session(engine) as session:
        OIDCService(session).ensure_active_signing_key()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_production_config()
    _seed_data()
    _seed_signing_key()
    _auto_import_manifests()
    await init_redis()
    try:
        yield
    finally:
        await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CSRF + Origin para las mutaciones del panel (solo las que traen la cookie de sesión).
app.middleware("http")(panel_csrf_middleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(applications_router)
app.include_router(public_router)
app.include_router(roles_router)
app.include_router(permissions_router)
app.include_router(groups_router)
app.include_router(authorization_router)
app.include_router(audit_router)
app.include_router(devkit_router)

# Endpoints públicos de descubrimiento OIDC y UserInfo. Van montados como sub-app
# por su política de CORS abierta (ver app/modules/oidc/router.py).
app.mount("/.well-known", wellknown_app)
app.mount("/userinfo", userinfo_app)


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
