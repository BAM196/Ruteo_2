import itertools

import numpy as np
import pytest

from motor import grafo
from motor.mision import bases, bateria, prioridad, sectores


def test_reserva_y_bateria_util(m):
    assert bateria.reserva_s(m) == pytest.approx(1500 / (15 - 12) + 60)
    assert bateria.tiempo_util_s(m) == pytest.approx(2280 - 560)
    assert bateria.cabe([100, 100], 2, m)
    assert not bateria.cabe([100, 100], 3, m)
    assert bateria.tiempo_tramo_s(900, 60, m) == pytest.approx(100 + 10)


def test_particion_es_exacta_y_sin_repetidos(esc, m):
    grupos = sectores.particion(esc, esc.camaras(), m)
    todas = [c for g in grupos for c in g["camaras"]]
    assert sorted(todas) == esc.camaras()
    assert len(grupos) == 2
    assert {tuple(g["camaras"]) for g in grupos} == {(1, 2, 3, 4), (6,)}


def test_diametro_de_los_sectores(esc, m):
    for g in sectores.particion(esc, esc.camaras(), m):
        pts = [grafo.xy(esc.nodos[c]["lon"], esc.nodos[c]["lat"]) for c in g["camaras"]]
        d = max([float(np.linalg.norm(a - b)) for a, b in itertools.combinations(pts, 2)] + [0.0])
        assert d <= m["diametro_max"] + 1e-6
        assert g["diametro_m"] == pytest.approx(d, abs=0.2)


def test_base_minimiza_suma_de_distancias(esc):
    b, _ = bases.elegir(esc, [1, 2])
    assert b["id"] == 1
    b, _ = bases.elegir(esc, [3, 4])
    assert b["id"] == 1
    b, motivo = bases.elegir(esc, [1, 6])
    assert b is None and motivo


def test_prioridad_y_subtitulo(esc, m):
    s = sectores.armar_sectores(esc, m=m)
    grande = next(x for x in s if x["n_camaras"] == 4)
    assert grande["presion_exoticas"] == pytest.approx(0.25)
    assert grande["valor_conservacion"] == pytest.approx(3 * 2 / 4 + 2 * 1 / 4 + 1 * 1 / 4)
    assert max(x["prioridad"] for x in s) <= 100
    assert "Prioridad" in grande["subtitulo"] and "Objetivo" in grande["subtitulo"]


def test_kendall():
    assert prioridad.kendall_tau([1, 2, 3], [1, 2, 3]) == 1
    assert prioridad.kendall_tau([1, 2, 3], [3, 2, 1]) == -1


class DEMSintetico:
    def __init__(self, cerro_x=500.0, alto=200.0):
        self.cerro_x, self.alto = cerro_x, alto

    def altura(self, x, y):
        x = np.asarray(x, dtype=float)
        return np.where(np.abs(x - self.cerro_x) < 40, self.alto, 0.0)


P = {"paso": 30.0, "claro": 60.0, "altura": 80.0, "techo": 120.0, "c_min": 24.5}


def test_linea_de_vista_cortada_por_un_cerro():
    terreno = pytest.importorskip("terreno")
    dem = DEMSintetico()
    ojo = (0.0, 0.0, 1.7)
    objetivos = np.array([[1000.0, 0.0, 80.0], [300.0, 0.0, 80.0]])
    vis = terreno.linea_de_vista(dem, ojo, objetivos, P)
    assert not vis[0] and vis[1]


def test_perfil_densifica_sobre_el_cerro_y_bloquea_acantilados():
    terreno = pytest.importorskip("terreno")
    suave = DEMSintetico(alto=60.0)
    r = terreno.perfil(suave, np.array([[0.0, 0.0], [1000.0, 0.0]]), P)
    assert not r["bloqueada"] and r["densificada"]
    assert r["despeje_min_m"] >= P["c_min"] - 1e-6
    assert r["altura_max_sobre_superficie_m"] <= P["techo"] + 1e-6
    acantilado = DEMSintetico(alto=300.0)
    r = terreno.perfil(acantilado, np.array([[0.0, 0.0], [1000.0, 0.0]]), P)
    assert r["bloqueada"]
