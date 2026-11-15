"""Conexión segura a Azure SQL Database.

- Siempre cifrada (TLS) y validando el certificado del servidor.
- Credenciales leídas de variables de entorno, nunca escritas en el código.
- Dos formas de conectarse (variable SQL_DRIVER):
    odbc  -> ODBC Driver 18 de Microsoft (por defecto; ideal en Azure App Service / Linux / Windows)
    pytds -> 100% Python, sin driver ODBC (útil en Mac si el driver ODBC da problemas con OpenSSL)
- Autenticación con usuario/contraseña SQL o Microsoft Entra ID (solo con odbc).
"""
import os
import struct
from pathlib import Path

from dotenv import load_dotenv

# Carga el .env de la carpeta raíz del proyecto, sin importar desde dónde se ejecute.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Atributo ODBC para pasar un token de acceso de Entra ID.
SQL_COPT_SS_ACCESS_TOKEN = 1256


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name}. Revisa tu archivo .env")
    return value


def _driver() -> str:
    return os.getenv("SQL_DRIVER", "odbc").lower()


def _auth() -> str:
    return os.getenv("AZURE_SQL_AUTH", "sql").lower()


# ---------- ODBC (Microsoft ODBC Driver 18) ----------

def _odbc_connection_string() -> str:
    server = _env("AZURE_SQL_SERVER")
    port = os.getenv("AZURE_SQL_PORT", "1433")
    parts = [
        f"Driver={{{_env('ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')}}}",
        f"Server=tcp:{server},{port}",
        f"Database={_env('AZURE_SQL_DATABASE')}",
        "Encrypt=yes",
        "TrustServerCertificate=no",
        "Connection Timeout=30",
    ]
    if _auth() == "sql":
        parts += [f"Uid={_env('AZURE_SQL_USER')}", f"Pwd={{{_env('AZURE_SQL_PASSWORD')}}}"]
    return ";".join(parts) + ";"


def _entra_token() -> bytes:
    """Obtiene un token de Entra ID (identidad administrada en Azure, o az login en local)."""
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    raw = token.encode("utf-16-le")
    return struct.pack(f"<I{len(raw)}s", len(raw), raw)


def _connect_odbc():
    import pyodbc

    # Reutiliza conexiones entre peticiones (más rápido que abrir una nueva cada vez).
    pyodbc.pooling = True
    if _auth() == "entra":
        return pyodbc.connect(
            _odbc_connection_string(), attrs_before={SQL_COPT_SS_ACCESS_TOKEN: _entra_token()}
        )
    return pyodbc.connect(_odbc_connection_string())


# ---------- pytds (100% Python) ----------

def _connect_pytds():
    import certifi
    import pytds

    if _auth() != "sql":
        raise RuntimeError("SQL_DRIVER=pytds solo admite AZURE_SQL_AUTH=sql")
    return pytds.connect(
        dsn=_env("AZURE_SQL_SERVER"),
        port=int(os.getenv("AZURE_SQL_PORT", "1433")),
        database=_env("AZURE_SQL_DATABASE"),
        user=_env("AZURE_SQL_USER"),
        password=_env("AZURE_SQL_PASSWORD"),
        # Cifrado TLS obligatorio validando el certificado y el nombre del servidor.
        cafile=certifi.where(),
        validate_host=True,
        enc_login_only=False,
        login_timeout=30,
    )


def get_connection():
    return _connect_pytds() if _driver() == "pytds" else _connect_odbc()


def check_connection() -> dict:
    """Ejecuta una consulta mínima y devuelve datos del servidor."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DB_NAME(), SUSER_SNAME(), "
            "CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(50)), "
            "CONVERT(nvarchar(40), SYSDATETIMEOFFSET(), 127)"
        )
        row = cur.fetchone()
        return {
            "base_de_datos": row[0],
            "usuario": row[1],
            "version": row[2],
            "hora_servidor": row[3],
            "driver": _driver(),
        }
    finally:
        conn.close()
