from datetime import datetime

import pytest

from motor import grafo, probabilidades


def test_sin_amenazas_todo_es_cero(esc):
    doc = probabilidades.calcular(esc)
    assert all(n["p_total"] == 0 for n in doc["nodos"])
    assert all(a["p_total"] == 0 for a in doc["aristas"])


def test_override_cambia_probabilidad(esc):
    doc = probabilidades.calcular(esc, overrides={"aristas": {"2": 0.9}, "nodos": {"6": 0.3}})
    q, p = probabilidades.mapas(doc)
    assert p[2] == pytest.approx(0.9)
    assert q[6] == pytest.approx(0.3)
    assert sum(1 for v in p.values() if v > 0) == 1


def test_firms_decae_con_la_distancia(esc):
    esc.focos = [{"id": 1, "lon": -72.5, "lat": -42.4865, "confidence": "h"}]
    doc = probabilidades.calcular(esc)
    q, p = probabilidades.mapas(doc)
    assert p[2] == pytest.approx(0.9, abs=0.02)
    assert 0 < q[2] < p[2]
    assert q[4] == 0
    assert 0 < p[6] < 0.05


def test_firms_respeta_radio(esc):
    esc.focos = [{"id": 1, "lon": -72.40, "lat": -42.40, "confidence": "h"}]
    q, p = probabilidades.mapas(probabilidades.calcular(esc))
    assert max(p.values()) == 0 and max(q.values()) == 0


def test_meteo_rampa_y_temperatura(esc):
    esc.meteo = {
        1: grafo.lectura_meteo(10, 80, 5, 10, 0, "m/s"),
        7: grafo.lectura_meteo(45, 20, 1, 1, 0, "m/s"),
    }
    doc = probabilidades.calcular(esc)
    q, p = probabilidades.mapas(doc)
    assert q[1] == pytest.approx(0.5)
    assert q[7] == pytest.approx(0.999999)
    assert p[1] == pytest.approx(0.5)


def test_meteo_convierte_kmh():
    lec = grafo.lectura_meteo(10, 50, 36, 43.2, 0, "km/h")
    assert lec["viento_ms"] == pytest.approx(10)
    assert lec["rafaga_ms"] == pytest.approx(12)


def test_ebird_recencia(esc):
    hoy = datetime(2026, 10, 20)
    esc.aves = [
        {"id": "a", "lon": -72.5, "lat": -42.5, "cantidad": 20, "fecha_obs": hoy},
        {"id": "b", "lon": -72.5, "lat": -42.482, "cantidad": 20, "fecha_obs": datetime(2026, 10, 13)},
    ]
    q, _ = probabilidades.mapas(probabilidades.calcular(esc))
    assert q[1] == pytest.approx(0.5)
    assert q[7] == pytest.approx(0.25)


def test_combinacion_independiente():
    assert probabilidades.combinar([0.5, 0.5]) == pytest.approx(0.75)
