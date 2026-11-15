"""Golf Campestre: API + web app instalable, sobre Azure SQL."""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import explorer
from app.db import check_connection, get_connection
from app.golf.api import router as golf_router

log = logging.getLogger("uvicorn.error")
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Golf Campestre", docs_url="/docs", redoc_url=None)
app.include_router(explorer.router)
app.include_router(golf_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(Exception)
async def error_inesperado(request: Request, exc: Exception):
    log.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Error interno. Intenta de nuevo."})


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    # El service worker debe servirse desde la raíz para controlar toda la app.
    return FileResponse(STATIC / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


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
