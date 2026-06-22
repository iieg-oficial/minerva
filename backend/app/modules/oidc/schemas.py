from pydantic import BaseModel


class OpenIDConfiguration(BaseModel):
    """Documento de descubrimiento OIDC (OpenID Connect Discovery 1.0 / RFC 8414).

    Es un **contrato público estable**: los consumidores (y su SDK) lo leen para
    auto-configurarse. Por eso solo se AGREGAN campos en el futuro, nunca se
    renombran ni se eliminan. Así, cambios internos de Minerva (rotación de
    claves, endpoints nuevos) no obligan a los consumidores a refactorizar.
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    response_types_supported: list[str]
    grant_types_supported: list[str]
    subject_types_supported: list[str]
    id_token_signing_alg_values_supported: list[str]
    scopes_supported: list[str]
    token_endpoint_auth_methods_supported: list[str]
    code_challenge_methods_supported: list[str]
    claims_supported: list[str]


class JWKS(BaseModel):
    """JSON Web Key Set (RFC 7517): claves públicas para verificar la firma de los
    tokens. Solo material público (nunca la clave privada)."""

    keys: list[dict]
