#!/usr/bin/env bash
# Publica la app en Azure App Service (Linux, Python 3.12) y la conecta a atecno/test.
#
# Uso (desde la carpeta del proyecto, después de "az login"):
#   ./deploy_azure.sh <nombre-de-la-app>
#
# El nombre debe ser único en todo Azure; la app quedará en https://<nombre>.azurewebsites.net
# Se puede volver a ejecutar las veces que quieras: solo crea lo que falte y vuelve a publicar.
set -euo pipefail

APP="${1:?Uso: ./deploy_azure.sh <nombre-de-la-app>   (ej. ./deploy_azure.sh atecno-prueba)}"
SQL_SERVER_NAME="${SQL_SERVER_NAME:-atecno}"   # servidor SQL (NO se modifica ninguna base)
SKU="${SKU:-B1}"                               # tamaño del servidor web (F1 = gratis, para pruebas)
# LOCATION=<region> permite crear la app en otra región (por defecto, la del servidor SQL)
PLAN="plan-$APP"

cd "$(dirname "$0")"

# --- Leer datos de conexión del .env (sin mostrarlos en pantalla) ---
[ -f .env ] || { echo "❌ No encuentro el archivo .env en $(pwd)"; exit 1; }
env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
DB_SERVER="$(env_get AZURE_SQL_SERVER)"
DB_NAME="$(env_get AZURE_SQL_DATABASE)"
DB_USER="$(env_get AZURE_SQL_USER)"
DB_PASS="$(env_get AZURE_SQL_PASSWORD)"
for v in DB_SERVER DB_NAME DB_USER DB_PASS; do
  [ -n "${!v}" ] || { echo "❌ Falta un dato en .env ($v)"; exit 1; }
done
if [ "$DB_NAME" != "test" ]; then
  echo "❌ Por seguridad este script solo publica contra la base 'test' (tu .env dice '$DB_NAME')."
  exit 1
fi

command -v az >/dev/null || { echo "❌ Falta Azure CLI. Instálalo con: brew install azure-cli"; exit 1; }
az account show >/dev/null 2>&1 || { echo "❌ Primero inicia sesión con: az login"; exit 1; }

echo "▶ Buscando el servidor SQL '$SQL_SERVER_NAME'..."
RG="$(az sql server list --query "[?name=='$SQL_SERVER_NAME'].resourceGroup | [0]" -o tsv)"
[ -n "$RG" ] || { echo "❌ No encontré el servidor SQL '$SQL_SERVER_NAME' en esta suscripción."; exit 1; }
LOC="${LOCATION:-$(az sql server show -g "$RG" -n "$SQL_SERVER_NAME" --query location -o tsv)}"
echo "  Grupo de recursos: $RG | Región: $LOC"

echo "▶ Plan de App Service ($PLAN, $SKU, Linux)..."
az appservice plan show -g "$RG" -n "$PLAN" -o none 2>/dev/null \
  || az appservice plan create -g "$RG" -n "$PLAN" -l "$LOC" --is-linux --sku "$SKU" -o none

echo "▶ Aplicación web ($APP)..."
az webapp show -g "$RG" -n "$APP" -o none 2>/dev/null \
  || az webapp create -g "$RG" -p "$PLAN" -n "$APP" --runtime "PYTHON:3.12" -o none

echo "▶ Seguridad: solo HTTPS, TLS 1.2+, FTP deshabilitado..."
az webapp update -g "$RG" -n "$APP" --https-only true -o none
az webapp config set -g "$RG" -n "$APP" --min-tls-version 1.2 --ftps-state Disabled \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 120 --workers 2 -k uvicorn.workers.UvicornWorker app.main:app" \
  -o none

echo "▶ Configuración de la conexión (se guarda cifrada en Azure, no en el código)..."
az webapp config appsettings set -g "$RG" -n "$APP" -o none --settings \
  "AZURE_SQL_SERVER=$DB_SERVER" "AZURE_SQL_DATABASE=$DB_NAME" "AZURE_SQL_PORT=1433" \
  "AZURE_SQL_AUTH=sql" "AZURE_SQL_USER=$DB_USER" "AZURE_SQL_PASSWORD=$DB_PASS" \
  "SQL_DRIVER=${DEPLOY_SQL_DRIVER:-odbc}" "ENABLE_DB_BROWSER=false" "SCM_DO_BUILD_DURING_DEPLOYMENT=true"

echo "▶ Firewall: permitir SOLO las IPs de salida de esta app hacia el servidor SQL..."
IPS="$(az webapp show -g "$RG" -n "$APP" --query possibleOutboundIpAddresses -o tsv | tr ',' ' ')"
for ip in $IPS; do
  az sql server firewall-rule create -g "$RG" -s "$SQL_SERVER_NAME" \
    -n "app-$APP-${ip//./-}" --start-ip-address "$ip" --end-ip-address "$ip" -o none
done
echo "  $(echo "$IPS" | wc -w | tr -d ' ') IPs autorizadas"

echo "▶ Empaquetando el código (solo archivos de git: sin .env ni .venv)..."
ZIP="$(mktemp -d)/app.zip"
git archive --format=zip -o "$ZIP" HEAD

echo "▶ Publicando (tarda 2-5 minutos)..."
az webapp deploy -g "$RG" -n "$APP" --src-path "$ZIP" --type zip -o none

URL="https://$APP.azurewebsites.net"
echo "▶ Probando $URL/health/db ..."
for i in $(seq 1 20); do
  if RESP="$(curl -fsS --max-time 60 "$URL/health/db" 2>/dev/null)"; then
    echo "✅ ¡Publicada y conectada!"
    echo "   $RESP"
    echo "   Abre: $URL/prueba  y  $URL/docs"
    exit 0
  fi
  sleep 15
done
echo "⚠️  La app no respondió OK todavía. Revisa el log con:"
echo "   az webapp log tail -g $RG -n $APP"
exit 1
