-- (Para producción) Da acceso a la identidad administrada del App Service.
-- Ejecútalo conectado como el ADMINISTRADOR DE ENTRA ID del servidor SQL.
-- Reemplaza <nombre-de-tu-app-service> por el nombre real de la app.
CREATE USER [<nombre-de-tu-app-service>] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [<nombre-de-tu-app-service>];
ALTER ROLE db_datawriter ADD MEMBER [<nombre-de-tu-app-service>];
