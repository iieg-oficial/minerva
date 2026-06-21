"""Endpoints públicos de descubrimiento OIDC (`.well-known`).

Se exponen en una **sub-app FastAPI propia** y no como un router más de la app
principal por una razón concreta de CORS: estos endpoints deben poder leerse desde
cualquier origen (`allow_origins=["*"]`) para que cualquier consumidor o SPA pueda
descubrir la configuración y las claves. Esa política es incompatible con
`allow_credentials=True`, que sí usa la app principal. Aislándolos en una sub-app,
cada una mantiene su propia política de CORS sin contaminar a la otra.

La sub-app se monta en `app/main.py` con `app.mount("/.well-known", wellknown_app)`.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.core.config import settings
from app.core.dependencies.db import get_db
from app.modules.oidc.schemas import JWKS, OpenIDConfiguration
from app.modules.oidc.service import OIDCService


def get_oidc_service(session: Session = Depends(get_db)) -> OIDCService:
    return OIDCService(session)


def _build_discovery() -> OpenIDConfiguration:
    """Arma el documento de descubrimiento a partir del issuer configurado."""
    issuer = settings.effective_jwt_issuer.rstrip("/")
    return OpenIDConfiguration(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/auth/authorize",
        token_endpoint=f"{issuer}/auth/token",
        jwks_uri=f"{issuer}/.well-known/jwks.json",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code"],
        subject_types_supported=["public"],
        id_token_signing_alg_values_supported=["RS256"],
        scopes_supported=["openid", "profile", "email"],
        token_endpoint_auth_methods_supported=["client_secret_post"],
        claims_supported=["sub", "iss", "aud", "exp", "iat", "email", "name", "roles", "permissions"],
    )


# Sub-app dedicada a los endpoints públicos `.well-known` (solo lectura, sin
# credenciales). Sin docs propias: no expone OpenAPI.
wellknown_app = FastAPI(
    title="Minerva OIDC Discovery",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

wellknown_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@wellknown_app.get("/openid-configuration", response_model=OpenIDConfiguration)
def openid_configuration() -> OpenIDConfiguration:
    """OpenID Connect Discovery: configuración del proveedor de identidad."""
    return _build_discovery()


@wellknown_app.get("/jwks.json", response_model=JWKS)
def jwks(service: OIDCService = Depends(get_oidc_service)) -> JWKS:
    """JWKS: claves públicas para que los consumidores verifiquen la firma RS256."""
    return JWKS(**service.build_jwks())
