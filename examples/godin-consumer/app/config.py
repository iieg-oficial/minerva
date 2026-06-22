import os
from dataclasses import dataclass


@dataclass
class ConsumerSettings:
    """Configuración propia del consumidor (no del SDK: ver minerva_sdk.config)."""

    issuer_url: str = os.getenv("MINERVA_ISSUER_URL", "http://localhost:9000")
    client_id: str = os.getenv("MINERVA_CLIENT_ID", "")
    redirect_uri: str = os.getenv("MINERVA_REDIRECT_URI", "http://localhost:8100/callback")


settings = ConsumerSettings()
