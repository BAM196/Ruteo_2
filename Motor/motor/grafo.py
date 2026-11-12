import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from pyproj import Transformer

from .config import RAIZ, conectar

CRS_METRICO = "EPSG:32718"
_TR = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)


@dataclass
class Escenario:
    nodos: dict
    aristas: dict
    focos: list = field(default_factory=list)
    aves: list = field(default_factory=list)
    meteo: dict = field(default_factory=dict)
    fuente: str = "json"

    def resumen(self) -> dict:
        return {
            "fuente": self.fuente,
            "n_nodos": len(self.nodos),
            "n_aristas": len(self.aristas),
            "n_focos": len(self.focos),
            "n_avistamientos": len(self.aves),
            "n_lecturas_meteo": len(self.meteo),
        }


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
    return min(
        distancia_punto_segmento(p, coords_xy[i], coords_xy[i + 1])
        for i in range(len(coords_xy) - 1)
    )


def _leer(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _fecha(texto):
    if not texto:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(texto)[:19], fmt)
        except ValueError:
            continue
    return None


def lectura_meteo(temperatura, humedad, viento, rafaga, lluvia_mm_h, unidad):
    factor = 1 / 3.6 if (unidad or "km/h").replace(" ", "").lower() in ("km/h", "kmh") else 1.0
    viento_ms = None if viento is None else float(viento) * factor
    rafaga_ms = None if rafaga is None else float(rafaga) * factor
    return {
        "temperatura": None if temperatura is None else float(temperatura),
        "humedad": None if humedad is None else float(humedad),
        "viento_ms": viento_ms,
        "rafaga_ms": rafaga_ms,
        "lluvia_mm_h": None if lluvia_mm_h is None else float(lluvia_mm_h),
    }


def desde_juguete(path: Path) -> Escenario:
    doc = _leer(Path(path))
    nodos = {n["id"]: {**n, "landcover_code": n.get("landcover_code", 10)} for n in doc["nodos"]}
    aristas = {}
    for a in doc["aristas"]:
        coords = a.get("coordenadas") or [
            [nodos[a["source"]]["lon"], nodos[a["source"]]["lat"]],
            [nodos[a["target"]]["lon"], nodos[a["target"]]["lat"]],
        ]
        aristas[a["id"]] = {
            "id": a["id"], "source": a["source"], "target": a["target"],
            "distancia_m": float(a["distancia_m"]),
            "costo_km": float(a["distancia_m"]) / 1000,
            "coords": coords, "excede_max": False, "viable": a.get("viable", True),
            "buffer_privacidad": bool(a.get("buffer_privacidad", False)),
        }
    meteo = {
        int(k): lectura_meteo(v.get("temperatura"), v.get("humedad"), v.get("viento"),
                              v.get("rafaga"), v.get("lluvia_mm_h"), "m/s")
        for k, v in (doc.get("meteo") or {}).items()
    }
    aves = [{**a, "fecha_obs": _fecha(a.get("fecha_obs"))} for a in doc.get("aves", [])]
    return Escenario(nodos, aristas, doc.get("focos", []), aves, meteo, fuente="juguete")


def desde_repo(raiz: Path = RAIZ) -> Escenario:
    raiz = Path(raiz)
    doc_n = _leer(raiz / "Infraestructura" / "nodosv2.json")
    doc_a = _leer(raiz / "Infraestructura" / "aristasv2.json")
    gee = _leer(raiz / "Metadata" / "metadata_gee.json") or {"registros": []}
    lc = {r["nodo_id"]: r.get("landcover_code") for r in gee.get("registros", [])}
    senderos = _leer(raiz / "Metadata" / "metadata_senderos.json") or {}
    aristas_privadas = {
        ar["id"]
        for s in senderos.get("senderos", [])
        for ar in s.get("aristas_cercanas", [])
        if ar.get("buffer_privacidad", False)
    }

    nodos = {
        n["id"]: {"id": n["id"], "nombre": n.get("nombre"), "lon": n["lon"], "lat": n["lat"],
                  "landcover_code": lc.get(n["id"])}
        for n in doc_n["nodos"]
    }
    aristas = {
        a["id"]: {
            "id": a["id"], "source": a["source"], "target": a["target"],
            "distancia_m": float(a["distancia_m"]), "costo_km": float(a["costo_km"]),
            "coords": a["coordenadas"], "excede_max": bool(a.get("excede_max")),
            "viable": a.get("viable", True), "buffer_privacidad": a["id"] in aristas_privadas,
        }
        for a in doc_a["aristas"]
    }

    firms = _leer(raiz / "Amenazas" / "amenaza_firms.json") or {}
    focos = [
        {"id": f.get("id", i), "lon": f["lon"], "lat": f["lat"],
         "confidence": f.get("confidence"), "frp": f.get("frp"), "fecha": f.get("acq_date")}
        for i, f in enumerate(firms.get("focos", []), start=1)
    ]

    ebird = _leer(raiz / "Amenazas" / "amenaza_ebird.json") or {}
    aves = [
        {"id": f'{a.get("id")}:{i}', "lon": a["lon"], "lat": a["lat"],
         "cientifico": a.get("cientifico"), "comun": a.get("comun"),
         "cantidad": a.get("cantidad"), "fecha_obs": _fecha(a.get("fecha_obs"))}
        for i, a in enumerate(ebird.get("avistamientos", []))
    ]

    meteo_doc = _leer(raiz / "Amenazas" / "amenaza_meteo.json") or {}
    unidad = (meteo_doc.get("meta") or {}).get("unidad_viento", "km/h")
    meteo = {}
    for lec in meteo_doc.get("lecturas", meteo_doc.get("alertas_meteorologicas", [])):
        nid = lec.get("nodo_id", lec.get("nodo_origen_alerta"))
        meteo[int(nid)] = lectura_meteo(
            lec.get("temperatura"), lec.get("humedad"), lec.get("viento"),
            lec.get("rafaga"), lec.get("lluvia_mm_h"), unidad,
        )
    return Escenario(nodos, aristas, focos, aves, meteo, fuente="json")


def _columnas(cur, tabla: str) -> set:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (tabla,)
    )
    return {r[0] for r in cur.fetchall()}


def desde_bd(conn=None) -> Escenario:
    propia = conn is None
    conn = conn or conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT n.id, n.nombre, ST_X(n.geom), ST_Y(n.geom), m.landcover_code
                FROM nodos n LEFT JOIN metadata_gee m ON m.nodo_id = n.id
                ORDER BY n.id
            """)
            nodos = {r[0]: {"id": r[0], "nombre": r[1], "lon": r[2], "lat": r[3],
                            "landcover_code": r[4]} for r in cur.fetchall()}

            viable = "a.viable" if "viable" in _columnas(cur, "aristas") else "TRUE"
            cur.execute(f"""
                SELECT a.id, a.source, a.target, a.distancia_m, a.costo_km,
                       ST_AsGeoJSON(a.geom)::json -> 'coordinates', a.excede_max, {viable},
                       COALESCE(s.buffer_privacidad, FALSE)
                FROM aristas a
                LEFT JOIN (
                    SELECT arista_id, BOOL_OR(buffer_privacidad) AS buffer_privacidad
                    FROM metadata_senderos_arista
                    GROUP BY arista_id
                ) s ON s.arista_id = a.id
                ORDER BY a.id
            """)
            aristas = {r[0]: {"id": r[0], "source": r[1], "target": r[2],
                              "distancia_m": float(r[3]), "costo_km": float(r[4]),
                              "coords": r[5], "excede_max": bool(r[6]), "viable": bool(r[7]),
                              "buffer_privacidad": bool(r[8])}
                       for r in cur.fetchall()}

            cur.execute("""
                SELECT id, ST_X(geom), ST_Y(geom), confidence, frp, acq_date
                FROM amenazas_firms ORDER BY id
            """)
            focos = [{"id": r[0], "lon": r[1], "lat": r[2], "confidence": r[3],
                      "frp": r[4], "fecha": str(r[5]) if r[5] else None}
                     for r in cur.fetchall()]

            cur.execute("""
                SELECT id, ST_X(geom), ST_Y(geom), especie_cientifico, especie_comun,
                       cantidad, fecha_obs
                FROM amenazas_ebird ORDER BY id
            """)
            aves = [{"id": r[0], "lon": r[1], "lat": r[2], "cientifico": r[3],
                     "comun": r[4], "cantidad": r[5], "fecha_obs": r[6]}
                    for r in cur.fetchall()]

            cols = _columnas(cur, "meteo_alertas")
            rafaga = "rafaga" if "rafaga" in cols else "NULL"
            lluvia = "lluvia_mm_h" if "lluvia_mm_h" in cols else "NULL"
            unidad = "unidad_viento" if "unidad_viento" in cols else "'km/h'"
            cur.execute(f"""
                SELECT DISTINCT ON (nodo_id) nodo_id, temperatura, humedad, viento,
                       {rafaga}, {lluvia}, {unidad}
                FROM meteo_alertas
                ORDER BY nodo_id, fecha DESC, id DESC
            """)
            meteo = {r[0]: lectura_meteo(r[1], r[2], r[3], r[4], r[5], r[6])
                     for r in cur.fetchall() if r[0] is not None}
    finally:
        if propia:
            conn.close()
    return Escenario(nodos, aristas, focos, aves, meteo, fuente="db")


def cargar(fuente: str = "db", path: str | Path | None = None) -> Escenario:
    if fuente == "db":
        return desde_bd()
    if path:
        return desde_juguete(Path(path))
    return desde_repo()
