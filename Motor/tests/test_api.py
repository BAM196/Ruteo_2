import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from conftest import JUGUETE


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setenv("MOTOR_FUENTE", "json")
    monkeypatch.setenv("MOTOR_GRAFO_JSON", str(JUGUETE))
    monkeypatch.setenv("MOTOR_PROGRAMADOR", "0")
    from motor import api

    api._CACHE.update(t=0.0, esc=None)
    return TestClient(api.app)


def test_health(cliente):
    r = cliente.get("/health").json()
    assert r["base"] == "ok" and r["n_camaras"] == 5


def test_sectores_y_bases(cliente):
    s = cliente.get("/api/sectores").json()["sectores"]
    assert len(s) == 2 and all("subtitulo" in x for x in s)
    b = cliente.get("/api/bases").json()["bases"]
    assert {x["id"] for x in b} == {1, 6, 100000}


def test_plan(cliente, con_amenaza):
    r = cliente.post("/api/plan", json=con_amenaza)
    assert r.status_code == 200
    data = r.json()
    assert [p["tecnica"] for p in data["planes"]] == ["dijkstra_distancia", "milp", "dijkstra_ponderado", "aco"]
    for p in data["planes"]:
        assert {"etiqueta", "vuelos", "R", "leyenda", "tiempo_ms", "factible"} <= set(p)
        for v in p["vuelos"]:
            assert v["geojson"]["geometry"]["type"] == "LineString"
    assert data["mas_resiliente"] != "dijkstra_distancia"


def test_fallas_y_kml(cliente, consulta):
    data = cliente.post("/api/plan", json=consulta).json()
    p = data["planes"][1]
    vuelos = [{**v, "tecnica": p["tecnica"]} for v in p["vuelos"]]
    f = cliente.post("/api/fallas", json={"vuelos": vuelos, "semilla": 1}).json()
    assert len(f["vuelos"]) == len(vuelos)
    k = cliente.post("/api/kml", json={"plan": {"tecnica": p["tecnica"], "vuelos": p["vuelos"]}})
    assert k.status_code == 200 and k.content[:2] == b"PK"


def test_validacion(cliente):
    assert cliente.post("/api/plan", json={"modo": "desconocido"}).status_code == 400
    assert cliente.post("/api/plan", json={"modo": "camaras", "camaras": []}).status_code == 400
