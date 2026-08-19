"""Almacén en memoria; un consumidor real puede sustituirlo por Redis o su BD."""

pending: dict[str, str] = {}
sessions: dict[str, dict] = {}
