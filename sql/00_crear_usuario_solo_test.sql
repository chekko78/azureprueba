-- Crea un usuario que SOLO existe dentro de la base "test" (usuario contenido).
-- No puede entrar a ninguna otra base del servidor (por ejemplo, atecnodb).
--
-- IMPORTANTE: ejecútalo estando conectado a la base "test"
-- (Portal -> SQL databases -> test -> Editor de consultas).
-- Verifica primero que este SELECT diga "test":
SELECT DB_NAME() AS base_actual;

-- Cambia la contraseña por una fuerte (mín. 8 caracteres, mayúsculas, minúsculas, números y símbolo).
CREATE USER app_test WITH PASSWORD = 'CAMBIA_ESTA_Contrasena_123!';

-- Permisos: solo leer y escribir datos en "test".
ALTER ROLE db_datareader ADD MEMBER app_test;
ALTER ROLE db_datawriter ADD MEMBER app_test;
