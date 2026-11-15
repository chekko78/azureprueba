"""Ayudante para consultas parametrizadas que funciona con ambos drivers (odbc y pytds).

Las consultas se escriben con '?' como marcador; para pytds se convierten a '%s'.
Nunca se arma SQL concatenando valores del usuario.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

from app.db import _driver, get_connection


def _adapt(sql: str) -> str:
    if _driver() == "pytds":
        return sql.replace("%", "%%").replace("?", "%s")
    return sql


def _valor(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


class Tx:
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()

    def all(self, sql: str, params: tuple | list = ()) -> list[dict]:
        self.cur.execute(_adapt(sql), tuple(params))
        cols = [d[0] for d in self.cur.description]
        return [dict(zip(cols, map(_valor, r))) for r in self.cur.fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def run(self, sql: str, params: tuple | list = ()) -> int:
        self.cur.execute(_adapt(sql), tuple(params))
        return self.cur.rowcount

    def insert(self, sql: str, params: tuple | list = ()) -> int:
        """Para INSERT ... OUTPUT INSERTED.Id VALUES (...)."""
        self.cur.execute(_adapt(sql), tuple(params))
        return int(self.cur.fetchone()[0])


@contextmanager
def tx():
    """Abre conexión y transacción; confirma al terminar o revierte si hay error."""
    conn = get_connection()
    try:
        t = Tx(conn)
        yield t
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
