"""Datos propios del portal de demostración."""

from minerva_example.modules.portal.consts import ADMIN_STATS, DOCUMENTS


class PortalRepository:
    def list_documents(self) -> list[dict]:
        return DOCUMENTS

    def get_admin_stats(self) -> dict:
        return ADMIN_STATS
