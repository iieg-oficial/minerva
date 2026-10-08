"""Contenedor de sesión del panel (patrón BFF), en Redis.

El panel admin ya NO guarda el JWT en el navegador: el browser solo conserva una
cookie opaca (`__Host-minerva_sid`) con un id de sesión aleatorio. El estado real
—qué cuentas hay iniciadas, cuál está activa, el token interno `typ=session` de
cada una y el token CSRF— vive aquí, en Redis, con TTL igual al de la sesión del
panel. Es la fuente de verdad del selector multi-cuenta.

Esta es la ÚNICA excepción al principio stateless de Minerva, y aplica solo al
panel: OAuth/OIDC de consumidores sigue siendo stateless (Bearer sin estado).

El id de sesión (`sid`) se genera aquí con entropía criptográfica; nunca se acepta
uno provisto por el cliente. En Redis se guarda hasheado (`sha256`), para que ni
con acceso de lectura a Redis se recupere el `sid` en claro.

Forma del contenedor:
    {
      "accounts": { "<sub>": {"token","exp","jti","email","name","is_admin"} },
      "active": "<sub>" | None,
      "csrf": "<token>",
    }
Los JWT internos (`accounts[*].token`) se validan SIEMPRE vía `_resolve_token`
(firma RS256, iss, aud=minerva, typ=session, exp, jti revocado, corte por usuario):
este módulo administra el contenedor, no valida tokens.
"""

import hashlib
import hmac
import json
import secrets
import time

from redis.asyncio import Redis

from app.core.config import settings

_PREFIX = "minerva:psid:"
# 32 bytes url-safe ≈ 256 bits de entropía, tanto para el sid como para el CSRF.
_ENTROPY_BYTES = 32


def _key(sid: str) -> str:
    """Clave Redis a partir del sid, hasheada: quien lea Redis no obtiene el sid."""
    return f"{_PREFIX}{hashlib.sha256(sid.encode()).hexdigest()}"


def _ttl_seconds() -> int:
    return settings.effective_token_expire_minutes * 60


def new_sid() -> str:
    return secrets.token_urlsafe(_ENTROPY_BYTES)


def new_csrf() -> str:
    return secrets.token_urlsafe(_ENTROPY_BYTES)


def empty_container() -> dict:
    return {"accounts": {}, "active": None, "csrf": new_csrf()}


# --- Redis -----------------------------------------------------------------


async def read(redis: Redis, sid: str | None) -> dict | None:
    if not sid:
        return None
    raw = await redis.get(_key(sid))
    return json.loads(raw) if raw is not None else None


async def write(redis: Redis, sid: str, container: dict) -> None:
    await redis.set(_key(sid), json.dumps(container), ex=_ttl_seconds())


async def destroy(redis: Redis, sid: str | None) -> None:
    if sid:
        await redis.delete(_key(sid))


async def rotate_sid(redis: Redis, old_sid: str | None, container: dict) -> str:
    """Emite un sid nuevo con el mismo contenedor y borra el viejo (queda inválido).

    Se llama en cada autenticación o cambio de privilegios (fijación de sesión):
    el atacante que conociera el sid previo no puede reutilizarlo tras el login."""
    sid = new_sid()
    await write(redis, sid, container)
    if old_sid and old_sid != sid:
        await destroy(redis, old_sid)
    return sid


# --- Operaciones sobre el contenedor (puras) -------------------------------


def add_account(
    container: dict, sub: str, token: str, *, email: str, name: str, is_admin: bool, exp: int, jti: str | None = None
) -> None:
    """Agrega o reemplaza una cuenta y la deja activa. Guarda `jti` para poder
    revocar el token al quitar la cuenta o cerrar todas las sesiones, sin re-decodificar."""
    container["accounts"][sub] = {
        "token": token,
        "exp": exp,
        "jti": jti,
        "email": email,
        "name": name,
        "is_admin": is_admin,
    }
    container["active"] = sub


def has_live_token(account: dict) -> bool:
    """Si la cuenta conserva un token no vencido. No valida firma ni revocación: eso lo
    hace `_resolve_token`; aquí solo se descarta lo que seguro ya no sirve."""
    return bool(account.get("token")) and not is_expired(account)


def set_active(container: dict, sub: str) -> bool:
    """Activa una cuenta del contenedor solo si su sesión sigue viva. Una cuenta cerrada o
    vencida se reactiva únicamente iniciando sesión con contraseña."""
    account = container["accounts"].get(sub)
    if account is None or not has_live_token(account):
        return False
    container["active"] = sub
    return True


def sign_out(container: dict, sub: str) -> dict | None:
    """Cierra la sesión de una cuenta sin quitarla del selector: descarta su token y la
    deja vencida, así que volver a ella pide contraseña. Devuelve el registro previo para
    que el caller revoque su `jti`. Si era la activa, el contenedor queda sin activa."""
    account = container["accounts"].get(sub)
    if account is None:
        return None
    previous = dict(account)
    account.update(token=None, jti=None, exp=0)
    if container.get("active") == sub:
        container["active"] = None
    return previous


def remove_account(container: dict, sub: str) -> dict | None:
    """Quita una cuenta y devuelve su registro (para que el caller revoque su jti).
    Si era la activa, pasa a otra no expirada o deja sin activa."""
    account = container["accounts"].pop(sub, None)
    if container.get("active") == sub:
        container["active"] = next(
            (s for s, a in container["accounts"].items() if has_live_token(a)),
            None,
        )
    return account


def active_token(container: dict) -> str | None:
    active = container.get("active")
    if not active:
        return None
    account = container["accounts"].get(active)
    return account["token"] if account else None


def rotate_csrf(container: dict) -> None:
    container["csrf"] = new_csrf()


def csrf_valid(container: dict, header_value: str | None) -> bool:
    return bool(header_value) and hmac.compare_digest(container.get("csrf", ""), header_value)


# --- Vistas no sensibles (nunca exponen el JWT al navegador) ----------------


def is_expired(account: dict) -> bool:
    exp = account.get("exp") or 0
    return exp <= int(time.time())


def descriptor(sub: str, account: dict) -> dict:
    return {
        "sub": sub,
        "email": account.get("email", ""),
        "name": account.get("name", ""),
        "is_admin": bool(account.get("is_admin")),
        "exp": account.get("exp", 0),
        "expired": not has_live_token(account),
        "signed_out": not account.get("token"),
    }


def session_view(container: dict) -> dict:
    """Descriptores de todas las cuentas + activa + csrf, para el selector del panel."""
    accounts = [descriptor(sub, acc) for sub, acc in container["accounts"].items()]
    active = container.get("active")
    return {
        "accounts": accounts,
        "active": descriptor(active, container["accounts"][active]) if active else None,
        "csrf": container.get("csrf", ""),
    }


if __name__ == "__main__":
    import asyncio

    # Self-check sin dependencias: cubre la lógica ramificada (add/set/remove/soft
    # logout, csrf constante y rotación de sid que invalida el anterior).
    c = empty_container()
    add_account(c, "u1", "tok1", email="u1@x", name="U1", is_admin=True, exp=int(time.time()) + 999)
    add_account(c, "u2", "tok2", email="u2@x", name="U2", is_admin=False, exp=0)  # expirada
    assert c["active"] == "u2"
    assert set_active(c, "u1") and c["active"] == "u1"
    assert not set_active(c, "nope")
    assert active_token(c) == "tok1"
    assert descriptor("u2", c["accounts"]["u2"])["expired"] is True
    assert descriptor("u1", c["accounts"]["u1"])["expired"] is False

    assert not set_active(c, "u2")  # vencida: no se reactiva sin contraseña
    add_account(c, "u3", "tok3", email="u3@x", name="U3", is_admin=False, exp=int(time.time()) + 999)
    closed = sign_out(c, "u3")
    assert closed["token"] == "tok3" and c["active"] is None and "u3" in c["accounts"]  # sigue en el selector
    assert descriptor("u3", c["accounts"]["u3"])["signed_out"] is True
    assert not set_active(c, "u3")  # cerrada: pide contraseña

    set_active(c, "u1")
    removed = remove_account(c, "u1")  # era activa; u2 y u3 no están vivas → sin activa
    assert removed["token"] == "tok1" and c["active"] is None

    assert csrf_valid(c, c["csrf"]) and not csrf_valid(c, "otro") and not csrf_valid(c, None)

    class _FakeRedis:
        def __init__(self):
            self.store = {}

        async def get(self, k):
            return self.store.get(k)

        async def set(self, k, v, ex=None):
            self.store[k] = v

        async def delete(self, k):
            self.store.pop(k, None)

    async def _redis_check():
        r = _FakeRedis()
        sid = new_sid()
        await write(r, sid, empty_container())
        assert await read(r, sid) is not None
        new = await rotate_sid(r, sid, await read(r, sid))
        assert new != sid
        assert await read(r, sid) is None  # el sid viejo quedó inválido
        assert await read(r, new) is not None

    asyncio.run(_redis_check())
    print("panel_session self-check OK")
