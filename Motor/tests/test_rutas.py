import copy
import itertools

import pytest

from motor import probabilidades, servicio
from motor.config import amenazas_cfg
from motor.rutas import aco, dijkstra_distancia, dijkstra_ponderado, milp
from motor.rutas.comun import Consulta, Contexto, ProblemaSector


def problema(esc, consulta, base_id=1):
    c = Consulta.desde_dict(consulta)
    cfg = amenazas_cfg()
    ctx = Contexto(esc, probabilidades.calcular(esc, cfg, c.overrides_prob), c, cfg["cota_superior"])
    prob = ProblemaSector(ctx, esc.bases[base_id], c.camaras, "T")
    dijkstra_distancia.resolver(prob)
    prob.calcular_tramos("modelo")
    return prob


def particiones(xs):
    if not xs:
        yield []
        return
    primero, resto = xs[0], xs[1:]
    for p in particiones(resto):
        for i in range(len(p)):
            yield p[:i] + [[primero] + p[i]] + p[i + 1:]
        yield [[primero]] + p


def fuerza_bruta(prob):
    mejor = None
    for part in particiones(prob.camaras):
        for perms in itertools.product(*[list(itertools.permutations(b)) for b in part]):
            ev = prob.evaluar([list(x) for x in perms], prob.tramos_modelo)
            if ev["factible"] and (mejor is None or ev["total"]["costo"] < mejor - 1e-12):
                mejor = ev["total"]["costo"]
    return mejor


def test_bateria_obliga_a_varios_vuelos(esc, consulta):
    res = servicio.planificar(consulta, esc, n_mc=500)
    for p in res["planes"]:
        assert len(p["vuelos"]) >= 2
        for v in p["vuelos"]:
            assert v["tiempo_s"] <= res["parametros"]["bateria"]["util_s"] + 1e-6
            assert v["nodos"][0] == v["nodos"][-1] == 1
        assert sorted(c for v in p["vuelos"] for c in v["camaras"]) == [1, 2, 3, 4]


def test_gurobi_igual_al_optimo_por_fuerza_bruta(esc, con_amenaza):
    prob = problema(esc, con_amenaza)
    r = milp.resolver(prob)
    assert r["factible"]
    assert r["total"]["costo"] == pytest.approx(fuerza_bruta(prob), rel=1e-9)


def test_aco_nunca_mejor_que_gurobi(esc, con_amenaza):
    prob = problema(esc, con_amenaza)
    opt = milp.resolver(prob)["total"]["costo"]
    for semilla in range(10):
        r = aco.resolver(prob, semilla=semilla, config="config_mai", params={"iteraciones": 30})
        assert r["total"]["costo"] >= opt - 1e-9


def test_aco_encuentra_el_optimo_en_la_mayoria(esc, con_amenaza):
    prob = problema(esc, con_amenaza)
    opt = milp.resolver(prob)["total"]["costo"]
    aciertos = sum(abs(aco.resolver(prob, semilla=s)["total"]["costo"] - opt) < 1e-9 for s in range(20))
    assert aciertos >= 15


def test_aco_misma_semilla_mismo_resultado(esc, con_amenaza):
    prob = problema(esc, con_amenaza)
    a = aco.resolver(prob, semilla=7, params={"iteraciones": 20})
    b = aco.resolver(prob, semilla=7, params={"iteraciones": 20})
    assert [v["camaras"] for v in a["vuelos"]] == [v["camaras"] for v in b["vuelos"]]
    assert a["extra"]["convergencia"] == b["extra"]["convergencia"]


def test_con_amenaza_el_modelo_se_desvia(esc, con_amenaza):
    res = servicio.planificar(con_amenaza, esc, n_mc=500)
    planes = {p["tecnica"]: p for p in res["planes"]}
    usa = lambda p: any(4 in v["aristas"] for v in p["vuelos"])
    assert usa(planes["dijkstra_distancia"])
    for t in ("milp", "dijkstra_ponderado", "aco"):
        assert not usa(planes[t])
        assert planes[t]["R"] > planes["dijkstra_distancia"]["R"]
    assert res["mas_resiliente"] != "dijkstra_distancia"


def test_theta_cero_gurobi_tan_rapido_como_tecnica_1(esc, con_amenaza):
    c = copy.deepcopy(con_amenaza)
    c["theta"] = 0.0
    res = servicio.planificar(c, esc, n_mc=500)
    planes = {p["tecnica"]: p for p in res["planes"]}
    traslado = lambda p: sum(v["tiempo_traslado_s"] for v in p["vuelos"])
    assert traslado(planes["milp"]) <= traslado(planes["dijkstra_distancia"]) + 1e-6


def test_solo_bosque_excluye_la_camara_de_pastizal(esc, consulta):
    c = copy.deepcopy(consulta)
    c["restricciones"] = {"solo_bosque": True}
    res = servicio.planificar(c, esc, n_mc=500)
    assert "4" in res["no_visitadas"]
    for p in res["planes"]:
        assert all(4 not in v["camaras"] and 4 not in v["nodos"] for v in p["vuelos"])


def test_excluir_camara(esc, consulta):
    c = copy.deepcopy(consulta)
    c["restricciones"] = {"excluir_nodos": [3]}
    res = servicio.planificar(c, esc, n_mc=500)
    for p in res["planes"]:
        assert all(3 not in v["camaras"] for v in p["vuelos"])


def test_base_que_no_ve_todas_las_camaras(esc, consulta):
    c = copy.deepcopy(consulta)
    c["base_id"] = 100000
    res = servicio.planificar(c, esc, n_mc=500)
    assert {"3", "4"} <= set(res["no_visitadas"])
    for p in res["planes"]:
        assert all(v["nodos"][0] == 100000 for v in p["vuelos"])


def test_r_minimo_inalcanzable_avisa(esc, con_amenaza):
    c = copy.deepcopy(con_amenaza)
    c["overrides_prob"] = {"nodos": {"2": 0.6}}
    c["r_min"] = 0.95
    res = servicio.planificar(c, esc, n_mc=500)
    assert res["resiliencia"]["aviso"]


def test_tecnica_3_no_impone_mas_que_vecino_mas_cercano(esc, con_amenaza):
    prob = problema(esc, con_amenaza)
    r3 = dijkstra_ponderado.resolver(prob)
    r2 = milp.resolver(prob)
    assert r3["total"]["costo"] >= r2["total"]["costo"] - 1e-9


def test_modo_sector_y_especie(esc):
    res = servicio.planificar({"modo": "especie", "especie": "Pudu puda"}, esc, n_mc=200)
    assert sorted(c for p in res["planes"][:1] for v in p["vuelos"] for c in v["camaras"]) == [1, 2]
    res = servicio.planificar({"modo": "parque"}, esc, n_mc=200)
    assert len(res["sectores"]) == 2
