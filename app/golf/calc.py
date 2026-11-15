"""Cálculos de golf: handicap (WHS), neto, Stableford, leaderboard, match, nassau y skins.

Funciones puras (sin base de datos) para poder probarlas fácilmente.
`holes` es una lista de 18 dicts: {"numero": 1..18, "par": int, "handicap": 1..18}.
`scores` es un dict {numero_de_hoyo: golpes}.
"""
from __future__ import annotations

import math


def redondear(x: float) -> int:
    """Redondeo .5 hacia arriba (como en el sistema de handicap), no el 'bancario' de Python."""
    return math.floor(x + 0.5)


def course_handicap(index: float, slope: int | None, rating: float | None, par: int) -> int:
    """Handicap de campo WHS: Index × Slope/113 + (Rating − Par).

    Si la salida no tiene rating/slope capturados, usa el index tal cual.
    """
    if slope is None or rating is None:
        return redondear(float(index))
    return redondear(float(index) * slope / 113 + (float(rating) - par))


def playing_handicap(course_hcp: int, pct: int = 100) -> int:
    return redondear(course_hcp * pct / 100)


def golpes_en_hoyo(hcp_juego: int, hoyo_hcp: int) -> int:
    """Golpes de ventaja que recibe el jugador en un hoyo (negativo si es handicap 'plus')."""
    if hcp_juego >= 0:
        return hcp_juego // 18 + (1 if hoyo_hcp <= hcp_juego % 18 else 0)
    p = -hcp_juego  # los 'plus' devuelven golpes empezando por los hoyos más fáciles
    return -(p // 18 + (1 if hoyo_hcp > 18 - p % 18 else 0))


def puntos_stableford(par: int, neto: int) -> int:
    return max(0, 2 + par - neto)


def resumen_jugador(holes: list[dict], scores: dict[int, int], hcp_juego: int) -> dict:
    """Totales de un jugador sobre los hoyos jugados."""
    detalle = []
    gross = neto = par_jugado = stb = 0
    ida = vuelta = 0
    for h in holes:
        n = h["numero"]
        g = scores.get(n)
        recibe = golpes_en_hoyo(hcp_juego, h["handicap"])
        fila = {"hoyo": n, "par": h["par"], "handicap": h["handicap"], "recibe": recibe,
                "golpes": g, "neto": None, "stableford": None}
        if g is not None:
            nt = g - recibe
            pts = puntos_stableford(h["par"], nt)
            fila.update(neto=nt, stableford=pts)
            gross += g
            neto += nt
            par_jugado += h["par"]
            stb += pts
            if n <= 9:
                ida += g
            else:
                vuelta += g
        detalle.append(fila)
    jugados = sum(1 for f in detalle if f["golpes"] is not None)
    return {
        "jugados": jugados,
        "gross": gross,
        "neto": neto,
        "gross_vs_par": gross - par_jugado,
        "neto_vs_par": neto - par_jugado,
        "stableford": stb,
        "ida": ida,
        "vuelta": vuelta,
        "hoyos": detalle,
    }


def ordenar_leaderboard(filas: list[dict], formato: str) -> list[dict]:
    """Ordena y asigna posiciones (con empates: 'T2'). Quien no ha jugado va al final."""
    if formato == "stableford":
        clave = lambda f: (-f["stableford"], -f["jugados"])  # noqa: E731
        valor = lambda f: f["stableford"]  # noqa: E731
    elif formato == "gross":
        clave = lambda f: (f["gross_vs_par"], -f["jugados"])  # noqa: E731
        valor = lambda f: f["gross_vs_par"]  # noqa: E731
    else:
        clave = lambda f: (f["neto_vs_par"], -f["jugados"])  # noqa: E731
        valor = lambda f: f["neto_vs_par"]  # noqa: E731

    con = sorted([f for f in filas if f["jugados"] > 0], key=clave)
    sin = sorted([f for f in filas if f["jugados"] == 0], key=lambda f: f["nombre"])
    for i, f in enumerate(con):
        empatados = [x for x in con if valor(x) == valor(f)]
        pos = con.index(empatados[0]) + 1
        f["posicion"] = f"T{pos}" if len(empatados) > 1 else str(pos)
    for f in sin:
        f["posicion"] = "—"
    return con + sin


# ---------------------------------------------------------------- apuestas

def _orden_juego(hoyo_salida: int) -> list[int]:
    return [((hoyo_salida - 1 + i) % 18) + 1 for i in range(18)]


def _ventajas(hcps: dict[int, int], neto: bool) -> dict[int, int]:
    """Golpes 'del más bajo': el de menor handicap juega a 0 y los demás reciben la diferencia."""
    if not neto:
        return {pid: 0 for pid in hcps}
    bajo = min(hcps.values())
    return {pid: h - bajo for pid, h in hcps.items()}


def _score_lado(lado, hoyo, holes_by_num, scores, ventaja):
    """Mejor bola neta del lado en el hoyo (None si nadie del lado lo ha capturado)."""
    vals = []
    for pid in lado:
        g = scores.get(pid, {}).get(hoyo)
        if g is not None:
            vals.append(g - golpes_en_hoyo(ventaja[pid], holes_by_num[hoyo]["handicap"]))
    return min(vals) if vals else None


def match_play(holes, lado_a, lado_b, scores, hcps, neto=True, hoyos=None, hoyo_salida=1):
    """Match (individual o mejor bola por parejas).

    scores: {participante_id: {hoyo: golpes}}, hcps: {participante_id: handicap_juego}.
    Devuelve el estado: diferencia (+ gana A), hoyos jugados, si está cerrado y texto.
    """
    holes_by_num = {h["numero"]: h for h in holes}
    hoyos = hoyos or list(range(1, 19))
    orden = [n for n in _orden_juego(hoyo_salida) if n in hoyos]
    ventaja = _ventajas({p: hcps[p] for p in lado_a + lado_b}, neto)
    dif = jugados = 0
    detalle = []
    for i, n in enumerate(orden):
        a = _score_lado(lado_a, n, holes_by_num, scores, ventaja)
        b = _score_lado(lado_b, n, holes_by_num, scores, ventaja)
        if a is None or b is None:
            break
        jugados += 1
        gana = "A" if a < b else "B" if b < a else "="
        dif += 1 if gana == "A" else -1 if gana == "B" else 0
        detalle.append({"hoyo": n, "a": a, "b": b, "gana": gana})
        restantes = len(orden) - (i + 1)
        if abs(dif) > restantes:  # match cerrado
            ganador = "A" if dif > 0 else "B"
            return {"diferencia": dif, "jugados": jugados, "cerrado": True, "ganador": ganador,
                    "texto": f"{abs(dif)}&{restantes}" if restantes else f"{abs(dif)} UP",
                    "detalle": detalle}
    terminado = jugados == len(orden)
    if dif == 0:
        texto = "A/S" if terminado else f"A/S tras {jugados}"
    else:
        texto = f"{abs(dif)} UP" + ("" if terminado else f" tras {jugados}")
    ganador = None
    if terminado:
        ganador = "A" if dif > 0 else "B" if dif < 0 else "="
    return {"diferencia": dif, "jugados": jugados, "cerrado": terminado, "ganador": ganador,
            "texto": texto, "detalle": detalle}


def nassau(holes, lado_a, lado_b, scores, hcps, neto=True, hoyo_salida=1):
    """Tres matches: ida (1-9), vuelta (10-18) y total."""
    return {
        "ida": match_play(holes, lado_a, lado_b, scores, hcps, neto, list(range(1, 10)), hoyo_salida),
        "vuelta": match_play(holes, lado_a, lado_b, scores, hcps, neto, list(range(10, 19)), hoyo_salida),
        "total": match_play(holes, lado_a, lado_b, scores, hcps, neto, None, hoyo_salida),
    }


def skins(holes, jugadores, scores, hcps, monto, neto=True, hoyo_salida=1):
    """Skins: el score más bajo y único del hoyo gana; si hay empate se acumula al siguiente.

    Solo cuenta hoyos donde TODOS los jugadores ya capturaron.
    Cada skin vale `monto` de cada uno de los demás jugadores.
    """
    holes_by_num = {h["numero"]: h for h in holes}
    ventaja = _ventajas({p: hcps[p] for p in jugadores}, neto)
    acumulado = 0
    ganados = {p: 0 for p in jugadores}
    detalle = []
    for n in _orden_juego(hoyo_salida):
        netos = {}
        for p in jugadores:
            g = scores.get(p, {}).get(n)
            if g is None:
                break
            netos[p] = g - golpes_en_hoyo(ventaja[p], holes_by_num[n]["handicap"])
        if len(netos) < len(jugadores):
            break
        acumulado += 1
        mejor = min(netos.values())
        quienes = [p for p, v in netos.items() if v == mejor]
        if len(quienes) == 1:
            ganados[quienes[0]] += acumulado
            detalle.append({"hoyo": n, "ganador": quienes[0], "skins": acumulado})
            acumulado = 0
        else:
            detalle.append({"hoyo": n, "ganador": None, "skins": 0})
    total = sum(ganados.values())
    otros = len(jugadores) - 1
    balance = {p: round(monto * (ganados[p] * otros - (total - ganados[p])), 2) for p in jugadores}
    return {"ganados": ganados, "balance": balance, "acumulado": acumulado, "detalle": detalle}


# ------------------------------------------------------------ estadísticas

def estadisticas(rondas: list[dict]) -> dict:
    """rondas: [{"holes": [...], "scores": {hoyo: {"golpes","putts","fairway"}}, "hcp_juego": int}]."""
    dist = {"eagle_o_mejor": 0, "birdie": 0, "par": 0, "bogey": 0, "doble_o_peor": 0}
    putts = putt_hoyos = fw_ok = fw_total = gir = gir_total = 0
    completas = []
    for r in rondas:
        sc = r["scores"]
        if len(sc) == 18:
            completas.append(sum(s["golpes"] for s in sc.values()))
        for h in r["holes"]:
            s = sc.get(h["numero"])
            if not s:
                continue
            d = s["golpes"] - h["par"]
            key = ("eagle_o_mejor" if d <= -2 else "birdie" if d == -1 else "par" if d == 0
                   else "bogey" if d == 1 else "doble_o_peor")
            dist[key] += 1
            if s.get("putts") is not None:
                putts += s["putts"]
                putt_hoyos += 1
                gir_total += 1
                if s["golpes"] - s["putts"] <= h["par"] - 2:
                    gir += 1
            if h["par"] >= 4 and s.get("fairway") is not None:
                fw_total += 1
                fw_ok += 1 if s["fairway"] else 0
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    return {
        "rondas": len(rondas),
        "rondas_completas": len(completas),
        "promedio_18": round(sum(completas) / len(completas), 1) if completas else None,
        "mejor_18": min(completas) if completas else None,
        "putts_por_hoyo": round(putts / putt_hoyos, 2) if putt_hoyos else None,
        "fairways_pct": pct(fw_ok, fw_total),
        "greens_regulacion_pct": pct(gir, gir_total),
        "distribucion": dist,
    }
