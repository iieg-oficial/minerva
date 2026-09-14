"""Punto único donde se cargan TODOS los modelos con `table=True`.

Alembic construye el autogenerate comparando la base contra `SQLModel.metadata`:
si un módulo no se importó, su tabla no existe para Alembic y una revisión
autogenerada propondría borrarla. Por eso los imports son explícitos —no hay
descubrimiento dinámico— y quien agregue un módulo con tablas debe sumarlo aquí.
"""


def import_models() -> None:
    from app.modules.applications import models as applications_models  # noqa: F401
    from app.modules.audit import models as audit_models  # noqa: F401
    from app.modules.auth import models as auth_models  # noqa: F401
    from app.modules.credentials import models as credentials_models  # noqa: F401
    from app.modules.devkit import models as devkit_models  # noqa: F401
    from app.modules.groups import models as groups_models  # noqa: F401
    from app.modules.oidc import models as oidc_models  # noqa: F401
    from app.modules.permissions import models as permissions_models  # noqa: F401
    from app.modules.roles import models as roles_models  # noqa: F401
    from app.modules.users import models as users_models  # noqa: F401
