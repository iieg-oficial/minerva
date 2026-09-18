import re
from typing import Annotated

from pydantic import AfterValidator


def validate_password_max_bytes(password: str | None) -> str | None:
    """bcrypt (5.x) lanza ValueError con contraseñas de más de 72 bytes UTF-8 en vez
    de truncarlas; se rechaza aquí como 422 antes de llegar al hash/check."""
    if password is not None and len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña no debe superar 72 bytes")
    return password


def validate_password_policy(password: str | None) -> str | None:
    """Política de contraseña nueva (alta por enlace o cambio propio): mínimo 8 caracteres
    y al menos 2 de las 3 familias —mayúscula y minúscula, número, carácter especial—, más
    el tope de bcrypt. Es la misma regla del indicador de fuerza portado de mariachi."""
    if password is None:
        return password
    validate_password_max_bytes(password)
    familias = [
        bool(re.search(r"[a-z]", password)) and bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^A-Za-z0-9]", password)),
    ]
    if len(password) < 8 or sum(familias) < 2:
        raise ValueError(
            "La contraseña debe tener al menos 8 caracteres y al menos 2 de: mayúscula y "
            "minúscula, un número, un carácter especial"
        )
    return password


# Contraseña nueva: política completa (mínimo 8 + 2 de 3 familias + tope de bcrypt).
NewPassword = Annotated[str, AfterValidator(validate_password_policy)]
