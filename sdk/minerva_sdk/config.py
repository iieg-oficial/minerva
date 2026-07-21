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
    # Issuer esperado del token. Si el `iss` público difiere del host desde el que se
    # descubre el JWKS (p. ej. red docker vs. dominio público), fíjalo aquí; si se deja
    # vacío se usa `issuer_url`. La validación de `iss` NO se puede desactivar.
    expected_issuer: str = os.getenv("MINERVA_EXPECTED_ISSUER", "")
    permissions_cache_ttl: int = int(os.getenv("MINERVA_PERMISSIONS_CACHE_TTL", "300"))
    jwks_cache_ttl: int = int(os.getenv("MINERVA_JWKS_CACHE_TTL", "3600"))
    # Mínimo entre dos refrescos del JWKS disparados por un `kid` desconocido. Acota el
    # coste de tokens con un `kid` inventado sin retrasar una rotación legítima.
    jwks_refresh_cooldown: int = int(os.getenv("MINERVA_JWKS_REFRESH_COOLDOWN", "30"))
    request_timeout: float = float(os.getenv("MINERVA_REQUEST_TIMEOUT", "10"))


settings = MinervaSettings()
