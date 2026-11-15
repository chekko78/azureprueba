# Golf Campestre – score y torneos (web app para iPhone + Azure SQL)

Web app instalable en iPhone para llevar el score de golf en los recorridos del
Club Campestre Monterrey (Silla / Mitras, Mitras / Sierra, Sierra / Silla), con
torneos, leaderboard en vivo y apuestas. Los datos viven en la base **`test`** de Azure SQL.

## Qué hace

| Función | Detalle |
|---|---|
| **Torneos** | Grupos de salida (hoyo 1 o 10, hora), cada grupo con su **PIN de 6 dígitos** para capturar |
| **Captura hoyo por hoyo** | Botones grandes + / −, golpes de ventaja por hoyo, putts y fairways opcionales |
| **Sin señal** | Lo capturado se guarda en el teléfono y se envía solo cuando regresa la señal |
| **Leaderboard en vivo** | Gross, neto y Stableford; se actualiza cada 20 s; tarjeta completa de cada jugador |
| **Handicap** | Sistema mundial (WHS): Index × Slope/113 + (Rating − Par), con % de handicap por torneo |
| **Apuestas por grupo** | Match (individual o parejas a mejor bola), Nassau (ida, vuelta y total) y Skins con acumulado |
| **Historial y estadísticas** | Rondas por jugador, promedio, mejor ronda, putts/hoyo, % fairways, % greens en regulación |
| **Administración** | Recorridos (par, handicap y yardas por hoyo; rating y slope por salida), jugadores y torneos |

## Arquitectura y seguridad

```
iPhone (Safari / app en pantalla de inicio)
        │  HTTPS
        ▼
Servidor web (FastAPI, Python)  ──cifrado TLS──►  Azure SQL (base test, usuario app_test)
```

- El teléfono **nunca** se conecta directo a la base ni guarda su contraseña.
- La conexión a Azure SQL va cifrada y valida el certificado del servidor.
- El administrador entra con contraseña (`ADMIN_PASSWORD`). Los capturistas usan el PIN de su grupo
  y solo pueden capturar ese grupo, solo mientras el torneo esté abierto.
- Las sesiones usan tokens firmados (HMAC) que vencen. Hay límite de intentos de contraseña y PIN.
- Todas las consultas a la base son parametrizadas.
- El usuario `app_test` solo existe en la base `test` y no puede ver `atecnodb`.

## Estructura

```
app/main.py               Arranque de la app, cabeceras de seguridad
app/db.py                 Conexión a Azure SQL (odbc o pytds)
app/golf/calc.py          Cálculos: handicap, neto, Stableford, leaderboard, match, nassau, skins
app/golf/api.py           API /api/... (pública, captura con PIN y administración)
app/golf/servicio.py      Lectura de datos y armado de resultados
app/golf/auth.py          Contraseña de admin, PIN de grupo, tokens y límite de intentos
app/static/               Web app (HTML/CSS/JS), manifest, service worker e íconos
sql/10_golf_esquema.sql   Tablas de golf y los 3 recorridos del club
tests/                    Pruebas (cálculos y de punta a punta)
deploy_azure.sh           Publica en Azure App Service con un comando
```

---

## 1. Crear las tablas en Azure (una sola vez)

1. Portal de Azure → **SQL databases** → **test** → **Editor de consultas**. Entra como administrador.
2. Abre `sql/10_golf_esquema.sql`, copia **todo** su contenido, pégalo y da clic en **Ejecutar**.
3. Al final verás los 3 recorridos con 18 hoyos y 5 salidas cada uno.

El script se niega a correr si no estás en la base `test`. Se puede volver a ejecutar sin problema.

## 2. Configurar `.env`

Agrega a tu `.env` una contraseña de administrador:

```
ADMIN_PASSWORD=una-contraseña-fuerte
```

## 3. Probar en tu Mac

```bash
git pull
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
uvicorn app.main:app --reload
```

Abre <http://localhost:8000>.

**Para verla en tu iPhone desde la misma red Wi-Fi**, arranca así:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Luego abre en Safari del iPhone `http://IP-DE-TU-MAC:8000`. La IP la ves en *Ajustes del Sistema → Red*.
El modo sin señal solo funciona cuando la app está publicada con HTTPS (paso 5).

## 4. Primer uso (Administración)

1. **Admin** → contraseña.
2. **Recorridos** → captura el **par** y el **handicap** de los 18 hoyos de cada recorrido con la
   **tarjeta oficial del club**, y revisa el rating/slope de cada salida.
   Los valores de rating/slope precargados vienen de internet (GolfPass) y hay que verificarlos.
3. **Jugadores** → da de alta a cada jugador con su handicap index.
4. **Torneos** → crea el torneo, sus grupos (cada uno recibe un PIN), inscribe jugadores
   (el handicap de juego se calcula solo) y, si quieren, apuestas.
5. Entrega a cada grupo su PIN. En el campo: **Capturar score de mi grupo** → PIN → hoyo por hoyo.

## 5. Publicar en Azure e instalar en el iPhone

```bash
./deploy_azure.sh atecno-golf
```

El script crea el servidor web, guarda la configuración cifrada en Azure, autoriza en el firewall
solo las IPs de la app y publica. Hoy está bloqueado por la **cuota de App Service** de la suscripción:
hay que pedirla a Microsoft (ver historial del proyecto).

En el iPhone: abre `https://atecno-golf.azurewebsites.net` en **Safari** → botón **Compartir** →
**Agregar a pantalla de inicio**. Queda como una app con su ícono.

## Pruebas

```bash
pip install -r requirements-dev.txt
```

```bash
pytest -q
```

Las pruebas de punta a punta (`tests/test_api_e2e.py`) necesitan un SQL Server con el esquema
y se activan con `GOLF_E2E=1`.

## Diagnóstico de conexión

- `python -m scripts.test_connection`: prueba la conexión a Azure SQL desde la terminal.
- `/health/db`: estado de la conexión desde la app.
- `/explorar`: explorador de tablas de solo lectura. Solo funciona en local; en Azure está apagado.
- **Mac con chip Apple:** si sale `OpenSSL library could not be loaded`, usa `SQL_DRIVER=pytds` en `.env`.
