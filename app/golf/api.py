"""API de la app de golf (/api/...)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.golf import auth, calc, servicio
from app.golf.sql import tx

router = APIRouter(prefix="/api")


# ============================================================ modelos
class Login(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class Acceso(BaseModel):
    pin: str = Field(pattern=r"^\d{6}$")


class ScoreIn(BaseModel):
    participante_id: int
    hoyo: int = Field(ge=1, le=18)
    golpes: int | None = Field(default=None, ge=1, le=20)   # None = borrar
    putts: int | None = Field(default=None, ge=0, le=10)
    fairway: bool | None = None


class HoyoIn(BaseModel):
    numero: int = Field(ge=1, le=18)
    par: int | None = Field(default=None, ge=3, le=6)
    handicap: int | None = Field(default=None, ge=1, le=18)


class TeeIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=30)
    color: str = Field(default="#888888", pattern=r"^#[0-9a-fA-F]{6}$")
    rating_h: float | None = Field(default=None, ge=50, le=85)
    slope_h: int | None = Field(default=None, ge=55, le=155)
    rating_m: float | None = Field(default=None, ge=50, le=85)
    slope_m: int | None = Field(default=None, ge=55, le=155)
    orden: int = Field(default=0, ge=0, le=50)
    yardas: list[int | None] | None = None

    @field_validator("yardas")
    @classmethod
    def _18(cls, v):
        if v is not None and len(v) != 18:
            raise ValueError("Deben ser 18 valores")
        return v


class JugadorIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    genero: Literal["H", "M"] = "H"
    handicap_index: float = Field(default=0, ge=-10, le=54)


class TorneoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    fecha: date
    recorrido_id: int
    formato: Literal["gross", "neto", "stableford"] = "neto"
    pct_handicap: int = Field(default=100, ge=0, le=100)


class GrupoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=40)
    hoyo_salida: int = Field(default=1, ge=1, le=18)
    hora_salida: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")


class ParticipanteIn(BaseModel):
    jugador_id: int
    tee_id: int
    grupo_id: int | None = None
    hcp_juego: int | None = Field(default=None, ge=-10, le=60)  # para ajustar a mano


class ApuestaIn(BaseModel):
    grupo_id: int
    tipo: Literal["match", "nassau", "skins"]
    monto: float = Field(default=0, ge=0, le=1_000_000)
    neto: bool = True
    lado_a: list[int] = Field(min_length=1, max_length=8)
    lado_b: list[int] = Field(default_factory=list, max_length=8)


# ============================================================ públicos
@router.get("/recorridos")
def recorridos():
    with tx() as t:
        rs = t.all("SELECT Id AS id, Nombre AS nombre FROM golf.Recorrido WHERE Activo = 1 ORDER BY Nombre")
        for r in rs:
            hoyos = servicio.hoyos_recorrido(t, r["id"])
            r["completo"] = servicio.recorrido_completo(hoyos)
            r["par"] = sum(h["par"] or 0 for h in hoyos)
        return rs


@router.get("/recorridos/{rid}")
def recorrido(rid: int):
    with tx() as t:
        r = t.one("SELECT Id AS id, Nombre AS nombre FROM golf.Recorrido WHERE Id = ?", (rid,))
        if not r:
            raise HTTPException(404, "Recorrido no encontrado")
        r["hoyos"] = servicio.hoyos_recorrido(t, rid)
        r["completo"] = servicio.recorrido_completo(r["hoyos"])
        r["tees"] = t.all(
            "SELECT Id AS id, Nombre AS nombre, Color AS color, RatingH AS rating_h, SlopeH AS slope_h, "
            "RatingM AS rating_m, SlopeM AS slope_m, Orden AS orden FROM golf.Tee "
            "WHERE RecorridoId = ? ORDER BY Orden, Nombre",
            (rid,),
        )
        yardas = t.all(
            "SELECT y.TeeId AS tee_id, y.Numero AS numero, y.Yardas AS yardas FROM golf.Yardas y "
            "JOIN golf.Tee te ON te.Id = y.TeeId WHERE te.RecorridoId = ?",
            (rid,),
        )
        for te in r["tees"]:
            ys = {y["numero"]: y["yardas"] for y in yardas if y["tee_id"] == te["id"]}
            te["yardas"] = [ys.get(n) for n in range(1, 19)]
        return r


@router.get("/torneos")
def torneos():
    with tx() as t:
        return t.all(
            "SELECT TOP 100 tr.Id AS id, tr.Nombre AS nombre, tr.Fecha AS fecha, r.Nombre AS recorrido, "
            "tr.Formato AS formato, tr.Estado AS estado, "
            "(SELECT COUNT(*) FROM golf.Participante p WHERE p.TorneoId = tr.Id) AS jugadores "
            "FROM golf.Torneo tr JOIN golf.Recorrido r ON r.Id = tr.RecorridoId "
            "ORDER BY tr.Fecha DESC, tr.Id DESC"
        )


@router.get("/torneos/{tid}")
def torneo_detalle(tid: int):
    with tx() as t:
        tr = servicio.torneo(t, tid)
        tr["grupos"] = t.all(
            "SELECT Id AS id, Nombre AS nombre, HoyoSalida AS hoyo_salida, HoraSalida AS hora_salida "
            "FROM golf.Grupo WHERE TorneoId = ? ORDER BY HoraSalida, Nombre",
            (tid,),
        )
        tr["participantes"] = servicio.participantes(t, tid)
        for g in tr["grupos"]:
            g["apuestas"] = t.one(
                "SELECT COUNT(*) AS n FROM golf.Apuesta WHERE GrupoId = ?", (g["id"],))["n"]
        return tr


@router.get("/torneos/{tid}/leaderboard")
def leaderboard(tid: int, formato: Literal["gross", "neto", "stableford"] | None = None):
    with tx() as t:
        return servicio.leaderboard(t, tid, formato)


@router.get("/torneos/{tid}/grupos/{gid}/apuestas")
def apuestas(tid: int, gid: int):
    with tx() as t:
        return servicio.apuestas_grupo(t, tid, gid)


@router.get("/jugadores")
def jugadores():
    with tx() as t:
        return t.all(
            "SELECT Id AS id, Nombre AS nombre, Genero AS genero, HandicapIndex AS handicap_index "
            "FROM golf.Jugador WHERE Activo = 1 ORDER BY Nombre"
        )


@router.get("/jugadores/{jid}")
def jugador(jid: int):
    with tx() as t:
        return servicio.historial_jugador(t, jid)


# ============================================================ captura (PIN)
@router.post("/torneos/{tid}/acceso")
def acceso(tid: int, body: Acceso, request: Request):
    auth.limitar(request, f"pin{tid}")
    with tx() as t:
        g = t.one(
            "SELECT g.Id AS id, g.Nombre AS nombre, tr.Estado AS estado FROM golf.Grupo g "
            "JOIN golf.Torneo tr ON tr.Id = g.TorneoId WHERE g.TorneoId = ? AND g.Pin = ?",
            (tid, body.pin),
        )
    if not g:
        raise HTTPException(401, "PIN incorrecto")
    if g["estado"] != "abierto":
        raise HTTPException(409, "El torneo ya está cerrado")
    token = auth.crear_token({"r": "grupo", "t": tid, "g": g["id"]}, auth.GRUPO_HORAS)
    return {"token": token, "grupo": g["nombre"], "grupo_id": g["id"]}


def _tarjeta(t, tid: int, gid: int) -> dict:
    tr = servicio.torneo(t, tid)
    grupo = t.one(
        "SELECT Id AS id, Nombre AS nombre, HoyoSalida AS hoyo_salida, HoraSalida AS hora_salida "
        "FROM golf.Grupo WHERE Id = ? AND TorneoId = ?",
        (gid, tid),
    )
    if not grupo:
        raise HTTPException(404, "Grupo no encontrado")
    parts = servicio.participantes(t, tid, gid)
    sc = servicio.scores_torneo(t, tid)
    hoyos = servicio.hoyos_recorrido(t, tr["recorrido_id"])
    yardas = {}
    for y in t.all(
        "SELECT y.TeeId AS tee_id, y.Numero AS numero, y.Yardas AS yardas FROM golf.Yardas y "
        "JOIN golf.Tee te ON te.Id = y.TeeId WHERE te.RecorridoId = ?",
        (tr["recorrido_id"],),
    ):
        yardas.setdefault(y["tee_id"], {})[y["numero"]] = y["yardas"]
    for p in parts:
        p["scores"] = sc.get(p["id"], {})
        p["recibe"] = {h["numero"]: calc.golpes_en_hoyo(p["hcp_juego"], h["handicap"])
                       for h in hoyos if h["handicap"]}
        p["yardas"] = yardas.get(p["tee_id"], {})
    return {"torneo": tr, "grupo": grupo, "hoyos": hoyos, "participantes": parts}


@router.get("/grupo")
def mi_grupo(s: dict = Depends(auth.requiere_grupo)):
    with tx() as t:
        return _tarjeta(t, s["t"], s["g"])


def _guardar_scores(t, tid: int, scores: list[ScoreIn], grupo_id: int | None) -> int:
    tr = servicio.torneo(t, tid)
    if tr["estado"] != "abierto":
        raise HTTPException(409, "El torneo está cerrado; ya no se pueden cambiar scores")
    sql = "SELECT Id AS id FROM golf.Participante WHERE TorneoId = ?"
    params: list = [tid]
    if grupo_id is not None:
        sql += " AND GrupoId = ?"
        params.append(grupo_id)
    permitidos = {r["id"] for r in t.all(sql, params)}
    n = 0
    for s in scores:
        if s.participante_id not in permitidos:
            raise HTTPException(403, "Ese jugador no pertenece a tu grupo")
        if s.golpes is None:
            t.run("DELETE FROM golf.Score WHERE ParticipanteId = ? AND Hoyo = ?", (s.participante_id, s.hoyo))
        else:
            fw = None if s.fairway is None else int(s.fairway)
            upd = t.run(
                "UPDATE golf.Score SET Golpes = ?, Putts = ?, Fairway = ?, ActualizadoEn = SYSUTCDATETIME() "
                "WHERE ParticipanteId = ? AND Hoyo = ?",
                (s.golpes, s.putts, fw, s.participante_id, s.hoyo),
            )
            if upd == 0:
                t.run(
                    "INSERT INTO golf.Score (ParticipanteId, Hoyo, Golpes, Putts, Fairway) VALUES (?, ?, ?, ?, ?)",
                    (s.participante_id, s.hoyo, s.golpes, s.putts, fw),
                )
        n += 1
    return n


@router.put("/grupo/scores")
def guardar_scores_grupo(scores: list[ScoreIn], s: dict = Depends(auth.requiere_grupo)):
    if len(scores) > 200:
        raise HTTPException(413, "Demasiados scores en un envío")
    with tx() as t:
        return {"guardados": _guardar_scores(t, s["t"], scores, s["g"])}


# ============================================================ administración
admin = APIRouter(prefix="/admin", dependencies=[Depends(auth.requiere_admin)])


@router.post("/admin/login")
def admin_login(body: Login, request: Request):
    auth.limitar(request, "admin", global_max=30)
    if not auth.verificar_admin_password(body.password):
        raise HTTPException(401, "Contraseña incorrecta")
    return {"token": auth.crear_token({"r": "admin"}, auth.ADMIN_HORAS)}


@admin.put("/recorridos/{rid}/hoyos")
def guardar_hoyos(rid: int, hoyos: list[HoyoIn]):
    hcps = [h.handicap for h in hoyos if h.handicap]
    if len(hcps) != len(set(hcps)):
        raise HTTPException(422, "Hay handicaps de hoyo repetidos; cada hoyo debe tener uno distinto (1 a 18)")
    with tx() as t:
        for h in hoyos:
            t.run("UPDATE golf.Hoyo SET Par = ?, Handicap = ? WHERE RecorridoId = ? AND Numero = ?",
                  (h.par, h.handicap, rid, h.numero))
        hs = servicio.hoyos_recorrido(t, rid)
        return {"completo": servicio.recorrido_completo(hs), "par": sum(h["par"] or 0 for h in hs)}


def _guardar_yardas(t, tee_id: int, yardas: list[int | None] | None):
    if yardas is None:
        return
    t.run("DELETE FROM golf.Yardas WHERE TeeId = ?", (tee_id,))
    for n, y in enumerate(yardas, start=1):
        if y:
            t.run("INSERT INTO golf.Yardas (TeeId, Numero, Yardas) VALUES (?, ?, ?)", (tee_id, n, y))


@admin.post("/recorridos/{rid}/tees")
def crear_tee(rid: int, b: TeeIn):
    with tx() as t:
        tid = t.insert(
            "INSERT INTO golf.Tee (RecorridoId, Nombre, Color, RatingH, SlopeH, RatingM, SlopeM, Orden) "
            "OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, b.nombre, b.color, b.rating_h, b.slope_h, b.rating_m, b.slope_m, b.orden),
        )
        _guardar_yardas(t, tid, b.yardas)
        return {"id": tid}


@admin.put("/tees/{tee_id}")
def editar_tee(tee_id: int, b: TeeIn):
    with tx() as t:
        n = t.run(
            "UPDATE golf.Tee SET Nombre = ?, Color = ?, RatingH = ?, SlopeH = ?, RatingM = ?, SlopeM = ?, "
            "Orden = ? WHERE Id = ?",
            (b.nombre, b.color, b.rating_h, b.slope_h, b.rating_m, b.slope_m, b.orden, tee_id),
        )
        if not n:
            raise HTTPException(404, "Salida no encontrada")
        _guardar_yardas(t, tee_id, b.yardas)
        return {"ok": True}


@admin.post("/jugadores")
def crear_jugador(b: JugadorIn):
    with tx() as t:
        return {"id": t.insert(
            "INSERT INTO golf.Jugador (Nombre, Genero, HandicapIndex) OUTPUT INSERTED.Id VALUES (?, ?, ?)",
            (b.nombre.strip(), b.genero, b.handicap_index))}


@admin.put("/jugadores/{jid}")
def editar_jugador(jid: int, b: JugadorIn):
    with tx() as t:
        if not t.run("UPDATE golf.Jugador SET Nombre = ?, Genero = ?, HandicapIndex = ? WHERE Id = ?",
                     (b.nombre.strip(), b.genero, b.handicap_index, jid)):
            raise HTTPException(404, "Jugador no encontrado")
        return {"ok": True}


@admin.delete("/jugadores/{jid}")
def baja_jugador(jid: int):
    with tx() as t:
        t.run("UPDATE golf.Jugador SET Activo = 0 WHERE Id = ?", (jid,))
        return {"ok": True}


@admin.post("/torneos")
def crear_torneo(b: TorneoIn):
    with tx() as t:
        servicio.exigir_completo(servicio.hoyos_recorrido(t, b.recorrido_id))
        return {"id": t.insert(
            "INSERT INTO golf.Torneo (Nombre, Fecha, RecorridoId, Formato, PctHandicap) "
            "OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?)",
            (b.nombre.strip(), b.fecha, b.recorrido_id, b.formato, b.pct_handicap))}


@admin.put("/torneos/{tid}")
def editar_torneo(tid: int, b: TorneoIn):
    with tx() as t:
        tr = servicio.torneo(t, tid)
        if b.recorrido_id != tr["recorrido_id"]:
            raise HTTPException(409, "No se puede cambiar el recorrido de un torneo ya creado")
        t.run("UPDATE golf.Torneo SET Nombre = ?, Fecha = ?, Formato = ?, PctHandicap = ? WHERE Id = ?",
              (b.nombre.strip(), b.fecha, b.formato, b.pct_handicap, tid))
        return {"ok": True}


@admin.post("/torneos/{tid}/estado/{estado}")
def estado_torneo(tid: int, estado: Literal["abierto", "cerrado"]):
    with tx() as t:
        servicio.torneo(t, tid)
        t.run("UPDATE golf.Torneo SET Estado = ? WHERE Id = ?", (estado, tid))
        return {"ok": True}


@admin.get("/torneos/{tid}")
def torneo_admin(tid: int):
    with tx() as t:
        tr = servicio.torneo(t, tid)
        tr["grupos"] = t.all(
            "SELECT Id AS id, Nombre AS nombre, HoyoSalida AS hoyo_salida, HoraSalida AS hora_salida, "
            "Pin AS pin FROM golf.Grupo WHERE TorneoId = ? ORDER BY HoraSalida, Nombre",
            (tid,),
        )
        tr["participantes"] = servicio.participantes(t, tid)
        tr["tees"] = t.all(
            "SELECT Id AS id, Nombre AS nombre, Color AS color FROM golf.Tee WHERE RecorridoId = ? "
            "ORDER BY Orden, Nombre",
            (tr["recorrido_id"],),
        )
        tr["apuestas"] = t.all(
            "SELECT Id AS id, GrupoId AS grupo_id, Tipo AS tipo, Monto AS monto, Neto AS neto, "
            "LadoA AS lado_a, LadoB AS lado_b FROM golf.Apuesta WHERE TorneoId = ? ORDER BY Id",
            (tid,),
        )
        return tr


@admin.post("/torneos/{tid}/grupos")
def crear_grupo(tid: int, b: GrupoIn):
    with tx() as t:
        servicio.torneo(t, tid)
        usados = {r["pin"] for r in t.all("SELECT Pin AS pin FROM golf.Grupo WHERE TorneoId = ?", (tid,))}
        pin = auth.nuevo_pin()
        while pin in usados:
            pin = auth.nuevo_pin()
        gid = t.insert(
            "INSERT INTO golf.Grupo (TorneoId, Nombre, HoyoSalida, HoraSalida, Pin) "
            "OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?)",
            (tid, b.nombre.strip(), b.hoyo_salida, b.hora_salida, pin),
        )
        return {"id": gid, "pin": pin}


@admin.put("/torneos/{tid}/grupos/{gid}")
def editar_grupo(tid: int, gid: int, b: GrupoIn):
    with tx() as t:
        if not t.run("UPDATE golf.Grupo SET Nombre = ?, HoyoSalida = ?, HoraSalida = ? WHERE Id = ? AND TorneoId = ?",
                     (b.nombre.strip(), b.hoyo_salida, b.hora_salida, gid, tid)):
            raise HTTPException(404, "Grupo no encontrado")
        return {"ok": True}


@admin.delete("/torneos/{tid}/grupos/{gid}")
def borrar_grupo(tid: int, gid: int):
    with tx() as t:
        t.run("DELETE FROM golf.Apuesta WHERE GrupoId = ? AND TorneoId = ?", (gid, tid))
        t.run("UPDATE golf.Participante SET GrupoId = NULL WHERE GrupoId = ? AND TorneoId = ?", (gid, tid))
        t.run("DELETE FROM golf.Grupo WHERE Id = ? AND TorneoId = ?", (gid, tid))
        return {"ok": True}


def _calcular_hcp(t, tr: dict, jugador_id: int, tee_id: int) -> tuple[float, int]:
    j = t.one("SELECT HandicapIndex AS idx, Genero AS genero FROM golf.Jugador WHERE Id = ? AND Activo = 1",
              (jugador_id,))
    if not j:
        raise HTTPException(404, "Jugador no encontrado")
    te = t.one("SELECT RatingH, SlopeH, RatingM, SlopeM FROM golf.Tee WHERE Id = ? AND RecorridoId = ?",
               (tee_id, tr["recorrido_id"]))
    if not te:
        raise HTTPException(422, "Esa salida no pertenece al recorrido del torneo")
    rating, slope = (te["RatingM"], te["SlopeM"]) if j["genero"] == "M" else (te["RatingH"], te["SlopeH"])
    par = sum(h["par"] for h in servicio.hoyos_recorrido(t, tr["recorrido_id"]))
    ch = calc.course_handicap(j["idx"], slope, rating, par)
    return j["idx"], calc.playing_handicap(ch, tr["pct_handicap"])


def _validar_grupo(t, tid: int, gid: int | None):
    if gid is not None and not t.one("SELECT 1 AS x FROM golf.Grupo WHERE Id = ? AND TorneoId = ?", (gid, tid)):
        raise HTTPException(422, "Ese grupo no es de este torneo")


@admin.post("/torneos/{tid}/participantes")
def inscribir(tid: int, b: ParticipanteIn):
    with tx() as t:
        tr = servicio.torneo(t, tid)
        _validar_grupo(t, tid, b.grupo_id)
        if t.one("SELECT 1 AS x FROM golf.Participante WHERE TorneoId = ? AND JugadorId = ?", (tid, b.jugador_id)):
            raise HTTPException(409, "Ese jugador ya está inscrito")
        idx, hcp = _calcular_hcp(t, tr, b.jugador_id, b.tee_id)
        if b.hcp_juego is not None:
            hcp = b.hcp_juego
        pid = t.insert(
            "INSERT INTO golf.Participante (TorneoId, JugadorId, GrupoId, TeeId, HandicapIndex, HandicapJuego) "
            "OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?)",
            (tid, b.jugador_id, b.grupo_id, b.tee_id, idx, hcp),
        )
        return {"id": pid, "hcp_juego": hcp}


@admin.put("/torneos/{tid}/participantes/{pid}")
def editar_participante(tid: int, pid: int, b: ParticipanteIn):
    with tx() as t:
        tr = servicio.torneo(t, tid)
        _validar_grupo(t, tid, b.grupo_id)
        idx, hcp = _calcular_hcp(t, tr, b.jugador_id, b.tee_id)
        if b.hcp_juego is not None:
            hcp = b.hcp_juego
        if not t.run(
            "UPDATE golf.Participante SET GrupoId = ?, TeeId = ?, HandicapIndex = ?, HandicapJuego = ? "
            "WHERE Id = ? AND TorneoId = ?",
            (b.grupo_id, b.tee_id, idx, hcp, pid, tid),
        ):
            raise HTTPException(404, "Participante no encontrado")
        return {"ok": True, "hcp_juego": hcp}


@admin.delete("/torneos/{tid}/participantes/{pid}")
def quitar_participante(tid: int, pid: int):
    with tx() as t:
        if not t.one("SELECT 1 AS x FROM golf.Participante WHERE Id = ? AND TorneoId = ?", (pid, tid)):
            raise HTTPException(404, "Participante no encontrado")
        t.run("DELETE FROM golf.Score WHERE ParticipanteId = ?", (pid,))
        t.run("DELETE FROM golf.Participante WHERE Id = ?", (pid,))
        return {"ok": True}


@admin.put("/torneos/{tid}/scores")
def admin_scores(tid: int, scores: list[ScoreIn]):
    with tx() as t:
        return {"guardados": _guardar_scores(t, tid, scores, None)}


@admin.get("/torneos/{tid}/grupos/{gid}/tarjeta")
def admin_tarjeta(tid: int, gid: int):
    with tx() as t:
        return _tarjeta(t, tid, gid)


@admin.post("/torneos/{tid}/apuestas")
def crear_apuesta(tid: int, b: ApuestaIn):
    if b.tipo != "skins" and not b.lado_b:
        raise HTTPException(422, "Un match necesita dos lados")
    if b.tipo == "skins" and len(b.lado_a) < 2:
        raise HTTPException(422, "Skins necesita al menos 2 jugadores")
    if set(b.lado_a) & set(b.lado_b):
        raise HTTPException(422, "Un jugador no puede estar en ambos lados")
    with tx() as t:
        _validar_grupo(t, tid, b.grupo_id)
        del_grupo = {r["id"] for r in t.all(
            "SELECT Id AS id FROM golf.Participante WHERE TorneoId = ? AND GrupoId = ?", (tid, b.grupo_id))}
        if not set(b.lado_a + b.lado_b) <= del_grupo:
            raise HTTPException(422, "Todos los jugadores de la apuesta deben ser del mismo grupo")
        aid = t.insert(
            "INSERT INTO golf.Apuesta (TorneoId, GrupoId, Tipo, Monto, Neto, LadoA, LadoB) "
            "OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, b.grupo_id, b.tipo, b.monto, int(b.neto),
             ",".join(map(str, b.lado_a)), ",".join(map(str, b.lado_b)) or None),
        )
        return {"id": aid}


@admin.delete("/torneos/{tid}/apuestas/{aid}")
def borrar_apuesta(tid: int, aid: int):
    with tx() as t:
        t.run("DELETE FROM golf.Apuesta WHERE Id = ? AND TorneoId = ?", (aid, tid))
        return {"ok": True}


router.include_router(admin)
