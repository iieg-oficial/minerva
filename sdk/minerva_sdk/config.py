import os
from dataclasses import dataclass


@dataclass
class MinervaSettings:
    """Configuración del SDK leída desde variables de entorno.

    En producción el SDK valida la firma RS256 contra el JWKS público de Minerva
    (sin secreto compartido). Para migrar de Minerva Dev a Minerva Central basta
    con cambiar `MINERVA_ISSUER_URL`: el JWKS y los endpoints se descubren solos.
    """

    issuer_url: str = os.getenv("MINERVA_ISSUER_URL", "http://localhost:9000")
    application_code: str = os.getenv("MINERVA_APPLICATION_CODE", "")
    # Si está vacío no se valida el issuer (útil cuando el host difiere
    # entre red docker y localhost en desarrollo).
    expected_issuer: str = os.getenv("MINERVA_EXPECTED_ISSUER", "")
    permissions_cache_ttl: int = int(os.getenv("MINERVA_PERMISSIONS_CACHE_TTL", "300"))
    jwks_cache_ttl: int = int(os.getenv("MINERVA_JWKS_CACHE_TTL", "3600"))
    # Verifica que el `aud` del access token sea esta aplicación. Recomendado.
    verify_aud: bool = os.getenv("MINERVA_VERIFY_AUD", "true").lower() == "true"
    # Secreto compartido SOLO para validar tokens HS256 legacy (transición). Si se
    # deja vacío, el SDK solo acepta RS256 (recomendado en producción).
    jwt_secret: str = os.getenv("MINERVA_JWT_SECRET", "")
    request_timeout: float = float(os.getenv("MINERVA_REQUEST_TIMEOUT", "10"))


settings = MinervaSettings()
