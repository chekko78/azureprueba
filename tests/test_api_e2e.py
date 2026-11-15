"""Prueba de punta a punta contra un SQL Server real (local o de pruebas).

Se ejecuta solo si GOLF_E2E=1 y la base ya tiene el esquema (sql/10_golf_esquema.sql).
"""
import os
import random

import pytest

pytestmark = pytest.mark.skipif(os.getenv("GOLF_E2E") != "1", reason="requiere GOLF_E2E=1 y SQL Server")

PARES = [4, 4, 3, 5, 4, 4, 3, 4, 5, 4, 4, 3, 5, 4, 4, 3, 4, 5]
HCPS = [7, 15, 17, 1, 3, 11, 13, 5, 9, 8, 16, 18, 2, 4, 12, 14, 6, 10]


@pytest.fixture(scope="module")
def c():
    os.environ.setdefault("ADMIN_PASSWORD", "clave-admin-prueba")
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_flujo_torneo_completo(c):
    sufijo = random.randint(1000, 9999)
    # --- admin
    assert c.post("/api/admin/login", json={"password": "mala"}).status_code == 401
    tok = c.post("/api/admin/login", json={"password": os.environ["ADMIN_PASSWORD"]}).json()["token"]
    A = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/admin/jugadores", json={"nombre": "x"}).status_code == 401  # sin token

    rec = next(r for r in c.get("/api/recorridos").json() if r["nombre"] == "Silla / Mitras")
    # torneo en recorrido incompleto -> 409
    hoyos_vacios = [{"numero": n, "par": None, "handicap": None} for n in range(1, 19)]
    c.put(f"/api/admin/recorridos/{rec['id']}/hoyos", json=hoyos_vacios, headers=A)
    r = c.post("/api/admin/torneos", json={"nombre": "X", "fecha": "2026-11-15", "recorrido_id": rec["id"]}, headers=A)
    assert r.status_code == 409
    # handicaps repetidos -> 422
    malos = [{"numero": n, "par": 4, "handicap": 1} for n in range(1, 19)]
    assert c.put(f"/api/admin/recorridos/{rec['id']}/hoyos", json=malos, headers=A).status_code == 422
    buenos = [{"numero": n + 1, "par": p, "handicap": h} for n, (p, h) in enumerate(zip(PARES, HCPS))]
    r = c.put(f"/api/admin/recorridos/{rec['id']}/hoyos", json=buenos, headers=A).json()
    assert r == {"completo": True, "par": 72}

    detalle = c.get(f"/api/recorridos/{rec['id']}").json()
    negras = next(t for t in detalle["tees"] if t["nombre"] == "Negras")
    blancas = next(t for t in detalle["tees"] if t["nombre"] == "Blancas")
    assert negras["rating_h"] == 73.0 and negras["slope_h"] == 127
    r = c.put(f"/api/admin/tees/{blancas['id']}", headers=A, json={
        "nombre": "Blancas", "color": "#e5e7eb", "rating_h": 69.2, "slope_h": 120, "orden": 3,
        "yardas": [380 + i for i in range(18)]})
    assert r.status_code == 200

    ids = []
    for nombre, idx in [("Ana", 12.4), ("Beto", 0.0), ("Carlos", 18.0), ("Dani", 25.3)]:
        ids.append(c.post("/api/admin/jugadores", json={"nombre": f"{nombre} {sufijo}", "handicap_index": idx},
                          headers=A).json()["id"])

    tid = c.post("/api/admin/torneos", headers=A, json={
        "nombre": f"Prueba {sufijo}", "fecha": "2026-11-15", "recorrido_id": rec["id"], "formato": "neto"}).json()["id"]
    g = c.post(f"/api/admin/torneos/{tid}/grupos", headers=A, json={"nombre": "Grupo 1", "hoyo_salida": 1}).json()
    assert len(g["pin"]) == 6
    pids = {}
    for jid in ids:
        r = c.post(f"/api/admin/torneos/{tid}/participantes", headers=A,
                   json={"jugador_id": jid, "tee_id": negras["id"], "grupo_id": g["id"]}).json()
        pids[jid] = r
    # Ana 12.4 en negras (73.0/127, par 72): 12.4*127/113 + 1 = 14.94 -> 15
    assert pids[ids[0]]["hcp_juego"] == 15
    assert c.post(f"/api/admin/torneos/{tid}/participantes", headers=A,
                  json={"jugador_id": ids[0], "tee_id": negras["id"]}).status_code == 409

    p = [pids[j]["id"] for j in ids]
    r = c.post(f"/api/admin/torneos/{tid}/apuestas", headers=A, json={
        "grupo_id": g["id"], "tipo": "match", "monto": 100, "lado_a": [p[0], p[1]], "lado_b": [p[2], p[3]]})
    assert r.status_code == 200
    c.post(f"/api/admin/torneos/{tid}/apuestas", headers=A, json={
        "grupo_id": g["id"], "tipo": "skins", "monto": 50, "neto": False, "lado_a": p})
    c.post(f"/api/admin/torneos/{tid}/apuestas", headers=A, json={
        "grupo_id": g["id"], "tipo": "nassau", "monto": 20, "lado_a": [p[0]], "lado_b": [p[1]]})

    # --- capturista con PIN
    assert c.post(f"/api/torneos/{tid}/acceso", json={"pin": "12345"}).status_code == 422
    malo = "000000" if g["pin"] != "000000" else "111111"
    assert c.post(f"/api/torneos/{tid}/acceso", json={"pin": malo}).status_code == 401
    gtok = c.post(f"/api/torneos/{tid}/acceso", json={"pin": g["pin"]}).json()["token"]
    G = {"Authorization": f"Bearer {gtok}"}
    tarjeta = c.get("/api/grupo", headers=G).json()
    assert len(tarjeta["participantes"]) == 4 and len(tarjeta["hoyos"]) == 18
    blanco = c.get(f"/api/recorridos/{rec['id']}").json()
    assert next(t for t in blanco["tees"] if t["id"] == blancas["id"])["yardas"][0] == 380

    lote = []
    for i, pid in enumerate(p):
        for n, par in enumerate(PARES, start=1):
            lote.append({"participante_id": pid, "hoyo": n, "golpes": par + i, "putts": 2,
                         "fairway": (n % 2 == 0) if par >= 4 else None})
    assert c.put("/api/grupo/scores", json=lote, headers=G).json()["guardados"] == 72
    # corrección (upsert) y borrado
    c.put("/api/grupo/scores", json=[{"participante_id": p[0], "hoyo": 1, "golpes": 3, "putts": 1}], headers=G)
    # jugador de otro torneo -> 403
    assert c.put("/api/grupo/scores", json=[{"participante_id": 999999, "hoyo": 1, "golpes": 4}], headers=G).status_code == 403
    # token de grupo no sirve para admin
    assert c.post("/api/admin/jugadores", json={"nombre": "x"}, headers=G).status_code == 403

    lb = c.get(f"/api/torneos/{tid}/leaderboard").json()
    filas = {f["jugador_id"]: f for f in lb["filas"]}
    assert filas[ids[0]]["gross"] == 71 and filas[ids[0]]["jugados"] == 18
    assert filas[ids[1]]["gross"] == 72 + 18
    assert lb["filas"][0]["posicion"] in ("1", "T1")
    stb = c.get(f"/api/torneos/{tid}/leaderboard?formato=stableford").json()
    assert stb["formato"] == "stableford"

    ap = c.get(f"/api/torneos/{tid}/grupos/{g['id']}/apuestas").json()
    tipos = {a["tipo"]: a for a in ap}
    assert tipos["skins"]["resultado"]["ganados"][str(p[0])] == 18  # Ana gana todos en gross
    assert tipos["match"]["resultado"]["cerrado"] is True
    assert tipos["nassau"]["resultado"]["total"]["jugados"] >= 1

    hist = c.get(f"/api/jugadores/{ids[0]}").json()
    assert hist["estadisticas"]["rondas"] == 1 and hist["estadisticas"]["mejor_18"] == 71
    assert hist["estadisticas"]["putts_por_hoyo"] is not None

    # --- cerrar torneo: ya no se capturan scores ni se entra con PIN
    c.post(f"/api/admin/torneos/{tid}/estado/cerrado", headers=A)
    assert c.put("/api/grupo/scores", json=[{"participante_id": p[0], "hoyo": 2, "golpes": 4}], headers=G).status_code == 409
    assert c.post(f"/api/torneos/{tid}/acceso", json={"pin": g["pin"]}).status_code == 409
    assert c.get("/api/grupo", headers={"Authorization": "Bearer basura.firma"}).status_code == 401


def test_pagina_y_pwa(c):
    r = c.get("/")
    assert r.status_code == 200 and "Golf Campestre" in r.text
    assert c.get("/static/manifest.json").json()["display"] == "standalone"
    assert c.get("/sw.js").headers["content-type"].startswith("application/javascript")
    assert c.get("/static/icons/icon-180.png").status_code == 200
