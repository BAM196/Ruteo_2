import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from conftest import JUGUETE


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("MOTOR_FUENTE", "json")
    monkeypatch.setenv("MOTOR_GRAFO_JSON", str(JUGUETE))
    from motor.api import app

    return TestClient(app)


def test_health(cliente):
    r = cliente.get("/health").json()
    assert r["base"] == "ok" and r["n_nodos"] == 7


def test_rutas(cliente):
    cuerpo = {"origen_id": 1, "destino_id": 7, "autonomia_m": 8000, "theta": 0.5,
              "restricciones": {"solo_bosque": False, "excluir_nodos": []},
              "overrides_prob": {"aristas": {"2": 0.9}}}
    r = cliente.post("/api/rutas", json=cuerpo)
    assert r.status_code == 200
    data = r.json()
    assert [x["tecnica"] for x in data["rutas"]] == ["dijkstra_distancia", "milp", "dijkstra_ponderado", "aco"]
    for ruta in data["rutas"]:
        assert {"etiqueta", "geojson", "distancia_m", "p_supervivencia", "riesgo_log",
                "tiempo_ms", "factible", "R", "leyenda"} <= set(ruta)
    assert data["mas_resiliente"] != "dijkstra_distancia"


def test_validacion(cliente):
    assert cliente.post("/api/rutas", json={"origen_id": 1}).status_code == 422
    assert cliente.post("/api/rutas", json={"origen_id": 1, "destino_id": 7, "theta": 2}).status_code == 422


def test_probabilidades(cliente):
    r = cliente.post("/api/probabilidades", json={"overrides_prob": {"nodos": {"3": 0.4}}}).json()
    assert next(n for n in r["nodos"] if n["id"] == 3)["p_total"] == pytest.approx(0.4)
    assert cliente.get("/api/probabilidades").status_code == 200
