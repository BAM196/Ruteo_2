import pytest

from motor import resiliencia, servicio


def test_r_analitico_en_ic_montecarlo():
    q = {1: 0.1, 2: 0.05, 3: 0.2}
    p = {10: 0.3, 11: 0.15}
    r = resiliencia.r_analitico([1, 2, 3], [10, 11], q, p)
    assert r == pytest.approx(0.9 * 0.95 * 0.8 * 0.7 * 0.85)
    mc = resiliencia.montecarlo([1, 2, 3], [10, 11], q, p, n=10_000, semilla=1)
    assert mc["ic95"][0] <= r <= mc["ic95"][1]


def test_regla_d4_extremos():
    import numpy as np

    rng = np.random.default_rng(0)
    f = resiliencia.sortear_fallas(np.array([0.0, 1.0]), 1000, rng)
    assert not f[:, 0].any()
    assert f[:, 1].all()


def test_leyenda_y_ranking(esc, con_amenaza):
    res = servicio.calcular_rutas(con_amenaza, esc, n_mc=5000)
    milp = next(r for r in res["rutas"] if r["tecnica"] == "milp")
    assert milp["leyenda"] == "Gurobi (MILP) | 2,2 km | R = 1,000 | " + milp["leyenda"].split(" | ")[-1]
    assert milp["delta_R"] == pytest.approx(0.9)
    assert res["resiliencia"]["ranking"][-1] == "dijkstra_distancia"
    for r in res["rutas"]:
        if r["R"] is not None:
            assert r["analitico_en_ic"]


def test_simular_fallas(esc):
    out = servicio.simular_fallas(esc, {"aristas": {"2": 1.0}}, semilla=3)
    a2 = next(a for a in out["aristas"] if a["id"] == 2)
    assert a2["falla"]
    assert not any(n["falla"] for n in out["nodos"])
