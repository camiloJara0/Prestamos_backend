"""Utilidades compartidas de los routers del Backoffice."""

from typing import Optional

from fastapi import Request

from app.core.observabilidad import obtener_request_id


def contexto_request(request: Optional[Request]) -> dict:
    """ip / user-agent / request-id para auditoría (mejor esfuerzo)."""
    if request is None:
        return {"ip_address": None, "user_agent": None, "request_id": None}
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": obtener_request_id(),
    }


def admin_id(usuario: dict) -> Optional[int]:
    """ID numérico del admin autenticado (payload del token)."""
    try:
        valor = usuario.get("id")
        return int(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
