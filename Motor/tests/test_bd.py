import pytest

from motor import config, grafo, probabilidades, servicio
from motor.mision import sectores


@pytest.fixture(scope="module")
def conn():
    try:
        c = config.conectar()
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM bases")
            if cur.fetchone()[0] == 0:
                pytest.skip("La tabla bases está vacía.")
    except Exception as exc:
        pytest.skip(f"Sin base de datos: {exc}")
    yield c
    c.close()


def test_pgr_dijkstra_igual_a_python(conn):
    from motor.rutas.comun import Consulta, Contexto, ProblemaSector

    esc = grafo.desde_bd(conn)
    s = max((x for x in sectores.leer_sectores(esc) if x["base"]), key=lambda x: x["n_camaras"])
    ctx = Contexto(esc, probabilidades.calcular(esc), Consulta())
    a = ProblemaSector(ctx, esc.bases[s["base"]["id"]], s["camaras"])
    b = ProblemaSector(ctx, esc.bases[s["base"]["id"]], s["camaras"])
    ta = a.calcular_tramos("distancia", conn)
    tb = b.calcular_tramos("distancia", None)
    assert a.motor_tramos.startswith("pgr_dijkstra")
    assert set(ta) == set(tb)
    for k in ta:
        assert ta[k].distancia == pytest.approx(tb[k].distancia)


def test_plan_desde_la_base(conn):
    esc = grafo.desde_bd(conn)
    res = servicio.planificar({"modo": "sector"}, esc, n_mc=500)
    assert res["planes"][0]["vuelos"]


def test_tablas_y_vistas_de_probabilidad(conn):
    esc = grafo.desde_bd(conn)
    probabilidades.cargar_bd(probabilidades.calcular(esc, overrides={"aristas": {"27": 0.8}}), conn)
    with conn.cursor() as cur:
        cur.execute("SELECT p_total FROM prob_fallo_arista_total WHERE arista_id = 27")
        assert cur.fetchone()[0] >= 0.8 - 1e-9
    probabilidades.cargar_bd(probabilidades.calcular(esc), conn)
