# Contexto del proyecto (para Claude)

App web instalable en iPhone (PWA) para llevar score de golf y torneos del Club Campestre
Monterrey, con backend FastAPI (Python) y datos en Azure SQL.

## Datos clave
- Servidor Azure SQL: `atecno.database.windows.net`, base **`test`**. Usuario de la app: `app_test`
  (usuario contenido, solo existe en `test`, roles db_datareader/db_datawriter).
- **NUNCA tocar la base `atecnodb`** del mismo servidor.
- Configuración en `.env` (no se sube a git). En Mac con chip Apple se usa `SQL_DRIVER=pytds`
  porque el ODBC Driver 18 falla al cargar OpenSSL. En Azure App Service se usa `odbc`.
- El usuario usa macOS y prefiere instrucciones en español, paso a paso.

## Estructura
- `app/golf/calc.py`: cálculos puros (handicap WHS, neto, Stableford, leaderboard, match, nassau, skins).
- `app/golf/api.py`: endpoints `/api/...` (público, captura con PIN de grupo, admin con `ADMIN_PASSWORD`).
- `app/static/`: frontend sin frameworks (`app.js`, `styles.css`, `sw.js`, manifest).
- `sql/10_golf_esquema.sql`: esquema `golf` (ya ejecutado en Azure). Recorridos: Silla / Mitras,
  Mitras / Sierra, Sierra / Silla; par y handicap por hoyo se capturan desde Admin con la tarjeta oficial.
- `deploy_azure.sh <app>`: publica en Azure App Service. Bloqueado por cuota de App Service en 0
  (suscripción PayAsYouGo; la página de Cuotas muestra 30 para B1 pero al crear dice 0) →
  pendiente de solicitud de soporte a Microsoft.

## Comandos
- Correr local: `source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Probar conexión: `python -m scripts.test_connection`
- Pruebas: `pip install -r requirements-dev.txt && pytest -q` (e2e requiere `GOLF_E2E=1` y SQL Server).

## Git
- Rama de trabajo: `claude/keen-newton-13xlmb`.
