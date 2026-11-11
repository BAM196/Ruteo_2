import pytest

from motor import config, grafo, probabilidades, servicio
from motor.rutas import dijkstra_distancia, dijkstra_ponderado


@pytest.fixture(scope="module")
def conn():
    try:
        c = config.conectar()
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM aristas")
            if cur.fetchone()[0] == 0:
                pytest.skip("La tabla aristas está vacía.")
    except Exception as exc:
        pytest.skip(f"Sin base de datos: {exc}")
    yield c
    c.close()


def test_distancia_m_es_costo_km_por_mil(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM aristas WHERE abs(distancia_m - costo_km * 1000) > 0.5")
        assert cur.fetchone()[0] == 0


def test_pgr_dijkstra_igual_a_python(conn):
    esc = grafo.desde_bd(conn)
    for s, t in [(16, 22), (1, 7), (18, 24)]:
        c = {"origen_id": s, "destino_id": t, "theta": 0.5,
             "overrides_prob": {"aristas": {"27": 0.8, "29": 0.5}}}
        p1, _ = servicio.preparar(c, esc)
        p2, _ = servicio.preparar(c, esc)
        a = dijkstra_distancia.resolver(p1, conn)
        b = dijkstra_distancia.resolver(p2, None)
        assert a["distancia_m"] == pytest.approx(b["distancia_m"])
        a3 = dijkstra_ponderado.resolver(p1, conn)
        b3 = dijkstra_ponderado.resolver(p2, None)
        assert a3["costo"] == pytest.approx(b3["costo"], rel=1e-9)


def test_tablas_y_vistas_de_probabilidad(conn):
    esc = grafo.desde_bd(conn)
    doc = probabilidades.calcular(esc, overrides={"aristas": {"27": 0.8}})
    probabilidades.cargar_bd(doc, conn)
    with conn.cursor() as cur:
        cur.execute("SELECT p_total FROM prob_fallo_arista_total WHERE arista_id = 27")
        assert cur.fetchone()[0] == pytest.approx(0.8)
        cur.execute("SELECT count(*) FROM prob_fallo_nodo_total")
        assert cur.fetchone()[0] == len(esc.nodos)
    probabilidades.cargar_bd(probabilidades.calcular(esc), conn)
