"""Conexión segura a Azure SQL Database.

- Siempre cifrada (Encrypt=yes) y validando el certificado del servidor.
- Credenciales leídas de variables de entorno, nunca escritas en el código.
- Soporta usuario/contraseña SQL o Microsoft Entra ID (identidad administrada).
"""
import os
import struct

import pyodbc
from dotenv import load_dotenv

load_dotenv()

# Reutiliza conexiones entre peticiones (más rápido que abrir una nueva cada vez).
pyodbc.pooling = True

# Atributo ODBC para pasar un token de acceso de Entra ID.
SQL_COPT_SS_ACCESS_TOKEN = 1256


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name}. Revisa tu archivo .env")
    return value


def _connection_string() -> str:
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
    if os.getenv("AZURE_SQL_AUTH", "sql").lower() == "sql":
        parts += [f"Uid={_env('AZURE_SQL_USER')}", f"Pwd={{{_env('AZURE_SQL_PASSWORD')}}}"]
    return ";".join(parts) + ";"


def _entra_token() -> bytes:
    """Obtiene un token de Entra ID (identidad administrada en Azure, o az login en local)."""
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    raw = token.encode("utf-16-le")
    return struct.pack(f"<I{len(raw)}s", len(raw), raw)


def get_connection() -> pyodbc.Connection:
    if os.getenv("AZURE_SQL_AUTH", "sql").lower() == "entra":
        return pyodbc.connect(
            _connection_string(), attrs_before={SQL_COPT_SS_ACCESS_TOKEN: _entra_token()}
        )
    return pyodbc.connect(_connection_string())


def check_connection() -> dict:
    """Ejecuta una consulta mínima y devuelve datos del servidor."""
    with get_connection() as conn:
        row = conn.cursor().execute(
            "SELECT DB_NAME() AS db, SUSER_SNAME() AS usuario, "
            "CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(50)) AS version, "
            "CONVERT(nvarchar(40), SYSDATETIMEOFFSET(), 127) AS hora_servidor"
        ).fetchone()
        return {
            "base_de_datos": row.db,
            "usuario": row.usuario,
            "version": row.version,
            "hora_servidor": str(row.hora_servidor),
        }
