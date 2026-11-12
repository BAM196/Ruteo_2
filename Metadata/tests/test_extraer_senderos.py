import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Metadata.extraer_senderos import (
    cruzar_senderos,
    distancia_entre_lineas,
    distancia_segmento_a_segmento,
    segmentos_se_tocan,
)


def test_segmentos_que_se_cruzan_tocan():
    a = np.array([0.0, 0.0])
    b = np.array([10.0, 0.0])
    c = np.array([5.0, -5.0])
    d = np.array([5.0, 5.0])

    assert segmentos_se_tocan(a, b, c, d)
    assert distancia_segmento_a_segmento(a, b, c, d) == 0.0


def test_segmentos_que_comparten_extremo_se_tocan():
    a = np.array([0.0, 0.0])
    b = np.array([10.0, 0.0])
    c = np.array([10.0, 0.0])
    d = np.array([10.0, 5.0])

    assert segmentos_se_tocan(a, b, c, d)


def test_distancia_entre_lineas_usa_el_segmento_completo():
    linea_a = [np.array([0.0, 0.0]), np.array([1000.0, 0.0])]
    linea_b = [np.array([0.0, 40.0]), np.array([1000.0, 40.0])]

    assert distancia_entre_lineas(linea_a, linea_b) == 40.0


def test_cruce_lejos_del_punto_medio_marca_arista():
    nodos = [
        {"id": 1, "lon": -72.5, "lat": -42.5},
        {"id": 2, "lon": -72.48, "lat": -42.5},
    ]
    aristas = [{
        "id": 1,
        "source": 1,
        "target": 2,
        "coordenadas": [[-72.5, -42.5], [-72.48, -42.5]],
    }]
    sendero = {
        "id": 1,
        "tipo": "trazado",
        "coordenadas": [[-72.499, -42.51, 0], [-72.499, -42.49, 0]],
    }

    cruzar_senderos([sendero], nodos, aristas)

    assert sendero["aristas_cercanas"] == [
        {"id": 1, "distancia_m": 0.0, "buffer_privacidad": True}
    ]
