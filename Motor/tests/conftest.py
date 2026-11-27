import copy
import sys
from pathlib import Path

import pytest

MOTOR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOTOR))
sys.path.insert(0, str(MOTOR.parent / "Infraestructura"))

from motor import grafo
from motor.config import parametros_mision

JUGUETE = MOTOR / "tests" / "grafo_juguete.json"


@pytest.fixture
def esc():
    return grafo.desde_juguete(JUGUETE)


@pytest.fixture
def m():
    return parametros_mision()


@pytest.fixture
def consulta():
    return {"modo": "camaras", "camaras": [1, 2, 3, 4], "base_id": 1, "theta": 0.5,
            "restricciones": {}, "overrides_prob": {}}


@pytest.fixture
def con_amenaza(consulta):
    c = copy.deepcopy(consulta)
    c["overrides_prob"] = {"aristas": {"4": 0.8}}
    return c
