import time

from psycopg2.extras import execute_values

from .comun import Problema, dijkstra

TECNICA, ETIQUETA = "dijkstra_ponderado", "pgr_dijkstra (ponderado)"

SQL = """
SELECT path_seq, node, edge, agg_cost
FROM pgr_dijkstra(
    'SELECT a.id, a.source, a.target, c.cost, c.reverse_cost
       FROM aristas a JOIN costos_tecnica3 c ON c.id = a.id',
    %(origen)s, %(destino)s, directed := true)
ORDER BY path_seq
"""


def costos_por_arista(prob: Problema) -> list[tuple]:
    filas = []
    for aid, a in prob.esc.aristas.items():
        if aid in prob.aristas_excluidas:
            filas.append((aid, -1.0, -1.0))
            continue
        u, v = a["source"], a["target"]
        filas.append((aid, prob.costo_arco(u, v, aid), prob.costo_arco(v, u, aid)))
    return filas


def _con_pgrouting(prob: Problema, conn):
    filas = costos_por_arista(prob)
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute("""CREATE TEMP TABLE IF NOT EXISTS costos_tecnica3
                       (id INTEGER PRIMARY KEY, cost DOUBLE PRECISION, reverse_cost DOUBLE PRECISION)""")
        cur.execute("TRUNCATE costos_tecnica3")
        execute_values(cur, "INSERT INTO costos_tecnica3 (id, cost, reverse_cost) VALUES %s", filas)
        cur.execute(SQL, {"origen": prob.s, "destino": prob.t})
        res = cur.fetchall()
    conn.rollback()
    ms = (time.perf_counter() - t0) * 1000
    if not res:
        return None, ms
    return ([int(f[1]) for f in res], [int(f[2]) for f in res if f[2] > 0], float(res[-1][3])), ms


def _en_python(prob: Problema):
    t0 = time.perf_counter()
    r = dijkstra(prob.adyacencia("combinado"), prob.s, prob.t)
    return r, (time.perf_counter() - t0) * 1000


def resolver(prob: Problema, conn=None) -> dict:
    error = prob.validar_extremos()
    if error or prob.d_ref is None:
        return prob.resultado(TECNICA, ETIQUETA, [], [], 0.0,
                              mensaje=error or "Sin distancia de referencia (no hay ruta por distancia).")
    if conn is not None:
        r, ms = _con_pgrouting(prob, conn)
        motor = "pgr_dijkstra (PostGIS/pgRouting)"
    else:
        r, ms = _en_python(prob)
        motor = "Dijkstra en Python (modo sin base, mismas reglas que pgr_dijkstra)"
    if r is None:
        return prob.resultado(TECNICA, ETIQUETA, [], [], ms, extra={"motor": motor},
                              mensaje="No hay camino que respete las exclusiones.")
    nodos, aristas, agg = r
    return prob.resultado(TECNICA, ETIQUETA, nodos, aristas, ms,
                          extra={"motor": motor, "agg_cost": agg,
                                 "nota": "pgr_dijkstra no impone D_max: se revisa después",
                                 "sql": SQL.strip() if conn else None})
