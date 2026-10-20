"""Identificadores fijos de la propia Minerva como aplicación."""

MINERVA_APP_SLUG = "minerva"
MINERVA_ADMIN_ROLE_SLUG = "minerva.admin"
# Los roles `minerva.*` solo pueden existir dentro de la app minerva.
RESERVED_ROLE_PREFIX = f"{MINERVA_APP_SLUG}."
# Permiso que convierte a una persona en administradora delegada de su aplicación
# (`{app}.access.manage`): puede invitar, asignar roles y restablecer cuentas de esa app.
DELEGATE_PERMISSION_SUFFIX = ".access.manage"


def delegate_permission(application_slug: str) -> str:
    return f"{application_slug}{DELEGATE_PERMISSION_SUFFIX}"
