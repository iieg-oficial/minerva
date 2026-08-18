"""Permisos y datos de demostración del portal."""

DOCUMENTS_VIEW = "portal_demo.documents.view"
DOCUMENTS_CREATE = "portal_demo.documents.create"
SYSTEM_MANAGE = "portal_demo.system.manage"

DOCUMENTS = [
    {
        "folio": "PD-2026-0042",
        "subject": "Informe mensual de actividades",
        "status": "En revisión",
        "updated_at": "18 ago 2026",
    },
    {
        "folio": "PD-2026-0037",
        "subject": "Solicitud de actualización",
        "status": "Atendido",
        "updated_at": "15 ago 2026",
    },
]

ADMIN_STATS = {"Usuarios activos": 24, "Documentos pendientes": 7, "Integraciones": 1}
