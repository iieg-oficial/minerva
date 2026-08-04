"""Tests de validación fail-fast de configuración en modo no-dev (issues #6 y #69)."""

import pytest

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    base = {
        "MINERVA_MODE": "production",
        "MINERVA_ENABLE_DEV_LOGIN": False,
        "ADMIN_PASSWORD": "una-password-real-y-larga",
        "SECRET_KEY": "valor-generado-aleatorio",
        "JWT_SECRET_KEY": "valor-generado-aleatorio",
        "MINERVA_KEY_ENCRYPTION_KEY": "clave-fernet-real",
        "MINERVA_ISSUER": "https://minerva.jalisco.gob.mx",
        "FRONTEND_URL": "https://minerva.jalisco.gob.mx",
    }
    base.update(overrides)
    return Settings(**base)


def test_dev_mode_never_raises():
    Settings(MINERVA_MODE="dev", ADMIN_PASSWORD="changeme123").validate_production_config()


def test_production_with_safe_config_does_not_raise():
    _settings().validate_production_config()


def test_production_rejects_dev_login_enabled():
    with pytest.raises(RuntimeError, match="MINERVA_ENABLE_DEV_LOGIN"):
        _settings(MINERVA_ENABLE_DEV_LOGIN=True).validate_production_config()


def test_production_rejects_default_admin_password():
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        _settings(ADMIN_PASSWORD="changeme123").validate_production_config()


def test_production_rejects_default_secret_key():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _settings(SECRET_KEY="change-me-in-production-use-long-random-string").validate_production_config()


def test_production_rejects_empty_key_encryption_key():
    with pytest.raises(RuntimeError, match="MINERVA_KEY_ENCRYPTION_KEY"):
        _settings(MINERVA_KEY_ENCRYPTION_KEY="").validate_production_config()


# --- Origen público único: la cookie `__Host-` es host-only (issue #69) ---


def test_production_rejects_frontend_url_on_a_different_host_than_the_issuer():
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        _settings(FRONTEND_URL="https://panel.jalisco.gob.mx").validate_production_config()


def test_production_rejects_jwt_issuer_on_a_different_host_than_the_frontend():
    with pytest.raises(RuntimeError, match="MINERVA_JWT_ISSUER"):
        _settings(MINERVA_JWT_ISSUER="https://api.jalisco.gob.mx").validate_production_config()


def test_production_accepts_same_host_with_different_scheme_or_trailing_slash():
    # El TLS puede terminar fuera del contenedor: nginx sirve HTTP con el mismo host público.
    _settings(FRONTEND_URL="http://minerva.jalisco.gob.mx/").validate_production_config()


def test_production_rejects_same_host_on_a_different_port():
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        _settings(FRONTEND_URL="https://minerva.jalisco.gob.mx:9000").validate_production_config()


def test_production_reports_all_problems_at_once():
    with pytest.raises(RuntimeError) as exc_info:
        _settings(MINERVA_ENABLE_DEV_LOGIN=True, ADMIN_PASSWORD="changeme123").validate_production_config()
    message = str(exc_info.value)
    assert "MINERVA_ENABLE_DEV_LOGIN" in message
    assert "ADMIN_PASSWORD" in message
