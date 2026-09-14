from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


def _public_host(url: str) -> str:
    """Host (con puerto) de una URL pública, para comparar orígenes. Ignora el
    esquema —el TLS puede terminar fuera del contenedor— y la barra final."""
    return urlparse(url.strip().rstrip("/")).netloc.lower()


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

    # JWT_SECRET_KEY ya no firma tokens (todo es RS256). Se conserva solo como
    # base para derivar la clave de cifrado en reposo en modo dev (ver core/crypto.py).
    JWT_SECRET_KEY: str = "change-me-in-production-use-long-random-string"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    ADMIN_EMAIL: str = "admin@iieg.gob.mx"
    ADMIN_PASSWORD: str = "changeme123"

    MINERVA_ISSUER: str = "http://localhost:9000"
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Minerva Dev Kit ---------------------------------------------------
    # Estas variables siguen el contrato Minerva Dev Kit (ver `docs/integracion.md`).
    # Cuando están definidas tienen prioridad sobre las variables heredadas
    # (DATABASE_URL, JWT_SECRET_KEY, etc.) para facilitar la futura migración a
    # una Minerva Central cambiando únicamente configuración.
    MINERVA_MODE: str = "dev"
    MINERVA_DB_URL: str = ""
    MINERVA_ENABLE_DEV_LOGIN: bool = True
    # Registro público self-service en /auth/register. Cerrado por defecto: Minerva
    # es un IdP institucional, las cuentas las provisiona un admin (o la federación).
    # Habilítalo solo si de verdad quieres alta libre de cuentas.
    MINERVA_ENABLE_PUBLIC_REGISTER: bool = False
    MINERVA_AUTO_IMPORT_MANIFESTS: bool = True
    MINERVA_MANIFESTS_PATH: str = "/app/manifests"
    MINERVA_JWT_ISSUER: str = ""
    MINERVA_JWT_SECRET: str = ""
    MINERVA_ACCESS_TOKEN_EXPIRE_MINUTES: int = 0

    # --- OIDC / firma de tokens --------------------------------------------
    # Toda la firma es RS256 (clave RSA + JWKS). No hay HS256 ni secreto compartido.
    # Clave maestra (Fernet) para cifrar la clave privada RSA en reposo en la BD.
    # OBLIGATORIA en producción. En dev, si está vacía, se deriva una clave estable
    # del secreto JWT (no apta para producción). Generar con: Fernet.generate_key().
    MINERVA_KEY_ENCRYPTION_KEY: str = ""
    # TTL de los tokens emitidos por el canje OIDC (/auth/token). Se mantienen
    # SEPARADOS del TTL de la sesión interna del panel (effective_token_expire_minutes)
    # para poder tener access tokens cortos sin forzar re-login del panel admin.
    # access token corto + refresh token = ciclo de vida estándar OIDC.
    MINERVA_ACCESS_TOKEN_TTL_MINUTES: int = 15
    MINERVA_REFRESH_TOKEN_TTL_DAYS: int = 30
    # Caché del JWKS (Redis) para no reconstruirlo desde BD en cada request que
    # valida un token. Con TTL corto, un caché stale nunca rechaza un JWKS válido
    # dentro de la ventana (build_jwks() ya incluye claves retiradas).
    MINERVA_JWKS_CACHE_TTL_SECONDS: int = 300
    # Cuánto puede tardar un verificador externo en ver una clave nueva en su JWKS
    # cacheado. Gobierna cuándo una clave `pending` puede promoverse a `active`
    # (publish-before-use). Default 60 min: cubre el default del SDK, que cachea el
    # JWKS una hora (MINERVA_JWKS_CACHE_TTL=3600).
    MINERVA_KEY_PROPAGATION_MINUTES: int = 60
    # Margen de reloj entre Minerva y los verificadores, para no purgar una clave
    # justo cuando a otro le queda un segundo de token válido.
    MINERVA_CLOCK_SKEW_MINUTES: int = 5

    # --- Redis -------------------------------------------------------------
    # Redis es control de seguridad: rate limiting, blacklist de tokens, cortes de
    # invalidación por usuario y el contenedor de sesión del panel (patrón BFF, la
    # fuente de verdad efímera del multi-cuenta). NO es la fuente de verdad de datos.
    REDIS_URL: str = "redis://minerva_redis:6379/0"
    RATE_LIMIT_LOGIN_MAX: int = 5
    RATE_LIMIT_LOGIN_WINDOW: int = 900  # segundos (15 min)
    RATE_LIMIT_AUTHORIZE_MAX: int = 20
    RATE_LIMIT_AUTHORIZE_WINDOW: int = 60
    # Por IP: una oficina detrás de un NAT puede activar varias cuentas seguidas. El token
    # del enlace (256 bits) no se adivina; el límite es contra abuso, no contra fuerza bruta.
    RATE_LIMIT_CREDENTIAL_MAX: int = 30
    RATE_LIMIT_CREDENTIAL_WINDOW: int = 900

    # --- Ciclo de vida de la credencial ------------------------------------
    # Vigencia de los enlaces de un solo uso para fijar la contraseña. Un enlace vencido
    # no se renueva solo: el administrador genera otro (que invalida al anterior).
    CREDENTIAL_INVITE_TTL_HOURS: int = 72
    CREDENTIAL_RESET_TTL_HOURS: int = 24
    # El que emite el login cuando la contraseña debe cambiarse: se usa en el acto.
    CREDENTIAL_FORCED_CHANGE_TTL_MINUTES: int = 10

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
    def key_retirement_overlap_minutes(self) -> int:
        """Cuánto debe seguir publicada en el JWKS una clave ya retirada: la vida
        máxima de CUALQUIER token firmado con ella, más el margen de reloj. Purgarla
        antes invalida tokens todavía vigentes.

        Se deriva (no es una variable de entorno aparte) para que no pueda quedar
        desincronizada del TTL de sesión. El máximo real es la sesión del panel
        (`effective_token_expire_minutes`, 480 min), NO el access token OIDC
        (`MINERVA_ACCESS_TOKEN_TTL_MINUTES`, 15 min) que se usaba antes. Los refresh
        tokens no entran: son opacos y hasheados en BD, nadie los firma.
        """
        max_signed_token_minutes = max(self.MINERVA_ACCESS_TOKEN_TTL_MINUTES, self.effective_token_expire_minutes)
        return max_signed_token_minutes + self.MINERVA_CLOCK_SKEW_MINUTES

    # --- Señal única de entorno --------------------------------------------
    # `APP_ENV` y `MINERVA_MODE` marcan lo mismo desde dos lados. Se resuelven en
    # UNA sola propiedad —la que consumen cookies y el fail-fast— y solo es
    # desarrollo si AMBAS lo dicen: cualquier marca de producción, o un typo
    # (`prod`, `devel`), cae del lado seguro y activa las validaciones.
    @property
    def is_production(self) -> bool:
        mode_is_dev = self.MINERVA_MODE.strip().lower() == "dev"
        env_is_dev = self.APP_ENV.strip().lower() in ("dev", "development")
        return not (mode_is_dev and env_is_dev)

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.FRONTEND_URL]
        if not self.is_production and "http://localhost:5173" not in origins:
            origins.append("http://localhost:5173")
        return origins

    # --- Cookie de sesión del panel (BFF) ----------------------------------
    # El panel usa una cookie opaca HttpOnly (solo un id de sesión, nunca el JWT).
    # En producción usa el prefijo `__Host-` (exige Secure + Path=/ + sin Domain,
    # por eso solo funciona sobre HTTPS); en dev HTTP se usa un nombre distinto sin
    # Secure para no romper el desarrollo local, sin debilitar producción.
    @property
    def session_cookie_secure(self) -> bool:
        return self.is_production

    @property
    def session_cookie_name(self) -> str:
        return "__Host-minerva_sid" if self.is_production else "minerva_sid"

    def validate_production_config(self) -> None:
        """Falla rápido al arrancar si la configuración es de producción (ver
        `is_production`) y quedó algún valor de desarrollo sin cambiar. Sin esto,
        Minerva arranca "production-looking" con debug, login de dev o password
        default, sin avisar a nadie."""
        if not self.is_production:
            return
        problems = []
        if self.APP_DEBUG:
            problems.append("APP_DEBUG=true (expone trazas y detalle interno; debe ser false en producción)")
        if self.MINERVA_ENABLE_DEV_LOGIN:
            problems.append("MINERVA_ENABLE_DEV_LOGIN=true (debe ser false en producción)")
        if self.ADMIN_PASSWORD == "changeme123":
            problems.append("ADMIN_PASSWORD sigue en su valor default (changeme123)")
        if "change-me-in-production" in self.SECRET_KEY:
            problems.append("SECRET_KEY sigue en su valor default")
        if "change-me-in-production" in self.JWT_SECRET_KEY:
            problems.append("JWT_SECRET_KEY sigue en su valor default")
        if not self.MINERVA_KEY_ENCRYPTION_KEY:
            problems.append("MINERVA_KEY_ENCRYPTION_KEY vacía (obligatoria fuera de modo dev)")
        # La cookie `__Host-` es host-only: con hosts distintos no viaja al API (401 mudo).
        frontend_host = _public_host(self.FRONTEND_URL)
        for name, url in (("MINERVA_ISSUER", self.MINERVA_ISSUER), ("MINERVA_JWT_ISSUER", self.effective_jwt_issuer)):
            if _public_host(url) != frontend_host:
                problems.append(
                    f"FRONTEND_URL ({self.FRONTEND_URL}) y {name} ({url}) apuntan a hosts públicos "
                    "distintos; la cookie `__Host-` es host-only y el panel no podría autenticarse"
                )
        if problems:
            detail = "\n  - ".join(problems)
            raise RuntimeError(
                f"Configuración insegura para APP_ENV={self.APP_ENV!r} / MINERVA_MODE={self.MINERVA_MODE!r}. "
                f"Corrige antes de arrancar:\n  - {detail}"
            )


settings = Settings()
