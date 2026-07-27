def validate_password_max_bytes(password: str | None) -> str | None:
    """bcrypt (5.x) lanza ValueError con contraseñas de más de 72 bytes UTF-8 en vez
    de truncarlas; se rechaza aquí como 422 antes de llegar al hash/check."""
    if password is not None and len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña no debe superar 72 bytes")
    return password
