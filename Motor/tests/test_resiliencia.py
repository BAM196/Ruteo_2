import math

import numpy as np
import pytest

from motor import resiliencia, servicio


def test_r_plan_es_producto_de_vuelos(esc, con_amenaza):
    res = servicio.planificar(con_amenaza, esc, n_mc=4000)
    for p in res["planes"]:
        assert p["R"] == pytest.approx(math.prod(v["R"] for v in p["vuelos"]))
        assert p["analitico_en_ic"]


def test_montecarlo_converge():
    elems = [[{"p": 0.1}, {"p": 0.2}], [{"p": 0.05}]]
    mc = resiliencia.montecarlo_plan(elems, 20000, 1)
    assert mc["r_mc"] == pytest.approx(0.9 * 0.8 * 0.95, abs=0.01)
    assert mc["ic95"][0] <= 0.9 * 0.8 * 0.95 <= mc["ic95"][1]


def test_regla_de_sorteo():
    rng = np.random.default_rng(0)
    falla = resiliencia.sortear(np.array([0.0, 1.0]), 1000, rng)
    assert not falla[:, 0].any() and falla[:, 1].all()


def test_sorteo_de_fallas_por_vuelo(esc, con_amenaza):
    res = servicio.planificar(con_amenaza, esc, n_mc=200)
    vuelos = [{**v, "tecnica": p["tecnica"]} for p in res["planes"] for v in p["vuelos"]]
    a = servicio.simular_fallas(vuelos, semilla=3)
    b = servicio.simular_fallas(vuelos, semilla=3)
    assert a == b
    for v in a["vuelos"]:
        assert v["falla"] == any(e["falla"] for e in v["elementos"])
        for e in v["elementos"]:
            assert e["falla"] == (e["r"] <= 100 * e["p"] + 1e-9)


def test_leyenda(esc, consulta):
    res = servicio.planificar(consulta, esc, n_mc=200)
    for p in res["planes"]:
        assert p["leyenda"].count("|") == 5 and "R plan" in p["leyenda"]
