"""Autenticación sencilla y segura sin dependencias extra.

- Administrador: contraseña en la variable ADMIN_PASSWORD.
- Capturistas: PIN de 6 dígitos de su grupo (solo pueden capturar ese grupo).
- Se entrega un token firmado con HMAC-SHA256 (SECRET_KEY) que expira.
- Límite de intentos por IP para evitar adivinar contraseña o PIN.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

log = logging.getLogger("uvicorn.error")

_SECRET = os.getenv("SECRET_KEY") or ""
if not _SECRET:
    _SECRET = secrets.token_hex(32)
    log.warning("SECRET_KEY no configurada: se generó una temporal (las sesiones se pierden al reiniciar)")
_KEY = _SECRET.encode()

ADMIN_HORAS = 12
GRUPO_HORAS = 16


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def crear_token(datos: dict, horas: int) -> str:
    payload = _b64(json.dumps({**datos, "exp": int(time.time()) + horas * 3600}).encode())
    firma = _b64(hmac.new(_KEY, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{firma}"


def leer_token(token: str) -> dict | None:
    try:
        payload, firma = token.split(".", 1)
        esperado = _b64(hmac.new(_KEY, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperado):
            return None
        datos = json.loads(_unb64(payload))
        return datos if datos.get("exp", 0) > time.time() else None
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------- límite de intentos
_intentos: dict[str, deque] = defaultdict(deque)
MAX_INTENTOS = 10
VENTANA_SEG = 300


def _contar(clave: str, maximo: int) -> None:
    q = _intentos[clave]
    ahora = time.time()
    while q and q[0] < ahora - VENTANA_SEG:
        q.popleft()
    if len(q) >= maximo:
        raise HTTPException(429, "Demasiados intentos. Espera unos minutos.")
    q.append(ahora)


def limitar(request: Request, tipo: str, global_max: int = 60) -> None:
    """Máximo de intentos por IP y, además, en total para ese tipo (evita rotar IPs)."""
    # En Azure el proxy agrega la IP real AL FINAL de X-Forwarded-For.
    xff = request.headers.get("x-forwarded-for")
    ip = xff.split(",")[-1].strip() if xff else (request.client.host if request.client else "?")
    _contar(f"{tipo}:global", global_max)
    _contar(f"{tipo}:{ip}", MAX_INTENTOS)


def verificar_admin_password(password: str) -> bool:
    real = os.getenv("ADMIN_PASSWORD", "")
    if not real:
        raise HTTPException(503, "El administrador no está configurado (falta ADMIN_PASSWORD).")
    return hmac.compare_digest(password.encode(), real.encode())


def _token_de(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Inicia sesión")
    datos = leer_token(authorization[7:])
    if not datos:
        raise HTTPException(401, "Sesión vencida o inválida. Vuelve a entrar.")
    return datos


def requiere_admin(authorization: str | None = Header(None)) -> dict:
    datos = _token_de(authorization)
    if datos.get("r") != "admin":
        raise HTTPException(403, "Solo el administrador")
    return datos


def requiere_grupo(authorization: str | None = Header(None)) -> dict:
    datos = _token_de(authorization)
    if datos.get("r") != "grupo":
        raise HTTPException(403, "Necesitas el PIN del grupo")
    return datos


def nuevo_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
