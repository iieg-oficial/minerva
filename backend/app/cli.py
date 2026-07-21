"""Comandos de mantenimiento operacional, sin necesidad de levantar el servidor HTTP.

Uso (dentro del contenedor backend o con el entorno conda `minerva` activo):
    python -m app.cli rotate-key      # fase 1: publica la clave nueva en el JWKS
    python -m app.cli promote-key     # fase 2: empieza a firmar con ella
"""

import argparse
import logging

from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.core.models import import_models
from app.modules.oidc.service import OIDCService

logger = logging.getLogger("minerva.cli")


def _drop_jwks_cache() -> None:
    """Invalida el JWKS cacheado en Redis. Sin esto el backend seguiría sirviendo el
    JWKS viejo hasta MINERVA_JWKS_CACHE_TTL_SECONDS y rechazaría tokens legítimos.

    No es fatal si falla: `_get_jwks_cached` se auto-sana al ver un `kid` desconocido,
    esto solo evita esperar a que ocurra."""
    import asyncio

    from app.core.dependencies.auth import invalidate_jwks_cache
    from app.core.redis import get_redis

    async def _run() -> None:
        await invalidate_jwks_cache(get_redis())

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - operacional: informar y seguir
        print(f"Aviso: no se pudo invalidar el cache JWKS en Redis ({exc}).")
        print("El backend lo reconstruira solo al ver el kid nuevo; no hace falta reintentar.")


def rotate_key(emergency: bool = False) -> None:
    import_models()
    with Session(engine) as session:
        service = OIDCService(session)
        if emergency:
            key = service.rotate_key_now()
        else:
            key = service.stage_key()
    _drop_jwks_cache()

    if emergency:
        logger.info("Rotacion de emergencia. Nuevo kid activo: %s", key.kid)
        print(f"Rotacion de emergencia: la clave {key.kid} ya esta firmando.")
        print("Los verificadores con el JWKS cacheado pueden rechazar tokens hasta refrescarlo.")
        return

    logger.info("Clave de firma publicada como pendiente: %s", key.kid)
    print(f"Clave {key.kid} publicada en el JWKS (aun no firma nada).")
    print(f"Espera {settings.MINERVA_KEY_PROPAGATION_MINUTES} min y corre: python -m app.cli promote-key")


def promote_key(force: bool = False) -> None:
    import_models()
    with Session(engine) as session:
        key = OIDCService(session).promote_key(force=force)
    _drop_jwks_cache()
    logger.info("Clave de firma promovida. Nuevo kid activo: %s", key.kid)
    print(f"Clave {key.kid} activa: ya firma los tokens nuevos.")
    print(f"La anterior queda retirada y publicada {settings.key_retirement_overlap_minutes} min mas.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Comandos de mantenimiento de Minerva")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rotate = subparsers.add_parser("rotate-key", help="Publica una clave de firma nueva en el JWKS (fase 1)")
    rotate.add_argument(
        "--emergency",
        action="store_true",
        help="Clave comprometida: publica y activa en un solo paso, asumiendo el corte",
    )

    promote = subparsers.add_parser("promote-key", help="Empieza a firmar con la clave pendiente (fase 2)")
    promote.add_argument(
        "--force",
        action="store_true",
        help="Promueve aunque no haya terminado la ventana de propagacion",
    )

    args = parser.parse_args()
    if args.command == "rotate-key":
        rotate_key(emergency=args.emergency)
    elif args.command == "promote-key":
        promote_key(force=args.force)


if __name__ == "__main__":
    main()
