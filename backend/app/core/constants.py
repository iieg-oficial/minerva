"""Identificadores fijos de la propia Minerva como aplicación."""

MINERVA_APP_SLUG = "minerva"
MINERVA_ADMIN_ROLE_SLUG = "minerva.admin"
# Los roles `minerva.*` solo pueden existir dentro de la app minerva.
RESERVED_ROLE_PREFIX = f"{MINERVA_APP_SLUG}."
