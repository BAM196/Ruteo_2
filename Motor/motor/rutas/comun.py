import heapq
import math
from dataclasses import dataclass, field

EPS = 1e-6
BOSQUE = 10


@dataclass
class Consulta:
    origen_id: int
    destino_id: int
    theta: float = 0.5
    autonomia_m: float | None = None
    solo_bosque: bool = False
    evitar_senderos: bool = False
    evitar_clima: bool = False
    evitar_aves: bool = False
    excluir_nodos: list = field(default_factory=list)
    overrides_prob: dict = field(default_factory=dict)
    r_min: float | None = None
    semilla: int = 0
    aco_config: str | None = None

    @classmethod
    def desde_dict(cls, d: dict, d_max_defecto: float) -> "Consulta":
        r = d.get("restricciones") or {}
        return cls(
            origen_id=int(d["origen_id"]),
            destino_id=int(d["destino_id"]),
            theta=float(d.get("theta", 0.5)),
            autonomia_m=float(d.get("autonomia_m") or d_max_defecto),
            solo_bosque=bool(r.get("solo_bosque", False)),
            evitar_senderos=bool(r.get("evitar_senderos", False)),
            evitar_clima=bool(r.get("evitar_clima", False)),
            evitar_aves=bool(r.get("evitar_aves", False)),
            excluir_nodos=[int(x) for x in r.get("excluir_nodos", [])],
            overrides_prob=d.get("overrides_prob") or {},
            r_min=d.get("r_min"),
            semilla=int(d.get("semilla", 0)),
            aco_config=d.get("aco_config"),
        )


class Problema:
    def __init__(self, esc, q_nodo: dict, p_arista: dict, consulta: Consulta,
                 cota: float = 0.999999, amenaza_nodo: dict | None = None,
                 amenaza_arista: dict | None = None):
        self.esc = esc
        self.c = consulta
        self.s, self.t = consulta.origen_id, consulta.destino_id
        self.theta = min(max(consulta.theta, 0.0), 1.0)
        self.d_max = consulta.autonomia_m
        self.q = {v: q_nodo.get(v, 0.0) for v in esc.nodos}
        self.p = {a: p_arista.get(a, 0.0) for a in esc.aristas}
        self.u = {v: -math.log(1 - q) for v, q in self.q.items()}
        self.w = {a: -math.log(1 - p) for a, p in self.p.items()}
        self.cota = cota
        self.d_ref = None

        amenaza_nodo = amenaza_nodo or {}
        amenaza_arista = amenaza_arista or {}
        evitar = [k for k, activo in (("meteo", consulta.evitar_clima), ("ebird", consulta.evitar_aves)) if activo]

        def con_amenaza_evitada(por_amenaza: dict) -> bool:
            return any(por_amenaza.get(k, 0.0) > 0 for k in evitar)

        self.excl_usuario = set(consulta.excluir_nodos)
        excl = set(self.excl_usuario)
        motivos = {v: "excluido por el usuario" for v in self.excl_usuario}
        for v, n in esc.nodos.items():
            if v in (self.s, self.t):
                continue
            if consulta.solo_bosque and n.get("landcover_code") != BOSQUE:
                excl.add(v)
                motivos.setdefault(v, "no es bosque (solo_bosque)")
            if con_amenaza_evitada(amenaza_nodo.get(v, {})):
                excl.add(v)
                motivos.setdefault(v, "riesgo por clima o aves (evitar)")
            if self.q[v] >= cota:
                excl.add(v)
                motivos.setdefault(v, "probabilidad de falla = 1")
        self.nodos_excluidos = excl
        self.motivos_nodo = motivos

        self.aristas_excluidas = set()
        for aid, a in esc.aristas.items():
            if (a["source"] in excl or a["target"] in excl or not a.get("viable", True)
                    or (consulta.evitar_senderos and a.get("buffer_privacidad", False))
                    or con_amenaza_evitada(amenaza_arista.get(aid, {}))
                    or self.p[aid] >= cota or (self.d_max and a["distancia_m"] > self.d_max)):
                self.aristas_excluidas.add(aid)

    def arcos(self, permitidos=True):
        for aid, a in self.esc.aristas.items():
            if permitidos and aid in self.aristas_excluidas:
                continue
            yield a["source"], a["target"], aid
            yield a["target"], a["source"], aid

    def costo_arco(self, u, v, aid) -> float:
        d = self.esc.aristas[aid]["distancia_m"]
        return (1 - self.theta + EPS) * d / self.d_ref + self.theta * (self.w[aid] + self.u[v])

    def adyacencia(self, costo="combinado", permitidos=True):
        adj = {v: [] for v in self.esc.nodos}
        for u, v, aid in self.arcos(permitidos):
            c = self.esc.aristas[aid]["distancia_m"] if costo == "distancia" else self.costo_arco(u, v, aid)
            adj[u].append((v, aid, c))
        return adj

    def evaluar(self, nodos: list, aristas: list) -> dict:
        dist = sum(self.esc.aristas[a]["distancia_m"] for a in aristas)
        riesgo = sum(self.u[v] for v in nodos) + sum(self.w[a] for a in aristas)
        costo = self.theta * self.u[nodos[0]] + sum(
            self.costo_arco(nodos[i], nodos[i + 1], a) for i, a in enumerate(aristas))
        usa_excluidos = [v for v in nodos if v in self.nodos_excluidos]
        aristas_excl = [a for a in aristas if a in self.aristas_excluidas]
        motivos = []
        if self.d_max and dist > self.d_max + 1e-6:
            motivos.append(f"supera la autonomía ({dist:.0f} m > {self.d_max:.0f} m)")
        if usa_excluidos:
            motivos.append(f"pasa por nodos excluidos {usa_excluidos}")
        elif aristas_excl:
            motivos.append(f"usa aristas excluidas {aristas_excl}")
        if self.c.r_min and math.exp(-riesgo) < self.c.r_min:
            motivos.append(f"R menor que r_min = {self.c.r_min}")
        return {
            "distancia_m": round(dist, 1),
            "riesgo_log": riesgo,
            "p_supervivencia": math.exp(-riesgo),
            "costo": costo,
            "factible": not motivos,
            "mensaje": "; ".join(motivos) if motivos else "ok",
        }

    def validar_extremos(self) -> str | None:
        for v in (self.s, self.t):
            if v not in self.esc.nodos:
                return f"La cámara {v} no existe."
        if self.s == self.t:
            return "El origen y el destino son la misma cámara."
        if self.s in self.excl_usuario or self.t in self.excl_usuario:
            return "El origen o el destino está en la lista de nodos excluidos."
        return None

    def geojson(self, nodos: list, aristas: list, props: dict | None = None) -> dict:
        coords = []
        for i, aid in enumerate(aristas):
            seg = [list(c) for c in self.esc.aristas[aid]["coords"]]
            u = self.esc.nodos[nodos[i]]
            ini, fin = seg[0], seg[-1]
            if (ini[0] - u["lon"]) ** 2 + (ini[1] - u["lat"]) ** 2 > (fin[0] - u["lon"]) ** 2 + (fin[1] - u["lat"]) ** 2:
                seg.reverse()
            coords.extend(seg if not coords else seg[1:])
        return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                "properties": props or {}}

    def resultado(self, tecnica, etiqueta, nodos, aristas, tiempo_ms, extra=None,
                  mensaje=None) -> dict:
        base = {"tecnica": tecnica, "etiqueta": etiqueta, "tiempo_ms": round(tiempo_ms, 2),
                "parametros": self.parametros(), "extra": extra or {}}
        if not nodos:
            return {**base, "nodos": [], "aristas": [], "geojson": None, "distancia_m": None,
                    "riesgo_log": None, "p_supervivencia": None, "costo": None,
                    "factible": False, "mensaje": mensaje or "No se encontró ruta."}
        ev = self.evaluar(nodos, aristas)
        if mensaje and ev["factible"]:
            ev["mensaje"] = mensaje
        elif mensaje:
            ev["mensaje"] = f"{mensaje}; {ev['mensaje']}"
        return {**base, "nodos": nodos, "aristas": aristas,
                "geojson": self.geojson(nodos, aristas, {"tecnica": tecnica, "etiqueta": etiqueta}),
                **ev}

    def parametros(self) -> dict:
        return {"origen": self.s, "destino": self.t, "theta": self.theta, "d_max_m": self.d_max,
                "d_ref_m": self.d_ref, "solo_bosque": self.c.solo_bosque,
                "evitar_senderos": self.c.evitar_senderos,
                "evitar_clima": self.c.evitar_clima, "evitar_aves": self.c.evitar_aves,
                "excluir_nodos": sorted(self.excl_usuario), "r_min": self.c.r_min,
                "nodos_excluidos_total": sorted(self.nodos_excluidos)}


def dijkstra(adj: dict, s, t, prohibidos=frozenset()):
    dist, prev = {s: 0.0}, {}
    heap = [(0.0, s)]
    hecho = set()
    while heap:
        d, u = heapq.heappop(heap)
        if u in hecho:
            continue
        hecho.add(u)
        if u == t:
            break
        for v, aid, c in adj.get(u, ()):
            if v in prohibidos or v in hecho:
                continue
            nd = d + c
            if nd < dist.get(v, math.inf) - 1e-12:
                dist[v], prev[v] = nd, (u, aid)
                heapq.heappush(heap, (nd, v))
    if t not in hecho:
        return None
    nodos, aristas, v = [t], [], t
    while v != s:
        u, aid = prev[v]
        nodos.append(u)
        aristas.append(aid)
        v = u
    return nodos[::-1], aristas[::-1], dist[t]


def distancias_desde(adj_inverso: dict, t) -> dict:
    dist = {t: 0.0}
    heap = [(0.0, t)]
    hecho = set()
    while heap:
        d, v = heapq.heappop(heap)
        if v in hecho:
            continue
        hecho.add(v)
        for u, _aid, c in adj_inverso.get(v, ()):
            nd = d + c
            if nd < dist.get(u, math.inf):
                dist[u] = nd
                heapq.heappush(heap, (nd, u))
    return dist
