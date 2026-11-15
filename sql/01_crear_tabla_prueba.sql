-- Tabla de prueba. Ejecútala en el Portal de Azure -> Base de datos -> Editor de consultas,
-- o con Azure Data Studio / SSMS.
IF OBJECT_ID('dbo.Prueba', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Prueba (
        Id        INT IDENTITY(1,1) PRIMARY KEY,
        Nombre    NVARCHAR(100)      NOT NULL,
        CreadoEn  DATETIME2          NOT NULL DEFAULT SYSUTCDATETIME()
    );

    INSERT INTO dbo.Prueba (Nombre) VALUES (N'Registro 1'), (N'Registro 2'), (N'Registro 3');
END;

SELECT * FROM dbo.Prueba;
