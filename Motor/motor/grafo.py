import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from pyproj import Transformer

from .config import RAIZ, conectar

CRS_METRICO = "EPSG:32718"
_TR = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
BOSQUE = 10


@dataclass
class Escenario:
    nodos: dict
    aristas: dict
    bases: dict = field(default_factory=dict)
    especies: dict = field(default_factory=dict)
    focos: list = field(default_factory=list)
    aves: list = field(default_factory=list)
    meteo: dict = field(default_factory=dict)
    fuente: str = "json"
    fecha: str | None = None
    modo_meteo: str | None = None

    def resumen(self) -> dict:
        return {
            "fuente": self.fuente,
            "fecha_escenario": self.fecha,
            "modo_meteo": self.modo_meteo,
            "n_nodos": len(self.nodos),
            "n_camaras": len(self.camaras()),
            "n_aristas": len(self.aristas),
            "n_bases": len(self.bases),
            "n_focos": len(self.focos),
            "n_avistamientos": len(self.aves),
            "n_lecturas_meteo": len(self.meteo),
        }

    def camaras(self) -> list[int]:
        return sorted(v for v, n in self.nodos.items() if n.get("es_camara"))

    def copia_amenazas(self, focos=None, aves=None, meteo=None, fecha=None, modo_meteo=None):
        return Escenario(self.nodos, self.aristas, self.bases, self.especies,
                         self.focos if focos is None else focos,
                         self.aves if aves is None else aves,
                         self.meteo if meteo is None else meteo,
                         self.fuente, fecha or self.fecha, modo_meteo or self.modo_meteo)


def xy(lon: float, lat: float) -> np.ndarray:
    x, y = _TR.transform(lon, lat)
    return np.array([x, y], dtype=float)


def distancia_punto_segmento(p, a, b) -> float:
    ab = b - a
    den = float(np.dot(ab, ab))
    if den == 0:
        return float(np.linalg.norm(p - a))
    t = float(np.clip(np.dot(p - a, ab) / den, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def distancia_punto_linea(p, coords_xy) -> float:
    if len(coords_xy) == 1:
        return float(np.linalg.norm(p - coords_xy[0]))
    return min(distancia_punto_segmento(p, coords_xy[i], coords_xy[i + 1]) for i in range(len(coords_xy) - 1))


def _leer(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def fecha(texto):
    if not texto:
        return None
    if isinstance(texto, datetime):
        return texto
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(texto)[:19], fmt)
        except ValueError:
            continue
    return None


def lectura_meteo(d: dict, unidad: str = "m/s") -> dict:
    factor = 1 / 3.6 if (unidad or "m/s").replace(" ", "").lower() in ("km/h", "kmh") else 1.0

    def num(k, f=1.0):
        v = d.get(k)
        return None if v is None else float(v) * f

    t = num("temperatura")
    return {
        "temperatura": t,
        "temperatura_min": num("temperatura_min") if d.get("temperatura_min") is not None else t,
        "temperatura_max": num("temperatura_max") if d.get("temperatura_max") is not None else t,
        "humedad": num("humedad"),
        "viento_ms": num("viento", factor),
        "rafaga_ms": num("rafaga", factor),
        "precipitacion_mm": num("precipitacion_mm") if d.get("precipitacion_mm") is not None else num("lluvia_mm_h"),
        "prob_lluvia": num("prob_lluvia"),
        "fecha": d.get("fecha"),
    }


def _arista(a: dict, perfil: dict | None, privadas: set) -> dict:
    perfil = perfil or {}
    puntos = perfil.get("puntos")
    coords = [[p[0], p[1]] for p in puntos] if puntos else a["coordenadas"]
    d2 = float(perfil.get("largo_2d_m") or a["distancia_m"])
    return {
        "id": a["id"], "source": a["source"], "target": a["target"], "tipo": a.get("tipo"),
        "distancia_m": d2, "largo_3d_m": float(perfil.get("largo_3d_m") or d2),
        "ascenso_ida_m": float(perfil.get("ascenso_ida_m") or 0.0),
        "ascenso_vuelta_m": float(perfil.get("ascenso_vuelta_m") or 0.0),
        "despeje_min_m": perfil.get("despeje_min_m"), "densificada": bool(perfil.get("densificada")),
        "bloqueada": bool(perfil.get("bloqueada")), "motivo_bloqueo": perfil.get("motivo"),
        "coords": coords, "puntos": puntos, "buffer_privacidad": a["id"] in privadas, "base_id": None,
    }


def _enlace(e: dict, base_id: int, nodo_base: int) -> dict:
    return {
        "id": e["id"], "source": nodo_base, "target": e["nodo_id"], "tipo": "enlace_base",
        "distancia_m": float(e["distancia_m"]), "largo_3d_m": float(e.get("largo_3d_m") or e["distancia_m"]),
        "ascenso_ida_m": float(e.get("ascenso_ida_m") or 0.0),
        "ascenso_vuelta_m": float(e.get("ascenso_vuelta_m") or 0.0),
        "despeje_min_m": e.get("despeje_min_m"), "densificada": len(e.get("puntos") or []) > 2,
        "bloqueada": False, "motivo_bloqueo": None,
        "coords": [[p[0], p[1]] for p in e["puntos"]], "puntos": e["puntos"],
        "buffer_privacidad": False, "base_id": base_id,
    }


def armar(nodos_doc, aristas_doc, cobertura, elevacion, perfiles, bases_doc, especies_doc, privadas):
    nodos = {}
    for n in nodos_doc:
        nodos[n["id"]] = {
            "id": n["id"], "nombre": n.get("nombre"), "lon": n["lon"], "lat": n["lat"],
            "es_camara": bool(n.get("es_camara", str(n.get("nombre", "")).startswith("Camara"))),
            "es_base_sendero": False, "landcover_code": cobertura.get(n["id"], n.get("landcover_code")),
            "elevacion_m": elevacion.get(n["id"]), "especies": n.get("especies", []),
        }
    aristas = {a["id"]: _arista(a, perfiles.get(a["id"]), privadas) for a in aristas_doc}

    bases = {}
    for b in bases_doc:
        if b["tipo"] == "camara":
            nodo_base = b["nodo_id"]
        else:
            nodo_base = b["id"]
            nodos[nodo_base] = {"id": nodo_base, "nombre": b.get("nombre"), "lon": b["lon"], "lat": b["lat"],
                                "es_camara": False, "es_base_sendero": True, "landcover_code": None,
                                "elevacion_m": b.get("elevacion_m"), "especies": []}
        enlaces = []
        for e in b.get("enlaces", []):
            aristas[e["id"]] = _enlace(e, b["id"], nodo_base)
            enlaces.append(e["id"])
        bases[b["id"]] = {
            "id": b["id"], "tipo": b["tipo"], "nodo": nodo_base, "nombre": b.get("nombre"),
            "lon": b["lon"], "lat": b["lat"], "elevacion_m": b.get("elevacion_m"),
            "camaras": {c["camara_id"]: c for c in b.get("camaras", [])},
            "visibles": set(b.get("aristas_visibles", [])) | set(enlaces),
            "bloqueadas": {x["arista_id"]: x["motivo"] for x in b.get("aristas_bloqueadas", [])},
            "enlaces": enlaces,
        }
    especies = {e["cientifico"]: e for e in especies_doc}
    return nodos, aristas, bases, especies


def _privadas(senderos: dict | None) -> set:
    return {ar["id"] for s in (senderos or {}).get("senderos", [])
            for ar in (s.get("aristas_cercanas") if isinstance(s.get("aristas_cercanas"), list) else [])
            if ar.get("buffer_privacidad", False)}


def desde_documentos(docs: dict, fuente: str = "json") -> Escenario:
    nodos, aristas, bases, especies = armar(
        docs["nodos"], docs["aristas"], docs.get("cobertura", {}), docs.get("elevacion", {}),
        docs.get("perfiles", {}), docs.get("bases", []), docs.get("especies", []), docs.get("privadas", set()))
    aves = [{**a, "fecha_obs": fecha(a.get("fecha_obs"))} for a in docs.get("aves", [])]
    esc = Escenario(nodos, aristas, bases, especies, docs.get("focos", []), aves, docs.get("meteo", {}),
                    fuente, docs.get("fecha"), docs.get("modo_meteo"))
    completar_meteo_bases(esc)
    return esc


def completar_meteo_bases(esc: Escenario):
    camaras = [(v, xy(esc.nodos[v]["lon"], esc.nodos[v]["lat"])) for v in esc.camaras() if v in esc.meteo]
    if not camaras:
        return
    for v, n in esc.nodos.items():
        if n.get("es_base_sendero") and v not in esc.meteo:
            p = xy(n["lon"], n["lat"])
            cercana = min(camaras, key=lambda c: float(np.linalg.norm(c[1] - p)))[0]
            esc.meteo[v] = {**esc.meteo[cercana], "desde_camara": cercana}


def meteo_desde_doc(meteo_doc: dict | None) -> tuple[dict, str | None, str | None]:
    meteo_doc = meteo_doc or {}
    meta = meteo_doc.get("meta") or {}
    unidad = meta.get("unidad_viento", "m/s")
    meteo = {}
    for lec in meteo_doc.get("lecturas", []):
        meteo[int(lec["nodo_id"])] = lectura_meteo(lec, unidad)
    return meteo, meta.get("modo"), meta.get("fecha_escenario")


def documentos_repo(raiz: Path = RAIZ) -> dict:
    raiz = Path(raiz)
    leer = lambda *p: _leer(raiz.joinpath(*p))
    cobertura = leer("Metadata", "metadata_cobertura.json") or {"registros": []}
    dem = leer("Metadata", "metadata_dem.json") or {"nodos": []}
    perfiles = leer("Infraestructura", "perfiles_aristas.json") or {"perfiles": []}
    bases = leer("Infraestructura", "bases.json") or {"bases": []}
    especies = leer("Metadata", "especies_rce.json") or {"especies": []}
    firms = leer("Amenazas", "amenaza_firms.json") or {}
    ebird = leer("Amenazas", "amenaza_ebird.json") or {}
    meteo, modo, fecha_meteo = meteo_desde_doc(leer("Amenazas", "amenaza_meteo.json"))
    return {
        "nodos": leer("Infraestructura", "nodosv2.json")["nodos"],
        "aristas": leer("Infraestructura", "aristasv2.json")["aristas"],
        "cobertura": {r["nodo_id"]: r.get("landcover_code") for r in cobertura["registros"]},
        "elevacion": {r["nodo_id"]: r.get("elevacion_m") for r in dem["nodos"]},
        "perfiles": {p["arista_id"]: p for p in perfiles["perfiles"]},
        "bases": bases["bases"],
        "especies": especies["especies"],
        "privadas": _privadas(leer("Metadata", "metadata_senderos.json")),
        "focos": [{"id": f.get("id", i), "lon": f["lon"], "lat": f["lat"], "confidence": f.get("confidence"),
                   "frp": f.get("frp"), "fecha": f.get("acq_date")}
                  for i, f in enumerate(firms.get("focos", []), start=1)],
        "aves": [{"id": a.get("id") or f"av{i}", "lon": a["lon"], "lat": a["lat"], "cientifico": a.get("cientifico"),
                  "comun": a.get("comun"), "cantidad": a.get("cantidad"), "fecha_obs": a.get("fecha_obs")}
                 for i, a in enumerate(ebird.get("avistamientos", []))],
        "meteo": meteo,
        "modo_meteo": modo,
        "fecha": (firms.get("meta") or {}).get("fecha_escenario") or fecha_meteo,
    }


def desde_repo(raiz: Path = RAIZ) -> Escenario:
    return desde_documentos(documentos_repo(raiz), "json")


def desde_juguete(path: Path) -> Escenario:
    doc = _leer(Path(path))
    meteo = {int(k): lectura_meteo(v) for k, v in (doc.get("meteo") or {}).items()}
    return desde_documentos({**doc, "meteo": meteo, "privadas": set(doc.get("privadas", []))}, "juguete")


def _filas(cur, sql, params=None):
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def desde_bd(conn=None) -> Escenario:
    propia = conn is None
    conn = conn or conectar()
    try:
        with conn.cursor() as cur:
            nodos = _filas(cur, """
                SELECT n.id, n.nombre, ST_X(n.geom) AS lon, ST_Y(n.geom) AS lat,
                       (n.nombre ILIKE 'Camara%%') AS es_camara,
                       COALESCE((SELECT json_agg(json_build_object('cientifico', e.cientifico, 'comun', e.comun,
                                 'registros', e.registros) ORDER BY e.registros DESC)
                                 FROM nodo_especie e WHERE e.nodo_id = n.id), '[]'::json) AS especies
                FROM nodos n ORDER BY n.id""")
            cob = _filas(cur, "SELECT nodo_id, landcover_code, elevacion_m FROM metadata_cobertura")
            aristas = _filas(cur, """
                SELECT id, source, target, distancia_m, costo_km, tipo,
                       ST_AsGeoJSON(geom)::json -> 'coordinates' AS coordenadas FROM aristas ORDER BY id""")
            perfiles = _filas(cur, """
                SELECT arista_id, largo_2d_m, largo_3d_m, ascenso_ida_m, ascenso_vuelta_m, despeje_min_m,
                       densificada, bloqueada, motivo,
                       ST_AsGeoJSON(geom)::json -> 'coordinates' AS puntos FROM arista_perfil""")
            privadas = {r["arista_id"] for r in _filas(cur, """
                SELECT arista_id FROM metadata_senderos_arista GROUP BY arista_id HAVING BOOL_OR(buffer_privacidad)""")}
            bases = _filas(cur, """
                SELECT id, tipo, nodo_id, nombre, elevacion_m, ST_X(geom) AS lon, ST_Y(geom) AS lat
                FROM bases ORDER BY id""")
            por_base = {b["id"]: b for b in bases}
            for b in bases:
                b.update(camaras=[], enlaces=[], aristas_visibles=[], aristas_bloqueadas=[])
            for r in _filas(cur, "SELECT * FROM base_camara"):
                por_base[r["base_id"]]["camaras"].append(r)
            for r in _filas(cur, """
                SELECT id, base_id, nodo_id, distancia_m, largo_3d_m, ascenso_ida_m, ascenso_vuelta_m,
                       despeje_min_m, ST_AsGeoJSON(geom)::json -> 'coordinates' AS puntos FROM base_enlace"""):
                por_base[r["base_id"]]["enlaces"].append(r)
            for r in _filas(cur, "SELECT base_id, arista_id, visible, motivo FROM base_arista_visible"):
                if r["visible"]:
                    por_base[r["base_id"]]["aristas_visibles"].append(r["arista_id"])
                else:
                    por_base[r["base_id"]]["aristas_bloqueadas"].append(r)
            especies = []
            for r in _filas(cur, "SELECT * FROM especie_rce"):
                ficha = r.pop("ficha") or {}
                especies.append({**r, **ficha})
            focos = _filas(cur, """
                SELECT id, ST_X(geom) AS lon, ST_Y(geom) AS lat, confidence, frp, acq_date::text AS fecha
                FROM amenazas_firms ORDER BY id""")
            aves = _filas(cur, """
                SELECT id, ST_X(geom) AS lon, ST_Y(geom) AS lat, especie_cientifico AS cientifico,
                       especie_comun AS comun, cantidad, fecha_obs FROM amenazas_ebird ORDER BY id""")
            meteo_filas = _filas(cur, """
                SELECT DISTINCT ON (nodo_id) nodo_id, fecha::text AS fecha, temperatura, temperatura_min,
                       temperatura_max, humedad, viento, rafaga, precipitacion_mm, lluvia_mm_h, prob_lluvia,
                       unidad_viento, modo
                FROM meteo_alertas ORDER BY nodo_id, fecha DESC, id DESC""")
    finally:
        if propia:
            conn.close()
    meteo = {r["nodo_id"]: lectura_meteo(r, r.get("unidad_viento") or "m/s") for r in meteo_filas if r["nodo_id"]}
    docs = {
        "nodos": nodos, "aristas": aristas,
        "cobertura": {r["nodo_id"]: r["landcover_code"] for r in cob},
        "elevacion": {r["nodo_id"]: r["elevacion_m"] for r in cob},
        "perfiles": {p["arista_id"]: p for p in perfiles}, "bases": bases, "especies": especies,
        "privadas": privadas, "focos": focos, "aves": aves, "meteo": meteo,
        "modo_meteo": meteo_filas[0]["modo"] if meteo_filas else None,
        "fecha": meteo_filas[0]["fecha"] if meteo_filas else None,
    }
    return desde_documentos(docs, "db")


_CACHE: dict = {}


def cargar(fuente: str = "db", path: str | Path | None = None, usar_cache: bool = True) -> Escenario:
    clave = (fuente, str(path))
    if usar_cache and clave in _CACHE:
        return _CACHE[clave]
    if fuente == "db":
        esc = desde_bd()
    elif path:
        esc = desde_juguete(Path(path))
    else:
        esc = desde_repo()
    if usar_cache:
        _CACHE[clave] = esc
    return esc


def limpiar_cache():
    _CACHE.clear()
