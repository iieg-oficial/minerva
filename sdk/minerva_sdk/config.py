import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def _env(name: str, default: str = ""):
    return field(default_factory=lambda: os.getenv(name, default))


def _env_int(name: str, default: int):
    return field(default_factory=lambda: int(os.getenv(name, str(default))))


def _env_float(name: str, default: float):
    return field(default_factory=lambda: float(os.getenv(name, str(default))))


@dataclass
class MinervaSettings:
    """Configuración del SDK leída desde variables de entorno.

    En producción el SDK valida la firma RS256 contra el JWKS público de Minerva
    (sin secreto compartido). Para migrar de Minerva Dev a Minerva Central basta
    con cambiar `MINERVA_ISSUER_URL`: el SDK construye desde ahí las rutas OIDC y JWKS.
    """

    issuer_url: str = _env("MINERVA_ISSUER_URL", "http://localhost:3100")
    application_code: str = _env("MINERVA_APPLICATION_CODE")
    client_id: str = _env("MINERVA_CLIENT_ID")
    client_secret: str = _env("MINERVA_CLIENT_SECRET")
    redirect_uri: str = _env("MINERVA_REDIRECT_URI")
    # Issuer esperado del token. Si el `iss` público difiere del host desde el que se
    # descubre el JWKS (p. ej. red docker vs. dominio público), fíjalo aquí; si se deja
    # vacío se usa `issuer_url`. La validación de `iss` NO se puede desactivar.
    expected_issuer: str = _env("MINERVA_EXPECTED_ISSUER")
    # Caché de permisos DESACTIVADA por defecto (0 = sin caché).
    # Con caché, una decisión positiva se sirve de memoria sin consultar a Minerva, así
    # que un token revocado sigue autorizando hasta que la entrada expire: la revocación
    # deja de ser inmediata. Activarla es una decisión explícita del consumidor, que
    # acepta esa ventana a cambio de menos tráfico (ver sdk/README.md).
    permissions_cache_ttl: int = _env_int("MINERVA_PERMISSIONS_CACHE_TTL", 0)
    jwks_cache_ttl: int = _env_int("MINERVA_JWKS_CACHE_TTL", 3600)
    # Mínimo entre dos refrescos del JWKS disparados por un `kid` desconocido. Acota el
    # coste de tokens con un `kid` inventado sin retrasar una rotación legítima.
    jwks_refresh_cooldown: int = _env_int("MINERVA_JWKS_REFRESH_COOLDOWN", 30)
    request_timeout: float = _env_float("MINERVA_REQUEST_TIMEOUT", 10)

    def validate(self, *, login: bool = False) -> None:
        """Explica los valores faltantes antes de iniciar un flujo contra Minerva."""
        problems = []
        issuer = urlsplit(self.issuer_url)
        if issuer.scheme not in {"http", "https"} or not issuer.netloc:
            problems.append("MINERVA_ISSUER_URL debe ser una URL absoluta, por ejemplo http://localhost:3100")
        if not self.application_code:
            problems.append(
                "MINERVA_APPLICATION_CODE debe ser el código/slug de la aplicación, por ejemplo portal_demo"
            )
        if login:
            if not self.client_id:
                problems.append("MINERVA_CLIENT_ID debe copiarse desde la aplicación registrada en Minerva")
            redirect = urlsplit(self.redirect_uri)
            if redirect.scheme not in {"http", "https"} or not redirect.netloc:
                problems.append(
                    "MINERVA_REDIRECT_URI debe ser la callback exacta registrada en Minerva, "
                    "por ejemplo http://localhost:8100/callback"
                )
        if problems:
            raise ValueError("Configuración de Minerva incompleta:\n- " + "\n- ".join(problems))


settings = MinervaSettings()
