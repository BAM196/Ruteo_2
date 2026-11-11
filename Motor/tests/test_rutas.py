import copy

import pytest

from motor import servicio
from motor.rutas import aco, dijkstra_distancia, dijkstra_ponderado, milp


def _todas(esc, consulta):
    res = servicio.calcular_rutas(consulta, esc, n_mc=2000)
    return {r["tecnica"]: r for r in res["rutas"]}, res


def test_sin_amenazas_todas_eligen_la_mas_corta(esc, consulta):
    rutas, res = _todas(esc, consulta)
    for r in rutas.values():
        assert r["nodos"] == [1, 2, 7]
        assert r["distancia_m"] == 2000
        assert r["R"] == pytest.approx(1.0)


def test_theta_cero_milp_igual_a_tecnica_1(esc, con_amenaza):
    c = copy.deepcopy(con_amenaza)
    c["theta"] = 0.0
    rutas, _ = _todas(esc, c)
    assert rutas["milp"]["distancia_m"] == rutas["dijkstra_distancia"]["distancia_m"]
    assert rutas["dijkstra_ponderado"]["nodos"] == rutas["dijkstra_distancia"]["nodos"]


def test_con_amenaza_se_desvia(esc, con_amenaza):
    rutas, res = _todas(esc, con_amenaza)
    assert rutas["dijkstra_distancia"]["nodos"] == [1, 2, 7]
    assert rutas["milp"]["nodos"] == [1, 3, 6, 7]
    assert rutas["milp"]["costo"] == pytest.approx(0.55, abs=1e-4)
    assert rutas["dijkstra_ponderado"]["nodos"] == [1, 3, 6, 7]
    assert rutas["aco"]["nodos"] == [1, 3, 6, 7]
    assert rutas["milp"]["R"] > rutas["dijkstra_distancia"]["R"]
    assert res["mas_resiliente"] in ("milp", "dijkstra_ponderado", "aco")


def test_autonomia_no_activa_milp_igual_a_tecnica_3(esc, con_amenaza):
    rutas, _ = _todas(esc, con_amenaza)
    assert rutas["milp"]["costo"] == pytest.approx(rutas["dijkstra_ponderado"]["costo"], rel=1e-9)


def test_solo_bosque(esc, con_amenaza):
    c = copy.deepcopy(con_amenaza)
    c["restricciones"]["solo_bosque"] = True
    rutas, _ = _todas(esc, c)
    assert rutas["milp"]["nodos"] == [1, 3, 7]
    assert rutas["dijkstra_ponderado"]["nodos"] == [1, 3, 7]


def test_autonomia_activa_diferencia_tecnica_2_y_3(esc, con_amenaza):
    c = copy.deepcopy(con_amenaza)
    c["autonomia_m"] = 2100
    rutas, _ = _todas(esc, c)
    assert rutas["milp"]["nodos"] == [1, 2, 7] and rutas["milp"]["factible"]
    assert rutas["dijkstra_ponderado"]["nodos"] == [1, 3, 6, 7]
    assert not rutas["dijkstra_ponderado"]["factible"]
    assert rutas["dijkstra_ponderado"]["R"] is None


def test_autonomia_muy_chica_respuesta_limpia(esc, consulta):
    c = copy.deepcopy(consulta)
    c["autonomia_m"] = 500
    rutas, res = _todas(esc, c)
    assert not any(r["factible"] for r in rutas.values())
    assert res["mas_resiliente"] is None


def test_exclusiones_que_cortan_el_grafo(esc, consulta):
    c = copy.deepcopy(consulta)
    c["restricciones"]["excluir_nodos"] = [2, 3, 4]
    rutas, _ = _todas(esc, c)
    for t in ("milp", "dijkstra_ponderado", "aco"):
        assert rutas[t]["factible"] is False
        assert rutas[t]["mensaje"]
    assert rutas["dijkstra_distancia"]["factible"] is False


def test_origen_igual_destino(esc, consulta):
    c = copy.deepcopy(consulta)
    c["destino_id"] = 1
    rutas, _ = _todas(esc, c)
    assert all(not r["factible"] for r in rutas.values())


def test_aco_nunca_mejor_que_el_optimo(esc, con_amenaza):
    prob, _ = servicio.preparar(con_amenaza, esc)
    dijkstra_distancia.resolver(prob)
    opt = milp.resolver(prob)["costo"]
    for semilla in range(10):
        r = aco.resolver(prob, semilla=semilla, config="config_mai", params={"iteraciones": 30})
        assert r["costo"] >= opt - 1e-9


def test_aco_misma_semilla_mismo_resultado(esc, con_amenaza):
    prob, _ = servicio.preparar(con_amenaza, esc)
    dijkstra_distancia.resolver(prob)
    a = aco.resolver(prob, semilla=7, params={"iteraciones": 20})
    b = aco.resolver(prob, semilla=7, params={"iteraciones": 20})
    assert a["nodos"] == b["nodos"] and a["extra"]["convergencia"] == b["extra"]["convergencia"]


def test_aco_encuentra_optimo_en_la_mayoria(esc, con_amenaza):
    prob, _ = servicio.preparar(con_amenaza, esc)
    dijkstra_distancia.resolver(prob)
    aciertos = sum(
        aco.resolver(prob, semilla=s, config="config_zhang", params={"pasos_busqueda_local": 0})["nodos"]
        == [1, 3, 6, 7] for s in range(20))
    assert aciertos >= 15


def test_geojson_continuo(esc, con_amenaza):
    rutas, _ = _todas(esc, con_amenaza)
    coords = rutas["milp"]["geojson"]["geometry"]["coordinates"]
    assert coords[0] == [-72.5, -42.5] and coords[-1] == [-72.5, -42.482]
    assert len(coords) == len(rutas["milp"]["nodos"])


def test_q0_calendario_mai(esc, con_amenaza):
    prob, _ = servicio.preparar(con_amenaza, esc)
    dijkstra_distancia.resolver(prob)
    nombre, params, comunes, _ = aco.parametros_config("config_mai")
    a = aco.ACO(prob, {**params, "iteraciones": 100, "q0_inicial": 0.9}, comunes)
    assert a.q0_iteracion(0) == pytest.approx(0.9)
    assert a.q0_iteracion(69) == pytest.approx(0.31 * 0.9)
    assert a.q0_iteracion(70) == pytest.approx(0.45)
    assert a.q0_iteracion(99) == pytest.approx(0.29 * 0.9 + 0.45)
    _, pz, cz, _ = aco.parametros_config("config_zhang")
    assert aco.ACO(prob, pz, cz).q0_iteracion(10) == 0.0
