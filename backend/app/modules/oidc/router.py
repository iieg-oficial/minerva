"""Endpoints públicos de descubrimiento OIDC (`.well-known`).

Se exponen en una **sub-app FastAPI propia** y no como un router más de la app
principal por una razón concreta de CORS: estos endpoints deben poder leerse desde
cualquier origen (`allow_origins=["*"]`) para que cualquier consumidor o SPA pueda
descubrir la configuración y las claves. Esa política es incompatible con
`allow_credentials=True`, que sí usa la app principal. Aislándolos en una sub-app,
cada una mantiene su propia política de CORS sin contaminar a la otra.

La sub-app se monta en `app/main.py` con `app.mount("/.well-known", wellknown_app)`.
"""

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.core.config import settings
from app.core.dependencies.auth import get_current_access_user
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
        userinfo_endpoint=f"{issuer}/userinfo",
        jwks_uri=f"{issuer}/.well-known/jwks.json",
        revocation_endpoint=f"{issuer}/auth/revoke",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        subject_types_supported=["public"],
        id_token_signing_alg_values_supported=["RS256"],
        scopes_supported=["openid", "profile", "email"],
        token_endpoint_auth_methods_supported=["client_secret_post", "none"],
        code_challenge_methods_supported=["S256"],
        claims_supported=[
            "sub",
            "iss",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "name",
            "preferred_username",
            "email",
            "email_verified",
            "nonce",
        ],
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
def jwks(response: Response, service: OIDCService = Depends(get_oidc_service)) -> JWKS:
    """JWKS: claves públicas para que los consumidores verifiquen la firma RS256.

    El `max-age` declara a los verificadores la misma ventana de propagación que
    Minerva asume al promover una clave pendiente: si respetan la cabecera, para
    cuando la clave nueva empiece a firmar ya la tienen cacheada."""
    response.headers["Cache-Control"] = f"public, max-age={settings.MINERVA_KEY_PROPAGATION_MINUTES * 60}"
    return JWKS(**service.build_jwks())


# Sub-app dedicada a `/userinfo` (OIDC Core 5.3), con el mismo CORS abierto que
# `wellknown_app` por la misma razón: el Bearer viaja en el header `Authorization`
# (no en cookies), así que `allow_credentials=False` no limita a ningún consumidor
# legítimo. Vive fuera de `/.well-known` porque por convención OIDC `userinfo_endpoint`
# cuelga de la raíz del issuer, no del path de discovery.
userinfo_app = FastAPI(
    title="Minerva UserInfo",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

userinfo_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    # Los dos métodos que OIDC Core 5.3 exige: sin el POST aquí, el preflight lo
    # rechazaría desde navegador y el endpoint solo sería equivalente server-to-server.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _userinfo_claims(payload: dict) -> dict:
    """Filtra los claims de identidad del access token por el `scope` con el que
    se emitió (OIDC Core 5.4). El access token ya lleva `name`/`email`/
    `email_verified` calculados al emitirse (ver `AuthService._issue_tokens`), así
    que no hace falta volver a consultar la BD."""
    scopes = set(payload.get("scope", "").split())
    claims = {"sub": payload["sub"]}
    if "profile" in scopes:
        claims["name"] = payload.get("name")
        claims["preferred_username"] = payload.get("email")
    if "email" in scopes:
        claims["email"] = payload.get("email")
        claims["email_verified"] = payload.get("email_verified", False)
    return claims


@userinfo_app.get("")
@userinfo_app.get("/")
@userinfo_app.post("")
@userinfo_app.post("/")
def userinfo(current_user: dict = Depends(get_current_access_user)) -> dict:
    """OIDC UserInfo (Core 5.3): claims de identidad filtrados por el scope del
    access token presentado como Bearer. Los dos métodos que exige la spec resuelven
    con la misma función: el token siempre viaja en el header `Authorization`, así que
    el POST no cambia nada más que el verbo."""
    return _userinfo_claims(current_user)
