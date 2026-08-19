"""Configuración cargada antes de importar el SDK."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from minerva_sdk import settings as minerva_settings  # noqa: E402

FRONTEND_DIR = Path(__file__).parents[1] / "frontend"
APP_TITLE = "Portal Demo · integración con Minerva"


def cookie_secure() -> bool:
    return minerva_settings.redirect_uri.startswith("https://")


def integration_status() -> dict:
    try:
        minerva_settings.validate(login=True)
        ok, message = True, "Configuración completa"
    except ValueError as exc:
        ok, message = False, str(exc)
    return {
        "ok": ok,
        "message": message,
        "values": {
            "MINERVA_ISSUER_URL": minerva_settings.issuer_url,
            "MINERVA_APPLICATION_CODE": minerva_settings.application_code or "FALTA",
            "MINERVA_CLIENT_ID": minerva_settings.client_id or "FALTA",
            "MINERVA_CLIENT_SECRET": "configurado"
            if minerva_settings.client_secret
            else "vacío (solo válido para cliente público)",
            "MINERVA_REDIRECT_URI": minerva_settings.redirect_uri or "FALTA",
        },
    }
