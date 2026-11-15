"""API web mínima para probar la conectividad con Azure SQL."""
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse

from app import explorer
from app.db import check_connection, get_connection

log = logging.getLogger("uvicorn.error")
app = FastAPI(title="Azure SQL - Prueba de conectividad")
app.include_router(explorer.router)


@app.get("/")
def root():
    if explorer.enabled():
        return RedirectResponse("/explorar")
    return {"mensaje": "La aplicación está en línea", "probar_bd": "/health/db"}


@app.get("/health")
def health():
    """La app responde (no toca la base de datos)."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    """Verifica que la app puede conectarse a Azure SQL."""
    try:
        return {"status": "ok", **check_connection()}
    except Exception as exc:  # noqa: BLE001
        # El detalle va al log del servidor; al cliente solo se le da el tipo de error.
        log.exception("Fallo al conectar con Azure SQL")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "tipo": type(exc).__name__},
        )


@app.get("/prueba")
def leer_tabla_prueba():
    """Lee la tabla de prueba (créala antes con sql/01_crear_tabla_prueba.sql)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT TOP 50 Id, Nombre, CreadoEn FROM dbo.Prueba ORDER BY Id")
        return [
            {"id": r[0], "nombre": r[1], "creado_en": str(r[2])}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
