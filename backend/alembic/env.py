from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context
from app.core.config import settings
from app.core.models import import_models

import_models()

config = context.config
# La MISMA URL que usa el runtime (`app/core/database.py`). Leer `DATABASE_URL`
# directo hacía que, con `MINERVA_DB_URL` definida, las migraciones se aplicaran
# a una base distinta de la que sirve la aplicación.
config.set_main_option("sqlalchemy.url", settings.effective_db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.effective_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connectable = create_engine(settings.effective_db_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
