"""Comandos de mantenimiento operacional, sin necesidad de levantar el servidor HTTP.

Uso (dentro del contenedor backend o con el entorno conda `minerva` activo):
    python -m app.cli rotate-key         # fase 1: publica la clave nueva en el JWKS
    python -m app.cli promote-key        # fase 2: empieza a firmar con ella
    python -m app.cli revoke-key KID     # simula la retirada de una clave comprometida
    python -m app.cli import-manifests   # importa los manifiestos del arranque
"""

import argparse
import logging
import sys
from pathlib import Path

from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.core.models import import_models
from app.modules.oidc.service import OIDCService

logger = logging.getLogger("minerva.cli")


def _drop_jwks_cache(strict: bool = False) -> bool:
    """Invalida el JWKS cacheado en Redis. Sin esto el backend seguiría sirviendo el
    JWKS viejo hasta MINERVA_JWKS_CACHE_TTL_SECONDS y rechazaría tokens legítimos.

    No es fatal si falla: `_get_jwks_cached` se auto-sana al ver un `kid` desconocido,
    esto solo evita esperar a que ocurra."""
    import asyncio

    from app.core.dependencies.auth import invalidate_jwks_cache
    from app.core.redis import close_redis, init_redis

    async def _run() -> None:
        # El CLI no pasa por el lifespan de FastAPI: hay que abrir y cerrar la
        # conexión aquí, o `get_redis()` falla por no estar inicializada.
        redis = await init_redis()
        try:
            await invalidate_jwks_cache(redis)
        finally:
            await close_redis()

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - operacional: informar y seguir
        print(f"Aviso: no se pudo invalidar el cache JWKS en Redis ({exc}).")
        if strict:
            print("Repite el comando: el kid ya no se publica, pero el cache debe invalidarse.")
        else:
            print("El backend lo reconstruira solo al ver el kid nuevo; no hace falta reintentar.")
        return False
    return True


def rotate_key() -> None:
    import_models()
    with Session(engine) as session:
        key = OIDCService(session).stage_key()
    _drop_jwks_cache()

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


def revoke_key(kid: str | None, confirm: str | None = None) -> int:
    """Lista o retira un kid comprometido. Sin confirmación solo muestra el impacto."""
    import_models()
    with Session(engine) as session:
        service = OIDCService(session)
        if kid is None:
            for key in service.repo.list_publishable():
                print(f"{key.kid}\t{key.status}\tcreada={key.created_at.isoformat()}")
            return 0

        compromised = service.repo.get_by_kid(kid)
        if compromised is None:
            if confirm == kid and _drop_jwks_cache(strict=True):
                print(f"El kid {kid} ya no existe; cache JWKS invalidado.")
                return 0
            print(f"ERROR: no existe el kid {kid}.")
            return 1

        print(f"Impacto: retirar {kid} ({compromised.status}) invalida inmediatamente sus tokens tras refrescar JWKS.")
        if compromised.status == "active":
            pending = service.repo.get_pending()
            action = f"promover {pending.kid}" if pending else "crear y promover una clave nueva"
            print(f"La clave comprometida esta activa: se va a {action} antes de eliminarla.")
        if confirm is None:
            print(f"DRY-RUN: para ejecutar, agrega --confirm {kid}")
            return 0
        if confirm != kid:
            print("ERROR: --confirm debe repetir exactamente el kid comprometido.")
            return 1

        active = service.revoke_compromised_key(kid)

    if not _drop_jwks_cache(strict=True):
        return 1
    logger.warning("Clave de firma comprometida retirada: %s; active=%s", kid, active.kid)
    print(f"Kid {kid} retirado. Nueva clave activa: {active.kid}.")
    return 0


def import_manifests() -> int:
    """Importa los manifiestos de `MINERVA_MANIFESTS_PATH`. Devuelve 1 si alguno falló.

    Es un paso ÚNICO del arranque (`scripts/backend-entrypoint.sh`, antes de levantar
    los workers). Vivía en el lifespan de FastAPI, así que con gunicorn corría una vez
    por worker y cada fallo quedaba en un `logger.warning` que nadie mira.
    """
    from app.modules.devkit.service import DevKitService

    if not settings.MINERVA_AUTO_IMPORT_MANIFESTS:
        print("Autoimport deshabilitado (MINERVA_AUTO_IMPORT_MANIFESTS=false); no se importa nada.")
        return 0

    manifests_dir = Path(settings.MINERVA_MANIFESTS_PATH)
    if not manifests_dir.exists():
        print(f"Sin manifiestos que importar: {manifests_dir} no existe.")
        return 0

    import_models()
    patterns = ("*.minerva.yml", "*.minerva.yaml", "manifest.yml", "manifest.yaml")
    files = sorted({path for pattern in patterns for path in manifests_dir.glob(pattern)})

    failures: list[str] = []
    for path in files:
        try:
            with Session(engine) as session:
                result = DevKitService(session).import_manifest(path.read_text(encoding="utf-8"), path.name)
            logger.info("Manifiesto importado: %s (app=%s)", path.name, result.application_code)
            print(f"Manifiesto importado: {path.name} (app={result.application_code})")
        except Exception as exc:  # noqa: BLE001 - se reportan todos, no solo el primero
            failures.append(f"{path.name}: {exc}")

    for failure in failures:
        print(f"ERROR: no se pudo importar el manifiesto {failure}")
    if failures:
        print(f"{len(failures)} de {len(files)} manifiestos fallaron; el arranque no debe continuar.")
        return 1
    print(f"{len(files)} manifiesto(s) importado(s) desde {manifests_dir}.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Comandos de mantenimiento de Minerva")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("rotate-key", help="Publica una clave de firma nueva en el JWKS (fase 1)")

    promote = subparsers.add_parser("promote-key", help="Empieza a firmar con la clave pendiente (fase 2)")
    promote.add_argument(
        "--force",
        action="store_true",
        help="Promueve aunque no haya terminado la ventana de propagacion",
    )

    revoke = subparsers.add_parser("revoke-key", help="Retira de emergencia un kid comprometido")
    revoke.add_argument("kid", nargs="?", help="Kid comprometido; omitir para listar claves")
    revoke.add_argument("--confirm", metavar="KID", help="Debe repetir exactamente el kid que se eliminara")

    subparsers.add_parser("import-manifests", help="Importa los manifiestos de MINERVA_MANIFESTS_PATH")

    args = parser.parse_args()
    if args.command == "rotate-key":
        rotate_key()
    elif args.command == "promote-key":
        promote_key(force=args.force)
    elif args.command == "revoke-key":
        sys.exit(revoke_key(args.kid, confirm=args.confirm))
    elif args.command == "import-manifests":
        sys.exit(import_manifests())


if __name__ == "__main__":
    main()
