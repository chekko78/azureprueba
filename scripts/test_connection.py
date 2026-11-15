"""Prueba de conectividad desde la línea de comandos.

Uso (desde la raíz del proyecto):
    python -m scripts.test_connection
"""
import sys
import time

from app.db import check_connection


def main() -> int:
    print("Conectando a Azure SQL...")
    start = time.perf_counter()
    try:
        info = check_connection()
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ No se pudo conectar: {exc}\n")
        print("Revisa: 1) datos del .env  2) firewall del servidor SQL en Azure (tu IP)")
        print("        3) ODBC Driver 18 instalado  4) usuario/contraseña correctos")
        return 1
    ms = (time.perf_counter() - start) * 1000
    print(f"\n✅ Conexión exitosa en {ms:.0f} ms")
    for k, v in info.items():
        print(f"   {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
