from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_db_url(url: str) -> str:
    """Acepta tanto `postgresql://` como `postgresql+psycopg://` y normaliza
    al driver psycopg (v3) que usa el proyecto."""
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Minerva"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg://minerva:minerva@localhost:5432/minerva"
    SECRET_KEY: str = "change-me-in-production-use-long-random-string"

    JWT_SECRET_KEY: str = "change-me-in-production-use-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    ADMIN_EMAIL: str = "admin@iieg.gob.mx"
    ADMIN_PASSWORD: str = "changeme123"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:9000/auth/google/callback"
    ALLOWED_GOOGLE_DOMAIN: str = "iieg.gob.mx"

    MINERVA_ISSUER: str = "http://localhost:9000"
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Minerva Dev Kit ---------------------------------------------------
    # Estas variables siguen el contrato del documento `minerva-dev-kit-context.md`.
    # Cuando están definidas tienen prioridad sobre las variables heredadas
    # (DATABASE_URL, JWT_SECRET_KEY, etc.) para facilitar la futura migración a
    # una Minerva Central cambiando únicamente configuración.
    MINERVA_MODE: str = "dev"
    MINERVA_DB_URL: str = ""
    MINERVA_ENABLE_DEV_LOGIN: bool = True
    MINERVA_AUTO_IMPORT_MANIFESTS: bool = True
    MINERVA_MANIFESTS_PATH: str = "/app/manifests"
    MINERVA_JWT_ISSUER: str = ""
    MINERVA_JWT_SECRET: str = ""
    MINERVA_ACCESS_TOKEN_EXPIRE_MINUTES: int = 0

    # --- OIDC / firma de tokens --------------------------------------------
    # Algoritmo de firma de los access tokens. Durante la transición a OIDC se
    # mantiene HS256 (secreto compartido) por defecto; se cambia a RS256 (JWKS)
    # cuando la infraestructura de claves y refresh tokens esté en producción.
    MINERVA_SIGNING_ALG: str = "RS256"  # HS256 | RS256
    # Clave maestra (Fernet) para cifrar la clave privada RSA en reposo en la BD.
    # OBLIGATORIA en producción. En dev, si está vacía, se deriva una clave estable
    # del secreto JWT (no apta para producción). Generar con: Fernet.generate_key().
    MINERVA_KEY_ENCRYPTION_KEY: str = ""

    # --- Redis -------------------------------------------------------------
    # Redis tiene un alcance acotado: rate limiting, blacklist de tokens y
    # sesiones efímeras del flujo /authorize. NO es la fuente de verdad de datos.
    REDIS_URL: str = "redis://minerva_redis:6379/0"
    RATE_LIMIT_LOGIN_MAX: int = 5
    RATE_LIMIT_LOGIN_WINDOW: int = 900  # segundos (15 min)
    RATE_LIMIT_AUTHORIZE_MAX: int = 20
    RATE_LIMIT_AUTHORIZE_WINDOW: int = 60

    # --- Valores efectivos -------------------------------------------------
    @property
    def effective_db_url(self) -> str:
        return _normalize_db_url(self.MINERVA_DB_URL) if self.MINERVA_DB_URL else self.DATABASE_URL

    @property
    def effective_jwt_secret(self) -> str:
        return self.MINERVA_JWT_SECRET or self.JWT_SECRET_KEY

    @property
    def effective_jwt_issuer(self) -> str:
        return self.MINERVA_JWT_ISSUER or self.MINERVA_ISSUER

    @property
    def effective_token_expire_minutes(self) -> int:
        return self.MINERVA_ACCESS_TOKEN_EXPIRE_MINUTES or self.ACCESS_TOKEN_EXPIRE_MINUTES

    @property
    def is_dev_mode(self) -> bool:
        return self.MINERVA_MODE.lower() == "dev"


settings = Settings()
