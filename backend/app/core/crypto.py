"""Cifrado simétrico en reposo para secretos sensibles guardados en la BD.

Se usa para la clave privada RSA de firma de tokens (`signing_keys.private_key_pem`),
que NUNCA debe persistirse en texto plano.

Usa Fernet (AES-128-CBC + HMAC) de `cryptography`, ya disponible vía
`python-jose[cryptography]`. La clave maestra es `MINERVA_KEY_ENCRYPTION_KEY`:
obligatoria en producción; en dev se deriva del secreto JWT para que el desarrollo
funcione entre reinicios sin configurar nada (no apto para producción).
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet

from app.core.config import settings

logger = logging.getLogger("minerva.crypto")


def _master_key() -> bytes:
    if settings.MINERVA_KEY_ENCRYPTION_KEY:
        return settings.MINERVA_KEY_ENCRYPTION_KEY.encode()
    if settings.is_production:
        raise RuntimeError(
            "MINERVA_KEY_ENCRYPTION_KEY es obligatoria en producción para cifrar la clave privada en reposo."
        )
    # Dev: clave estable derivada del secreto JWT (no apta para producción).
    logger.warning("MINERVA_KEY_ENCRYPTION_KEY no configurada; usando clave de desarrollo derivada del secreto JWT.")
    digest = hashlib.sha256(settings.effective_jwt_secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_master_key())


def encrypt_secret(plaintext: str) -> str:
    """Cifra un secreto para guardarlo en la BD."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Descifra un secreto recuperado de la BD."""
    return _fernet().decrypt(token.encode()).decode()
