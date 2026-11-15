-- =====================================================================
-- Golf Campestre: esquema de base de datos
-- Ejecutar UNA VEZ en el Portal de Azure:
--   SQL databases -> test -> Editor de consultas (como administrador)
-- Verifica antes que SELECT DB_NAME() devuelva "test".
-- Es seguro volver a ejecutarlo: solo crea lo que falte.
-- Ejecútalo completo de una vez (botón Ejecutar).
-- =====================================================================
IF DB_NAME() <> 'test'
    THROW 50000, 'Este script solo debe ejecutarse en la base test.', 1;

IF SCHEMA_ID('golf') IS NULL EXEC('CREATE SCHEMA golf');

-- Recorrido de 18 hoyos (combinación de dos vueltas: Silla/Mitras, etc.)
IF OBJECT_ID('golf.Recorrido') IS NULL
CREATE TABLE golf.Recorrido (
    Id      INT IDENTITY PRIMARY KEY,
    Nombre  NVARCHAR(60) NOT NULL UNIQUE,
    Activo  BIT NOT NULL DEFAULT 1
);

-- Par y handicap de cada hoyo del recorrido
IF OBJECT_ID('golf.Hoyo') IS NULL
CREATE TABLE golf.Hoyo (
    RecorridoId     INT NOT NULL REFERENCES golf.Recorrido(Id),
    Numero          TINYINT NOT NULL CHECK (Numero BETWEEN 1 AND 18),
    Par             TINYINT NULL CHECK (Par BETWEEN 3 AND 6),
    Handicap        TINYINT NULL CHECK (Handicap BETWEEN 1 AND 18),
    PRIMARY KEY (RecorridoId, Numero)
);

-- Salidas (tees) con su rating y slope
IF OBJECT_ID('golf.Tee') IS NULL
CREATE TABLE golf.Tee (
    Id          INT IDENTITY PRIMARY KEY,
    RecorridoId INT NOT NULL REFERENCES golf.Recorrido(Id),
    Nombre      NVARCHAR(30) NOT NULL,
    Color       VARCHAR(7) NOT NULL DEFAULT '#888888',
    RatingH     DECIMAL(4,1) NULL,   -- caballeros
    SlopeH      SMALLINT NULL,
    RatingM     DECIMAL(4,1) NULL,   -- damas
    SlopeM      SMALLINT NULL,
    Orden       TINYINT NOT NULL DEFAULT 0,
    UNIQUE (RecorridoId, Nombre)
);

IF OBJECT_ID('golf.Yardas') IS NULL
CREATE TABLE golf.Yardas (
    TeeId   INT NOT NULL REFERENCES golf.Tee(Id),
    Numero  TINYINT NOT NULL CHECK (Numero BETWEEN 1 AND 18),
    Yardas  SMALLINT NOT NULL,
    PRIMARY KEY (TeeId, Numero)
);

IF OBJECT_ID('golf.Jugador') IS NULL
CREATE TABLE golf.Jugador (
    Id              INT IDENTITY PRIMARY KEY,
    Nombre          NVARCHAR(80) NOT NULL,
    Genero          CHAR(1) NOT NULL DEFAULT 'H' CHECK (Genero IN ('H','M')),
    HandicapIndex   DECIMAL(4,1) NOT NULL DEFAULT 0 CHECK (HandicapIndex BETWEEN -10 AND 54),
    Activo          BIT NOT NULL DEFAULT 1,
    CreadoEn        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

IF OBJECT_ID('golf.Torneo') IS NULL
CREATE TABLE golf.Torneo (
    Id              INT IDENTITY PRIMARY KEY,
    Nombre          NVARCHAR(100) NOT NULL,
    Fecha           DATE NOT NULL,
    RecorridoId     INT NOT NULL REFERENCES golf.Recorrido(Id),
    Formato         VARCHAR(12) NOT NULL DEFAULT 'neto' CHECK (Formato IN ('gross','neto','stableford')),
    PctHandicap     TINYINT NOT NULL DEFAULT 100 CHECK (PctHandicap BETWEEN 0 AND 100),
    Estado          VARCHAR(10) NOT NULL DEFAULT 'abierto' CHECK (Estado IN ('abierto','cerrado')),
    CreadoEn        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

-- Grupo de salida; el PIN permite capturar scores de ese grupo
IF OBJECT_ID('golf.Grupo') IS NULL
CREATE TABLE golf.Grupo (
    Id          INT IDENTITY PRIMARY KEY,
    TorneoId    INT NOT NULL REFERENCES golf.Torneo(Id),
    Nombre      NVARCHAR(40) NOT NULL,
    HoyoSalida  TINYINT NOT NULL DEFAULT 1 CHECK (HoyoSalida BETWEEN 1 AND 18),
    HoraSalida  NVARCHAR(5) NULL,
    Pin         CHAR(6) NOT NULL,
    UNIQUE (TorneoId, Nombre)
);

IF OBJECT_ID('golf.Participante') IS NULL
CREATE TABLE golf.Participante (
    Id              INT IDENTITY PRIMARY KEY,
    TorneoId        INT NOT NULL REFERENCES golf.Torneo(Id),
    JugadorId       INT NOT NULL REFERENCES golf.Jugador(Id),
    GrupoId         INT NULL REFERENCES golf.Grupo(Id),
    TeeId           INT NOT NULL REFERENCES golf.Tee(Id),
    HandicapIndex   DECIMAL(4,1) NOT NULL,   -- copia al momento de inscribirse
    HandicapJuego   SMALLINT NOT NULL,       -- golpes que recibe en este torneo
    UNIQUE (TorneoId, JugadorId)
);

IF OBJECT_ID('golf.Score') IS NULL
CREATE TABLE golf.Score (
    ParticipanteId  INT NOT NULL REFERENCES golf.Participante(Id),
    Hoyo            TINYINT NOT NULL CHECK (Hoyo BETWEEN 1 AND 18),
    Golpes          TINYINT NOT NULL CHECK (Golpes BETWEEN 1 AND 20),
    Putts           TINYINT NULL CHECK (Putts BETWEEN 0 AND 10),
    Fairway         BIT NULL,
    ActualizadoEn   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    PRIMARY KEY (ParticipanteId, Hoyo)
);

-- Apuestas dentro de un grupo: match, nassau o skins
IF OBJECT_ID('golf.Apuesta') IS NULL
CREATE TABLE golf.Apuesta (
    Id          INT IDENTITY PRIMARY KEY,
    TorneoId    INT NOT NULL REFERENCES golf.Torneo(Id),
    GrupoId     INT NOT NULL REFERENCES golf.Grupo(Id),
    Tipo        VARCHAR(10) NOT NULL CHECK (Tipo IN ('match','nassau','skins')),
    Monto       DECIMAL(10,2) NOT NULL DEFAULT 0,
    Neto        BIT NOT NULL DEFAULT 1,
    LadoA       VARCHAR(100) NOT NULL,   -- ids de participantes separados por coma
    LadoB       VARCHAR(100) NULL        -- vacío en skins
);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Participante_Jugador')
    CREATE INDEX IX_Participante_Jugador ON golf.Participante(JugadorId);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Participante_Grupo')
    CREATE INDEX IX_Participante_Grupo ON golf.Participante(GrupoId);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Torneo_Fecha')
    CREATE INDEX IX_Torneo_Fecha ON golf.Torneo(Fecha DESC);

-- ---------------------------------------------------------------------
-- Datos iniciales: los 3 recorridos del Club Campestre Monterrey.
-- Par y handicap por hoyo quedan VACÍOS: cárgalos desde la app
-- (Administración -> Recorridos) con la tarjeta oficial del club.
-- Rating/slope tomados de GolfPass (internet) -> VERIFICAR con la tarjeta.
-- ---------------------------------------------------------------------
DECLARE @r TABLE (Nombre NVARCHAR(60));
INSERT INTO @r VALUES (N'Silla / Mitras'), (N'Mitras / Sierra'), (N'Sierra / Silla');

INSERT INTO golf.Recorrido (Nombre)
SELECT Nombre FROM @r WHERE Nombre NOT IN (SELECT Nombre FROM golf.Recorrido);

INSERT INTO golf.Hoyo (RecorridoId, Numero)
SELECT r.Id, n.Numero
FROM golf.Recorrido r
CROSS JOIN (SELECT TOP 18 ROW_NUMBER() OVER (ORDER BY (SELECT 1)) AS Numero FROM sys.objects) n
WHERE NOT EXISTS (SELECT 1 FROM golf.Hoyo h WHERE h.RecorridoId = r.Id AND h.Numero = n.Numero);

DECLARE @t TABLE (Recorrido NVARCHAR(60), Nombre NVARCHAR(30), Color VARCHAR(7),
                  RatingH DECIMAL(4,1), SlopeH SMALLINT, Orden TINYINT);
INSERT INTO @t VALUES
 (N'Silla / Mitras',  N'Negras',  '#111111', 73.0, 127, 1),
 (N'Silla / Mitras',  N'Azules',  '#1d4ed8', 71.0, 125, 2),
 (N'Silla / Mitras',  N'Blancas', '#e5e7eb', 69.2, 120, 3),
 (N'Silla / Mitras',  N'Doradas', '#d4a017', 67.4, 116, 4),
 (N'Silla / Mitras',  N'Rojas',   '#dc2626', NULL, NULL, 5),
 (N'Mitras / Sierra', N'Negras',  '#111111', NULL, NULL, 1),
 (N'Mitras / Sierra', N'Azules',  '#1d4ed8', NULL, NULL, 2),
 (N'Mitras / Sierra', N'Blancas', '#e5e7eb', 69.1, 121, 3),
 (N'Mitras / Sierra', N'Doradas', '#d4a017', NULL, NULL, 4),
 (N'Mitras / Sierra', N'Rojas',   '#dc2626', NULL, NULL, 5),
 (N'Sierra / Silla',  N'Negras',  '#111111', 73.7, 126, 1),
 (N'Sierra / Silla',  N'Azules',  '#1d4ed8', 71.6, 124, 2),
 (N'Sierra / Silla',  N'Blancas', '#e5e7eb', 69.9, 122, 3),
 (N'Sierra / Silla',  N'Doradas', '#d4a017', 68.2, 116, 4),
 (N'Sierra / Silla',  N'Rojas',   '#dc2626', NULL, NULL, 5);

INSERT INTO golf.Tee (RecorridoId, Nombre, Color, RatingH, SlopeH, Orden)
SELECT r.Id, t.Nombre, t.Color, t.RatingH, t.SlopeH, t.Orden
FROM @t t JOIN golf.Recorrido r ON r.Nombre = t.Recorrido
WHERE NOT EXISTS (SELECT 1 FROM golf.Tee x WHERE x.RecorridoId = r.Id AND x.Nombre = t.Nombre);

SELECT r.Nombre AS Recorrido, COUNT(DISTINCT h.Numero) AS Hoyos, COUNT(DISTINCT t.Id) AS Tees
FROM golf.Recorrido r
LEFT JOIN golf.Hoyo h ON h.RecorridoId = r.Id
LEFT JOIN golf.Tee t ON t.RecorridoId = r.Id
GROUP BY r.Nombre;
