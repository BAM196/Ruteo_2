import heapq
import math

SQL = """
SELECT start_vid, end_vid, path_seq, node, edge, agg_cost
FROM pgr_dijkstra(
    'SELECT id, source, target, cost, reverse_cost FROM costos_tramos',
    %(origenes)s::bigint[], %(destinos)s::bigint[], directed := true)
ORDER BY start_vid, end_vid, path_seq
"""


def _desde(adj: dict, s):
    dist, prev = {s: 0.0}, {}
    heap, hecho = [(0.0, s)], set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in hecho:
            continue
        hecho.add(u)
        for v, aid, c in adj.get(u, ()):
            nd = d + c
            if nd < dist.get(v, math.inf) - 1e-12:
                dist[v], prev[v] = nd, (u, aid)
                heapq.heappush(heap, (nd, v))
    return dist, prev


def _camino(prev, s, t):
    nodos, aristas, v = [t], [], t
    while v != s:
        u, aid = prev[v]
        nodos.append(u)
        aristas.append(aid)
        v = u
    return nodos[::-1], aristas[::-1]


def en_python(adj: dict, pts: list) -> dict:
    salida = {}
    for s in pts:
        dist, prev = _desde(adj, s)
        for t in pts:
            if t != s and t in dist:
                nodos, aristas = _camino(prev, s, t)
                salida[(s, t)] = (nodos, aristas)
    return salida


def con_pgrouting(prob, adj: dict, pts: list, conn) -> dict:
    from psycopg2.extras import execute_values

    costo = {}
    for u, lista in adj.items():
        for v, aid, c in lista:
            costo[(aid, u)] = c
    filas = []
    for aid in {aid for (aid, _u) in costo}:
        a = prob.esc.aristas[aid]
        s, t = a["source"], a["target"]
        filas.append((aid, s, t, costo.get((aid, s), -1.0), costo.get((aid, t), -1.0)))
    salida = {}
    if not filas:
        return salida
    with conn.cursor() as cur:
        cur.execute("""CREATE TEMP TABLE IF NOT EXISTS costos_tramos
                       (id BIGINT PRIMARY KEY, source BIGINT, target BIGINT,
                        cost DOUBLE PRECISION, reverse_cost DOUBLE PRECISION)""")
        cur.execute("TRUNCATE costos_tramos")
        execute_values(cur, "INSERT INTO costos_tramos (id, source, target, cost, reverse_cost) VALUES %s", filas)
        cur.execute(SQL, {"origenes": pts, "destinos": pts})
        res = cur.fetchall()
    conn.rollback()
    actual = {}
    for s, t, seq, node, edge, _agg in res:
        actual.setdefault((int(s), int(t)), []).append((int(node), int(edge)))
    for (s, t), pasos in actual.items():
        nodos = [n for n, _ in pasos]
        aristas = [e for _, e in pasos if e > 0]
        salida[(s, t)] = (nodos, aristas)
    return salida


def caminos(prob, adj: dict, pts: list, tipo: str, conn=None):
    if conn is not None:
        try:
            return con_pgrouting(prob, adj, pts, conn), "pgr_dijkstra (PostGIS/pgRouting)"
        except Exception:
            conn.rollback()
    return en_python(adj, pts), "Dijkstra en Python (mismas reglas que pgr_dijkstra)"
