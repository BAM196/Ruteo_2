import math
from datetime import datetime

import pytest

from motor import grafo, probabilidades as pr
from motor.config import amenazas_cfg


@pytest.fixture
def cfg():
    return amenazas_cfg()["amenazas"]


def test_firms_decae_linealmente_desde_p_foco_real(cfg):
    foco = {"id": 1, "confidence": "n"}
    p0 = cfg["firms"]["p_real_por_confianza"]["valor"]["n"]
    centro = grafo.xy(-72.5, -42.5)
    p, _ = pr.modelo_firms(centro, False, [(foco, centro)], cfg["firms"])
    assert p == pytest.approx(p0)
    lejos = centro + [500, 0]
    p, _ = pr.modelo_firms(lejos, False, [(foco, centro)], cfg["firms"])
    assert p == pytest.approx(p0 * 0.5)
    p, _ = pr.modelo_firms(centro + [1000, 0], False, [(foco, centro)], cfg["firms"])
    assert p == 0.0


def test_confianza_baja_vale_menos(cfg):
    centro = grafo.xy(-72.5, -42.5)
    alta, _ = pr.modelo_firms(centro, False, [({"id": 1, "confidence": "h"}, centro)], cfg["firms"])
    baja, _ = pr.modelo_firms(centro, False, [({"id": 1, "confidence": "l"}, centro)], cfg["firms"])
    assert baja < alta


def test_viento_es_excedencia_de_12_ms_a_80_m(cfg):
    met = cfg["meteo"]
    alpha, sigma = met["alpha_perfil"]["valor"], met["sigma_rafaga_ms"]["valor"]
    g10 = 12 / 8 ** alpha
    p, det = pr.modelo_meteo_nodo({"rafaga_ms": g10, "temperatura": 10}, met)
    assert det["rafaga_80m_ms"] == pytest.approx(12, abs=0.01)
    assert det["p_viento"] == pytest.approx(0.5, abs=1e-6)
    p, det = pr.modelo_meteo_nodo({"rafaga_ms": g10 - sigma / 8 ** alpha, "temperatura": 10}, met)
    assert det["p_viento"] == pytest.approx(1 - pr.phi(1.0), abs=1e-4)


def test_lluvia_usa_probabilidad_o_si_llovio(cfg):
    met = cfg["meteo"]
    _, det = pr.modelo_meteo_nodo({"rafaga_ms": 0, "temperatura": 10, "prob_lluvia": 40}, met)
    assert det["p_lluvia"] == pytest.approx(0.4)
    _, det = pr.modelo_meteo_nodo({"rafaga_ms": 0, "temperatura": 10, "precipitacion_mm": 0.3}, met)
    assert det["p_lluvia"] == 1.0
    _, det = pr.modelo_meteo_nodo({"rafaga_ms": 0, "temperatura": 10, "precipitacion_mm": 0.0}, met)
    assert det["p_lluvia"] == 0.0


def test_temperatura_fuera_de_rango(cfg):
    met = cfg["meteo"]
    _, det = pr.modelo_meteo_nodo({"rafaga_ms": 0, "temperatura": -15}, met)
    assert det["p_temperatura"] > 0.99
    _, det = pr.modelo_meteo_nodo({"rafaga_ms": 0, "temperatura": 12}, met)
    assert det["p_temperatura"] < 1e-6


def test_aves_al_menos_una_de_n(cfg):
    eb = cfg["ebird"]
    R = pr.radio_aves(eb)
    centro = grafo.xy(-72.5, -42.5)
    fecha = datetime(2026, 1, 10)
    ave = {"id": "a", "cantidad": 3, "fecha_obs": fecha}
    p, det = pr.modelo_ebird(centro + [R / 2, 0], False, [(ave, centro)], eb, fecha)
    p_i = eb["p0"]["valor"] * 0.5
    assert p == pytest.approx(1 - (1 - p_i) ** 3)
    assert R == pytest.approx(eb["distancia_precaucion_m"]["valor"] + eb["r_mov_m"]["valor"])


def test_combinar_independientes():
    assert pr.combinar([0.5, 0.5]) == pytest.approx(0.75)
    assert pr.combinar([0.2, 0.0, 0.3]) >= 0.3


def test_overrides_y_cota(esc):
    doc = pr.calcular(esc, overrides={"aristas": {"3": 1.0}, "nodos": {"2": 0.4}})
    a3 = next(a for a in doc["aristas"] if a["id"] == 3)
    assert a3["p_total"] == pytest.approx(0.999999)
    n2 = next(n for n in doc["nodos"] if n["id"] == 2)
    assert n2["por_amenaza"]["escenario"] == pytest.approx(0.4)
    assert math.isfinite(-math.log(1 - a3["p_total"]))
