from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Normaliza a UTC un timestamp leído de la base.

    Las columnas sin timezone devuelven `datetime` naive; el proyecto siempre guarda
    UTC, así que asumirlo al leer evita dos trampas: comparar naive contra aware (que
    lanza TypeError) y llamar `.timestamp()` sobre un naive, que lo interpretaría como
    hora local y desplazaría el valor por el offset del servidor."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
