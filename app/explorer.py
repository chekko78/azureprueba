"""Explorador web de SOLO LECTURA para la base de datos (pensado para uso local).

Se activa con ENABLE_DB_BROWSER=true (valor por defecto en local).
En el servidor web se deja desactivado hasta que la app tenga inicio de sesión.
"""
import html
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.db import get_connection

router = APIRouter()


def enabled() -> bool:
    return os.getenv("ENABLE_DB_BROWSER", "true").lower() == "true"


def _q(name: str) -> str:
    """Escapa un identificador SQL con corchetes: mi]tabla -> [mi]]tabla]."""
    return "[" + name.replace("]", "]]") + "]"


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #f5f7fa; color: #1f2937; }}
  header {{ background: #0f4c81; color: #fff; padding: 14px 24px; }}
  header a {{ color: #fff; text-decoration: none; font-weight: 600; }}
  main {{ padding: 24px; max-width: 1200px; margin: auto; }}
  .card {{ background: #fff; border-radius: 10px; padding: 18px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 18px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #e5e7eb; white-space: nowrap; }}
  th {{ background: #eef2f7; position: sticky; top: 0; }}
  tr:hover td {{ background: #f9fbff; }}
  .scroll {{ overflow: auto; max-height: 70vh; }}
  .muted {{ color: #6b7280; font-size: 13px; }}
  .ok {{ color: #047857; font-weight: 600; }}
  .null {{ color: #9ca3af; font-style: italic; }}
  a {{ color: #0f4c81; }}
</style></head>
<body><header><a href="/explorar">🗄️ Explorador de base de datos</a></header>
<main>{body}</main></body></html>""")


def _tables(cur) -> list[tuple[str, str]]:
    cur.execute(
        "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW') ORDER BY TABLE_SCHEMA, TABLE_NAME"
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


@router.get("/explorar", response_class=HTMLResponse, include_in_schema=False)
def lista_tablas():
    if not enabled():
        raise HTTPException(404)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DB_NAME(), SUSER_SNAME()")
        db, user = cur.fetchone()
        tablas = _tables(cur)
    finally:
        conn.close()

    filas = "".join(
        f'<tr><td>{html.escape(s)}</td><td><a href="/explorar/{html.escape(s)}/{html.escape(t)}">'
        f"{html.escape(t)}</a></td></tr>"
        for s, t in tablas
    ) or '<tr><td colspan="2" class="muted">La base no tiene tablas todavía.</td></tr>'
    return _page("Tablas", f"""
<div class="card"><span class="ok">● Conectado</span> &nbsp; Base: <b>{html.escape(db)}</b>
 &nbsp;·&nbsp; Usuario: <b>{html.escape(user)}</b>
 <div class="muted">Modo solo lectura. Las tablas se listan según los permisos del usuario.</div></div>
<div class="card"><h2>Tablas ({len(tablas)})</h2>
<table><tr><th>Esquema</th><th>Tabla</th></tr>{filas}</table></div>""")


@router.get("/explorar/{schema}/{table}", response_class=HTMLResponse, include_in_schema=False)
def ver_tabla(schema: str, table: str, limite: int = Query(100, ge=1, le=1000)):
    if not enabled():
        raise HTTPException(404)
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Solo se permiten tablas que existen (evita inyección de SQL en el nombre).
        if (schema, table) not in set(_tables(cur)):
            raise HTTPException(404, "La tabla no existe")
        cur.execute(f"SELECT TOP ({int(limite)}) * FROM {_q(schema)}.{_q(table)}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    def cell(v):
        return '<td class="null">NULL</td>' if v is None else f"<td>{html.escape(str(v))}</td>"

    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(cell(v) for v in r) + "</tr>" for r in rows)
    opciones = " · ".join(
        f'<a href="?limite={n}">{n}</a>' if n != limite else f"<b>{n}</b>" for n in (100, 500, 1000)
    )
    return _page(f"{schema}.{table}", f"""
<p><a href="/explorar">← Todas las tablas</a></p>
<div class="card"><h2>{html.escape(schema)}.{html.escape(table)}</h2>
<div class="muted">Mostrando {len(rows)} registro(s) · máximo: {opciones}</div><br>
<div class="scroll"><table><tr>{head}</tr>{body}</table></div></div>""")
