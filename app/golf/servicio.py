"""Lectura de datos de la base y armado de resultados (leaderboard, apuestas, historial)."""
from __future__ import annotations

from fastapi import HTTPException

from app.golf import calc
from app.golf.sql import Tx


def hoyos_recorrido(t: Tx, recorrido_id: int) -> list[dict]:
    rows = t.all(
        "SELECT Numero AS numero, Par AS par, Handicap AS handicap FROM golf.Hoyo "
        "WHERE RecorridoId = ? ORDER BY Numero",
        (recorrido_id,),
    )
    return rows


def recorrido_completo(hoyos: list[dict]) -> bool:
    return (
        len(hoyos) == 18
        and all(h["par"] and h["handicap"] for h in hoyos)
        and sorted(h["handicap"] for h in hoyos) == list(range(1, 19))
    )


def exigir_completo(hoyos: list[dict]) -> None:
    if not recorrido_completo(hoyos):
        raise HTTPException(
            409,
            "El recorrido no tiene completos el par y el handicap de los 18 hoyos. "
            "Captúralos en Administración → Recorridos.",
        )


def torneo(t: Tx, torneo_id: int) -> dict:
    row = t.one(
        "SELECT tr.Id AS id, tr.Nombre AS nombre, tr.Fecha AS fecha, tr.RecorridoId AS recorrido_id, "
        "r.Nombre AS recorrido, tr.Formato AS formato, tr.PctHandicap AS pct_handicap, tr.Estado AS estado "
        "FROM golf.Torneo tr JOIN golf.Recorrido r ON r.Id = tr.RecorridoId WHERE tr.Id = ?",
        (torneo_id,),
    )
    if not row:
        raise HTTPException(404, "Torneo no encontrado")
    return row


def participantes(t: Tx, torneo_id: int, grupo_id: int | None = None) -> list[dict]:
    sql = (
        "SELECT p.Id AS id, p.JugadorId AS jugador_id, j.Nombre AS nombre, p.GrupoId AS grupo_id, "
        "g.Nombre AS grupo, g.HoyoSalida AS hoyo_salida, p.TeeId AS tee_id, te.Nombre AS tee, "
        "te.Color AS tee_color, p.HandicapIndex AS handicap_index, p.HandicapJuego AS hcp_juego "
        "FROM golf.Participante p JOIN golf.Jugador j ON j.Id = p.JugadorId "
        "JOIN golf.Tee te ON te.Id = p.TeeId LEFT JOIN golf.Grupo g ON g.Id = p.GrupoId "
        "WHERE p.TorneoId = ?"
    )
    params: list = [torneo_id]
    if grupo_id is not None:
        sql += " AND p.GrupoId = ?"
        params.append(grupo_id)
    return t.all(sql + " ORDER BY g.Nombre, j.Nombre", params)


def scores_torneo(t: Tx, torneo_id: int) -> dict[int, dict[int, dict]]:
    rows = t.all(
        "SELECT s.ParticipanteId AS pid, s.Hoyo AS hoyo, s.Golpes AS golpes, s.Putts AS putts, "
        "s.Fairway AS fairway FROM golf.Score s JOIN golf.Participante p ON p.Id = s.ParticipanteId "
        "WHERE p.TorneoId = ?",
        (torneo_id,),
    )
    out: dict[int, dict[int, dict]] = {}
    for r in rows:
        fw = r["fairway"]
        out.setdefault(r["pid"], {})[r["hoyo"]] = {
            "golpes": r["golpes"], "putts": r["putts"], "fairway": None if fw is None else bool(fw),
        }
    return out


def leaderboard(t: Tx, torneo_id: int, formato: str | None = None) -> dict:
    tr = torneo(t, torneo_id)
    hoyos = hoyos_recorrido(t, tr["recorrido_id"])
    parts = participantes(t, torneo_id)
    sc = scores_torneo(t, torneo_id)
    filas = []
    for p in parts:
        golpes = {h: s["golpes"] for h, s in sc.get(p["id"], {}).items()}
        res = calc.resumen_jugador(hoyos, golpes, p["hcp_juego"])
        filas.append({**p, **res})
    fmt = formato or tr["formato"]
    return {"torneo": tr, "formato": fmt, "hoyos": hoyos,
            "filas": calc.ordenar_leaderboard(filas, fmt)}


def _ids(csv: str | None) -> list[int]:
    return [int(x) for x in (csv or "").split(",") if x.strip()]


def apuestas_grupo(t: Tx, torneo_id: int, grupo_id: int) -> list[dict]:
    tr = torneo(t, torneo_id)
    hoyos = hoyos_recorrido(t, tr["recorrido_id"])
    parts = {p["id"]: p for p in participantes(t, torneo_id, grupo_id)}
    sc = scores_torneo(t, torneo_id)
    golpes = {pid: {h: s["golpes"] for h, s in sc.get(pid, {}).items()} for pid in parts}
    hcps = {pid: p["hcp_juego"] for pid, p in parts.items()}
    salida = next(iter(parts.values()))["hoyo_salida"] if parts else 1
    out = []
    for a in t.all(
        "SELECT Id AS id, Tipo AS tipo, Monto AS monto, Neto AS neto, LadoA AS lado_a, LadoB AS lado_b "
        "FROM golf.Apuesta WHERE TorneoId = ? AND GrupoId = ? ORDER BY Id",
        (torneo_id, grupo_id),
    ):
        lado_a = [i for i in _ids(a["lado_a"]) if i in parts]
        lado_b = [i for i in _ids(a["lado_b"]) if i in parts]
        neto = bool(a["neto"])
        item = {**a, "neto": neto, "lado_a": lado_a, "lado_b": lado_b,
                "nombres_a": [parts[i]["nombre"] for i in lado_a],
                "nombres_b": [parts[i]["nombre"] for i in lado_b]}
        if a["tipo"] == "skins" and len(lado_a) >= 2:
            item["resultado"] = calc.skins(hoyos, lado_a, golpes, hcps, a["monto"], neto, salida)
            item["nombres"] = {i: parts[i]["nombre"] for i in lado_a}
        elif a["tipo"] == "match" and lado_a and lado_b:
            item["resultado"] = calc.match_play(hoyos, lado_a, lado_b, golpes, hcps, neto, None, salida)
        elif a["tipo"] == "nassau" and lado_a and lado_b:
            item["resultado"] = calc.nassau(hoyos, lado_a, lado_b, golpes, hcps, neto, salida)
        else:
            item["resultado"] = None
        out.append(item)
    return out


def historial_jugador(t: Tx, jugador_id: int) -> dict:
    j = t.one(
        "SELECT Id AS id, Nombre AS nombre, Genero AS genero, HandicapIndex AS handicap_index "
        "FROM golf.Jugador WHERE Id = ?",
        (jugador_id,),
    )
    if not j:
        raise HTTPException(404, "Jugador no encontrado")
    rondas_db = t.all(
        "SELECT p.Id AS pid, p.TorneoId AS torneo_id, tr.Nombre AS torneo, tr.Fecha AS fecha, "
        "tr.RecorridoId AS recorrido_id, r.Nombre AS recorrido, p.HandicapJuego AS hcp_juego, "
        "te.Nombre AS tee FROM golf.Participante p JOIN golf.Torneo tr ON tr.Id = p.TorneoId "
        "JOIN golf.Recorrido r ON r.Id = tr.RecorridoId JOIN golf.Tee te ON te.Id = p.TeeId "
        "WHERE p.JugadorId = ? ORDER BY tr.Fecha DESC, tr.Id DESC",
        (jugador_id,),
    )
    pids = [r["pid"] for r in rondas_db]
    sc: dict[int, dict[int, dict]] = {}
    if pids:
        marcas = ",".join("?" * len(pids))
        for s in t.all(
            f"SELECT ParticipanteId AS pid, Hoyo AS hoyo, Golpes AS golpes, Putts AS putts, "
            f"Fairway AS fairway FROM golf.Score WHERE ParticipanteId IN ({marcas})",
            pids,
        ):
            fw = s["fairway"]
            sc.setdefault(s["pid"], {})[s["hoyo"]] = {
                "golpes": s["golpes"], "putts": s["putts"], "fairway": None if fw is None else bool(fw)}
    hoyos_cache: dict[int, list[dict]] = {}
    rondas, para_stats = [], []
    for r in rondas_db:
        hoyos = hoyos_cache.setdefault(r["recorrido_id"], hoyos_recorrido(t, r["recorrido_id"]))
        s = sc.get(r["pid"], {})
        if not s or not recorrido_completo(hoyos):
            continue
        res = calc.resumen_jugador(hoyos, {h: v["golpes"] for h, v in s.items()}, r["hcp_juego"])
        res.pop("hoyos")
        rondas.append({**r, **res})
        para_stats.append({"holes": hoyos, "scores": s, "hcp_juego": r["hcp_juego"]})
    return {"jugador": j, "rondas": rondas, "estadisticas": calc.estadisticas(para_stats)}
