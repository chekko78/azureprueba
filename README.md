# Azure SQL – Prueba de conectividad (Python + FastAPI)

Aplicación web mínima para comprobar que nos conectamos de forma **rápida y segura**
a la base de datos `test` de Azure SQL, antes de construir la aplicación completa.

## Por qué esta tecnología

| Elección | Motivo |
|---|---|
| **Python + FastAPI** | Rápido, moderno, fácil de mantener; documentación automática en `/docs` |
| **ODBC Driver 18 (pyodbc)** | Driver oficial de Microsoft para Azure SQL; conexión cifrada (TLS) obligatoria |
| **Pool de conexiones** | Reutiliza conexiones: las consultas siguientes tardan milisegundos |
| **Azure App Service (Linux)** | Hosting administrado con HTTPS incluido, en la misma región que la BD (baja latencia) |
| **Identidad administrada** | En producción, la app entra a la BD **sin contraseña** guardada en ningún lado |

## Estructura

```
app/db.py                          Conexión a Azure SQL (cifrada, pool, SQL o Entra ID)
app/main.py                        API web: /, /health, /health/db, /prueba
scripts/test_connection.py         Prueba de conexión desde la terminal
sql/01_crear_tabla_prueba.sql      Crea la tabla dbo.Prueba con 3 registros
sql/02_usuario_identidad_administrada.sql   Acceso sin contraseña (producción)
startup.sh                         Comando de arranque para el servidor web
.env.example                       Plantilla de configuración
```

---

## Paso 1 – Preparar Azure (Portal)

1. **Firewall del servidor SQL**: Portal → *Servidor SQL* → **Redes** →
   - *Agregar la dirección IPv4 del cliente* (tu IP actual) → **Guardar**.
2. **Crear la tabla de prueba**: Portal → *Base de datos `test`* → **Editor de consultas** →
   pega y ejecuta `sql/01_crear_tabla_prueba.sql`.

## Paso 2 – Probar la conectividad desde tu computadora

Requisitos: Python 3.11+ y **ODBC Driver 18 for SQL Server**
([descarga para Windows/macOS/Linux](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # en Windows: copy .env.example .env
```

Edita `.env` con tu servidor, base, usuario y contraseña. Luego:

```bash
python -m scripts.test_connection
```

Resultado esperado:

```
✅ Conexión exitosa en 450 ms
   base_de_datos: test
   usuario: ...
```

Y la API web local:

```bash
uvicorn app.main:app --reload
```

Abre <http://localhost:8000/health/db>, <http://localhost:8000/prueba> y <http://localhost:8000/docs>.

### Si falla

> **Mac con chip Apple:** si sale `OpenSSL library could not be loaded`, agrega
> `SQL_DRIVER=pytds` a tu `.env`. Usa una conexión 100% Python (también cifrada y
> validando el certificado) que no necesita el driver ODBC.

| Mensaje | Solución |
|---|---|
| `Cannot open server ... requested by the login. Client with IP address ... is not allowed` | Agrega esa IP en el firewall (Paso 1) |
| `Login failed for user` | Usuario/contraseña incorrectos |
| `Can't open lib 'ODBC Driver 18 for SQL Server'` | Instala el ODBC Driver 18 |
| `Login timeout expired` | Red/puerto 1433 bloqueado por tu red corporativa |

---

## Paso 3 – Publicar en un servidor web (Azure App Service)

Se recomienda App Service Linux en la **misma región** que la base de datos.
Con [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) instalado, desde la carpeta del proyecto:

```bash
az login
```

```bash
az webapp up --name <nombre-unico-app> --resource-group <tu-grupo> --location <region-de-tu-bd> --runtime "PYTHON:3.12" --sku B1
```

```bash
az webapp config set --name <nombre-unico-app> --resource-group <tu-grupo> --startup-file "startup.sh"
```

### 3a. Configuración (sin subir el `.env`)

Para la primera prueba puedes usar usuario/contraseña (se guardan cifrados en App Service):

```bash
az webapp config appsettings set --name <nombre-unico-app> --resource-group <tu-grupo> --settings AZURE_SQL_SERVER=<servidor>.database.windows.net AZURE_SQL_DATABASE=test AZURE_SQL_AUTH=sql AZURE_SQL_USER=<usuario> AZURE_SQL_PASSWORD=<contraseña> SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

Permite que los servicios de Azure lleguen a la BD: Portal → *Servidor SQL* → **Redes** →
marcar *Permitir que los servicios y recursos de Azure accedan a este servidor*.

Prueba: `https://<nombre-unico-app>.azurewebsites.net/health/db`

### 3b. Producción: sin contraseñas (identidad administrada)

1. Activa la identidad de la app:
   ```bash
   az webapp identity assign --name <nombre-unico-app> --resource-group <tu-grupo>
   ```
2. Portal → *Servidor SQL* → **Microsoft Entra ID** → define un administrador de Entra.
3. Conectado como ese administrador, ejecuta `sql/02_usuario_identidad_administrada.sql`.
4. Cambia la configuración y borra la contraseña:
   ```bash
   az webapp config appsettings set --name <nombre-unico-app> --resource-group <tu-grupo> --settings AZURE_SQL_AUTH=entra
   ```
   ```bash
   az webapp config appsettings delete --name <nombre-unico-app> --resource-group <tu-grupo> --setting-names AZURE_SQL_USER AZURE_SQL_PASSWORD
   ```

Recomendaciones extra de seguridad: activar **Solo HTTPS** en App Service y, más adelante,
usar *Private Endpoint* para que la BD no tenga acceso público.

---

## Endpoints

| Ruta | Qué hace |
|---|---|
| `GET /` | La app está en línea |
| `GET /health` | Salud de la app (sin tocar la BD) |
| `GET /health/db` | Conecta a Azure SQL y devuelve base, usuario, versión y hora del servidor |
| `GET /prueba` | Lee los registros de `dbo.Prueba` |
| `GET /docs` | Documentación interactiva |
