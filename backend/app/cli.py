"""Comandos de mantenimiento operacional, sin necesidad de levantar el servidor HTTP.

Uso (dentro del contenedor backend o con el entorno conda `minerva` activo):
    python -m app.cli rotate-key
"""

import argparse
import logging

from sqlmodel import Session

from app.core.database import engine
from app.core.models import import_models
from app.modules.oidc.service import OIDCService

logger = logging.getLogger("minerva.cli")


def rotate_key() -> None:
    import_models()
    with Session(engine) as session:
        new_key = OIDCService(session).rotate_key()
    logger.info("Clave de firma rotada. Nuevo kid activo: %s", new_key.kid)
    print(f"Clave de firma rotada. Nuevo kid activo: {new_key.kid}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Comandos de mantenimiento de Minerva")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("rotate-key", help="Retira la clave de firma activa, genera una nueva y purga retiradas")

    args = parser.parse_args()
    if args.command == "rotate-key":
        rotate_key()


if __name__ == "__main__":
    main()
