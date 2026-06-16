import os
from dataclasses import dataclass


@dataclass
class MinervaSettings:
    """Configuración del SDK leída desde variables de entorno.

    Para migrar de Minerva Dev a Minerva Central, basta con cambiar estas
    variables (sobre todo `MINERVA_ISSUER_URL` y, en producción, el mecanismo
    de validación de firma).
    """

    issuer_url: str = os.getenv("MINERVA_ISSUER_URL", "http://localhost:9000")
    application_code: str = os.getenv("MINERVA_APPLICATION_CODE", "")
    jwt_secret: str = os.getenv("MINERVA_JWT_SECRET", "dev-secret")
    jwt_algorithm: str = os.getenv("MINERVA_JWT_ALGORITHM", "HS256")
    # Si está vacío no se valida el issuer (útil cuando el host difiere
    # entre red docker y localhost en desarrollo).
    expected_issuer: str = os.getenv("MINERVA_EXPECTED_ISSUER", "")
    permissions_cache_ttl: int = int(os.getenv("MINERVA_PERMISSIONS_CACHE_TTL", "300"))
    verify_signature: bool = os.getenv("MINERVA_VERIFY_SIGNATURE", "true").lower() == "true"


settings = MinervaSettings()
