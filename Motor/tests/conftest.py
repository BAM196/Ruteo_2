import copy
import sys
from pathlib import Path

import pytest

MOTOR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOTOR))

from motor import grafo

JUGUETE = MOTOR / "tests" / "grafo_juguete.json"


@pytest.fixture
def esc():
    return grafo.desde_juguete(JUGUETE)


@pytest.fixture
def consulta():
    return {"origen_id": 1, "destino_id": 7, "theta": 0.5, "autonomia_m": 10_000,
            "restricciones": {"solo_bosque": False, "excluir_nodos": []}, "overrides_prob": {}}


@pytest.fixture
def con_amenaza(consulta):
    c = copy.deepcopy(consulta)
    c["overrides_prob"] = {"aristas": {"2": 0.9}}
    return c
