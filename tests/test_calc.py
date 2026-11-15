import pytest

from app.golf import calc

# Recorrido de prueba: par 72, handicaps 1..18 alternados ida impares / vuelta pares
PARES = [4, 4, 3, 5, 4, 4, 3, 4, 5, 4, 4, 3, 5, 4, 4, 3, 4, 5]
HCPS = [7, 15, 17, 1, 3, 11, 13, 5, 9, 8, 16, 18, 2, 4, 12, 14, 6, 10]
HOLES = [{"numero": i + 1, "par": p, "handicap": h} for i, (p, h) in enumerate(zip(PARES, HCPS))]


def test_par_total():
    assert sum(PARES) == 72 and sorted(HCPS) == list(range(1, 19))


@pytest.mark.parametrize("index,slope,rating,par,esperado", [
    (10.0, 113, 72.0, 72, 10),
    (12.4, 127, 73.0, 72, 15),      # 12.4*127/113 + 1 = 14.94 -> 15
    (0.0, 125, 71.0, 72, -1),
    (-2.0, 130, 74.0, 72, 0),       # -2.30 + 2 = -0.30 -> 0
    (18.0, None, None, 72, 18),     # sin rating/slope: usa el index
    (5.5, None, None, 72, 6),       # .5 redondea hacia arriba
])
def test_course_handicap(index, slope, rating, par, esperado):
    assert calc.course_handicap(index, slope, rating, par) == esperado


def test_playing_handicap():
    assert calc.playing_handicap(15, 100) == 15
    assert calc.playing_handicap(15, 85) == 13      # 12.75
    assert calc.playing_handicap(10, 85) == 9       # 8.5 -> 9


def test_golpes_en_hoyo_distribucion():
    for hcp in (0, 1, 9, 18, 20, 36, 40):
        total = sum(calc.golpes_en_hoyo(hcp, h["handicap"]) for h in HOLES)
        assert total == hcp
    assert calc.golpes_en_hoyo(20, 1) == 2 and calc.golpes_en_hoyo(20, 3) == 1
    assert calc.golpes_en_hoyo(9, 9) == 1 and calc.golpes_en_hoyo(9, 10) == 0


def test_handicap_plus_devuelve_en_hoyos_faciles():
    assert sum(calc.golpes_en_hoyo(-2, h["handicap"]) for h in HOLES) == -2
    assert calc.golpes_en_hoyo(-2, 18) == -1 and calc.golpes_en_hoyo(-2, 17) == -1
    assert calc.golpes_en_hoyo(-2, 16) == 0


def test_stableford():
    assert calc.puntos_stableford(4, 4) == 2
    assert calc.puntos_stableford(4, 3) == 3
    assert calc.puntos_stableford(5, 3) == 4
    assert calc.puntos_stableford(4, 6) == 0
    assert calc.puntos_stableford(4, 9) == 0


def test_resumen_jugador_neto_y_stableford():
    scores = {h["numero"]: h["par"] + 1 for h in HOLES}  # bogey en todos: 90
    r = calc.resumen_jugador(HOLES, scores, 18)
    assert r["gross"] == 90 and r["neto"] == 72 and r["neto_vs_par"] == 0
    assert r["stableford"] == 36 and r["ida"] + r["vuelta"] == 90 and r["jugados"] == 18


def test_resumen_parcial():
    r = calc.resumen_jugador(HOLES, {1: 5, 2: 4}, 10)
    assert r["jugados"] == 2 and r["gross_vs_par"] == 1
    assert r["neto"] == 5 - 1 + 4 - 0  # hoyo 1 hcp 7 recibe; hoyo 2 hcp 15 no


def test_leaderboard_empates_y_sin_jugar():
    filas = [
        {"nombre": "A", "jugados": 18, "neto_vs_par": -2, "gross_vs_par": 10, "stableford": 38},
        {"nombre": "B", "jugados": 18, "neto_vs_par": 1, "gross_vs_par": 5, "stableford": 35},
        {"nombre": "C", "jugados": 9, "neto_vs_par": -2, "gross_vs_par": 3, "stableford": 20},
        {"nombre": "D", "jugados": 0, "neto_vs_par": 0, "gross_vs_par": 0, "stableford": 0},
    ]
    neto = calc.ordenar_leaderboard([dict(f) for f in filas], "neto")
    assert [(f["nombre"], f["posicion"]) for f in neto] == [("A", "T1"), ("C", "T1"), ("B", "3"), ("D", "—")]
    gross = calc.ordenar_leaderboard([dict(f) for f in filas], "gross")
    assert [f["nombre"] for f in gross][:3] == ["C", "B", "A"]
    stb = calc.ordenar_leaderboard([dict(f) for f in filas], "stableford")
    assert stb[0]["nombre"] == "A" and stb[0]["posicion"] == "1"


def _todos(valor_por_hoyo):
    return {h["numero"]: valor_por_hoyo(h) for h in HOLES}


def test_match_individual_gross_cerrado():
    scores = {1: _todos(lambda h: h["par"]), 2: _todos(lambda h: h["par"] + 1)}
    m = calc.match_play(HOLES, [1], [2], scores, {1: 0, 2: 0}, neto=False)
    assert m["ganador"] == "A" and m["texto"] == "10&8" and m["jugados"] == 10


def test_match_neto_del_mas_bajo():
    # B (hcp 18) hace bogey en todo; A (hcp 0) par en todo -> neto empatan todos: A/S
    scores = {1: _todos(lambda h: h["par"]), 2: _todos(lambda h: h["par"] + 1)}
    m = calc.match_play(HOLES, [1], [2], scores, {1: 0, 2: 18}, neto=True)
    assert m["texto"] == "A/S" and m["ganador"] == "="
    # mismo resultado si ambos tienen handicap alto (diferencia de 18)
    m2 = calc.match_play(HOLES, [1], [2], scores, {1: 10, 2: 28}, neto=True)
    assert m2["texto"] == "A/S"


def test_match_parcial_y_mejor_bola():
    scores = {1: {1: 4, 2: 5}, 2: {1: 6, 2: 4}, 3: {1: 5, 2: 5}, 4: {1: 5, 2: 5}}
    m = calc.match_play(HOLES, [1, 2], [3, 4], scores, {1: 0, 2: 0, 3: 0, 4: 0}, neto=False)
    # hoyo 1: A 4 vs B 5 -> A; hoyo 2: A 4 vs B 5 -> A
    assert m["diferencia"] == 2 and m["jugados"] == 2 and m["texto"] == "2 UP tras 2"
    assert m["cerrado"] is False


def test_match_salida_hoyo_10():
    scores = {1: {10: 3}, 2: {10: 4}}
    m = calc.match_play(HOLES, [1], [2], scores, {1: 0, 2: 0}, neto=False, hoyo_salida=10)
    assert m["jugados"] == 1 and m["diferencia"] == 1


def test_nassau():
    a = _todos(lambda h: h["par"] if h["numero"] <= 9 else h["par"] + 1)
    b = _todos(lambda h: h["par"] + 1 if h["numero"] <= 9 else h["par"])
    n = calc.nassau(HOLES, [1], [2], {1: a, 2: b}, {1: 0, 2: 0}, neto=False)
    assert n["ida"]["ganador"] == "A" and n["vuelta"]["ganador"] == "B"
    assert n["total"]["ganador"] == "="


def test_skins_con_acumulado_y_balance():
    scores = {
        1: {1: 4, 2: 4, 3: 3},
        2: {1: 4, 2: 5, 3: 4},
        3: {1: 4, 2: 5, 3: 4},
    }
    s = calc.skins(HOLES, [1, 2, 3], scores, {1: 0, 2: 0, 3: 0}, monto=10, neto=False)
    # hoyo 1 empate (acumula), hoyo 2 gana 1 (2 skins), hoyo 3 gana 1 (1 skin)
    assert s["ganados"] == {1: 3, 2: 0, 3: 0}
    assert s["balance"] == {1: 60, 2: -30, 3: -30}
    assert sum(s["balance"].values()) == 0 and s["acumulado"] == 0


def test_skins_espera_a_todos():
    s = calc.skins(HOLES, [1, 2], {1: {1: 3}, 2: {}}, {1: 0, 2: 0}, monto=5, neto=False)
    assert s["ganados"] == {1: 0, 2: 0} and s["detalle"] == []


def test_estadisticas():
    sc = {h["numero"]: {"golpes": h["par"], "putts": 2, "fairway": True} for h in HOLES}
    sc[1] = {"golpes": 3, "putts": 1, "fairway": True}     # birdie
    sc[2] = {"golpes": 6, "putts": 3, "fairway": False}    # doble
    e = calc.estadisticas([{"holes": HOLES, "scores": sc, "hcp_juego": 10}])
    assert e["promedio_18"] == 73 and e["mejor_18"] == 73
    assert e["distribucion"]["birdie"] == 1 and e["distribucion"]["doble_o_peor"] == 1
    assert e["distribucion"]["par"] == 16
    assert e["fairways_pct"] == round(100 * 13 / 14, 1)  # 14 hoyos par 4/5, 1 fallado
    assert e["greens_regulacion_pct"] == round(100 * 17 / 18, 1)
