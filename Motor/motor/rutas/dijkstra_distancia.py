import time

from .comun import Problema, dijkstra

TECNICA, ETIQUETA = "dijkstra_distancia", "pgr_dijkstra (distancia)"

SQL = """
SELECT path_seq, node, edge, agg_cost
FROM pgr_dijkstra(
    'SELECT id, source, target, distancia_m AS cost FROM aristas',
    %(origen)s, %(destino)s, directed := false)
ORDER BY path_seq
"""


def _con_pgrouting(prob: Problema, conn):
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(SQL, {"origen": prob.s, "destino": prob.t})
        filas = cur.fetchall()
    ms = (time.perf_counter() - t0) * 1000
    if not filas:
        return None, ms
    nodos = [int(f[1]) for f in filas]
    aristas = [int(f[2]) for f in filas if f[2] > 0]
    return (nodos, aristas, float(filas[-1][3])), ms


def _en_python(prob: Problema):
    t0 = time.perf_counter()
    r = dijkstra(prob.adyacencia("distancia", permitidos=False), prob.s, prob.t)
    return r, (time.perf_counter() - t0) * 1000


def resolver(prob: Problema, conn=None) -> dict:
    error = prob.validar_extremos()
    if error:
        return prob.resultado(TECNICA, ETIQUETA, [], [], 0.0, mensaje=error)
    if conn is not None:
        r, ms = _con_pgrouting(prob, conn)
        motor = "pgr_dijkstra (PostGIS/pgRouting)"
    else:
        r, ms = _en_python(prob)
        motor = "Dijkstra en Python (modo sin base, mismas reglas que pgr_dijkstra)"
    if r is None:
        return prob.resultado(TECNICA, ETIQUETA, [], [], ms,
                              extra={"motor": motor}, mensaje="No hay camino entre esas cámaras.")
    nodos, aristas, dist = r
    if prob.d_ref is None:
        prob.d_ref = dist
    return prob.resultado(TECNICA, ETIQUETA, nodos, aristas, ms,
                          extra={"motor": motor, "sql": SQL.strip() if conn else None})
