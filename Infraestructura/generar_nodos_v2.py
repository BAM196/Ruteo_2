import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
OCCURRENCE = Path(os.getenv("OCCURRENCE_PATH", RAIZ / "data" / "occurrence.txt"))
SALIDA_NODOS = AQUI / "nodosv2.json"
SALIDA_ARISTAS = AQUI / "aristasv2.json"

K_VECINOS = int(os.getenv("K_VECINOS", "2"))
MAX_ARISTA_M = float(os.getenv("MAX_ARISTA_M", "3000"))
LOCALIDAD = os.getenv("LOCALIDAD", "Pumal")
BBOX = os.getenv("NODOS_BBOX", "none")
CRS_METRICO = "EPSG:32718"  # UTM 18S; Pumalín queda al oeste de -72
MAX_NODOS_MST = 6000

# Parámetros de exploración y evasión del dron
RADIO_ANILLO_CAMARA_M = float(os.getenv("RADIO_ANILLO_CAMARA_M", "450"))
OFFSET_LATERAL_ARISTA_M = float(os.getenv("OFFSET_LATERAL_ARISTA_M", "800"))
MIN_LARGO_DESVIO_M = float(os.getenv("MIN_LARGO_DESVIO_M", "900"))

COLUMNAS = {
    "decimalLatitude", "decimalLongitude", "locality", "eventID",
    "year", "scientificName", "vernacularName", "species",
}


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.p[rb] = ra
        return True


def cargar_ocurrencias() -> pd.DataFrame:
    if not OCCURRENCE.exists():
        sys.exit(f"No existe {OCCURRENCE}. Descarga occurrence.txt o define OCCURRENCE_PATH.")
    df = pd.read_csv(
        OCCURRENCE, sep="\t", low_memory=False, usecols=lambda c: c in COLUMNAS,
    )
    for col in ("decimalLatitude", "decimalLongitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["decimalLatitude", "decimalLongitude"])
    if LOCALIDAD and "locality" in df.columns:
        df = df[df["locality"].astype(str).str.contains(LOCALIDAD, case=False, na=False)]
    if BBOX.lower() != "none":
        w, s, e, n = (float(x) for x in BBOX.split(","))
        df = df[df["decimalLatitude"].between(s, n) & df["decimalLongitude"].between(w, e)]
    if df.empty:
        sys.exit("Sin registros tras filtrar. Revisa NODOS_BBOX / LOCALIDAD.")
    return df


def _modo(serie: pd.Series) -> str:
    limpio = serie.dropna().astype(str).str.strip()
    limpio = limpio[limpio != ""]
    if limpio.empty:
        return ""
    return str(limpio.mode().iloc[0])


def construir_nodos(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["lat_k"] = (df["decimalLatitude"] * 1_000_000).round().astype("int64")
    df["lon_k"] = (df["decimalLongitude"] * 1_000_000).round().astype("int64")
    col_sp = next((c for c in ("scientificName", "species") if c in df.columns), None)
    if col_sp is None:
        print("AVISO: no hay columna de especie; 'especies' quedará vacío.")

    nodos = []
    for (_, _), g in df.groupby(["lat_k", "lon_k"], sort=False):
        especies = []
        if col_sp:
            for cientifico, sg in g.groupby(g[col_sp].fillna("").astype(str).str.strip()):
                if not cientifico:
                    continue
                comun = _modo(sg["vernacularName"]) if "vernacularName" in sg.columns else ""
                especies.append({
                    "cientifico": cientifico,
                    "comun": comun,
                    "registros": int(len(sg)),
                })
            especies.sort(key=lambda e: (-e["registros"], e["cientifico"]))
        codigos = []
        if "eventID" in g.columns:
            codigos = sorted({str(x).strip() for x in g["eventID"].dropna() if str(x).strip()})
        anios = []
        if "year" in g.columns:
            anios = sorted({int(y) for y in pd.to_numeric(g["year"], errors="coerce").dropna()})
        sufijo = codigos[0].split(":")[-1] if codigos else f"{len(nodos) + 1}"
        nodos.append({
            "lat": float(g["lat_k"].iloc[0] / 1_000_000),
            "lon": float(g["lon_k"].iloc[0] / 1_000_000),
            "nombre": f"Camara {sufijo}",
            "es_camara": True,
            "tipo_nodo": "camara",
            "codigos_estacion": codigos,
            "localidad": _modo(g["locality"]) if "locality" in g.columns else "",
            "n_registros": int(len(g)),
            "anios": anios,
            "especies": especies,
        })
    nodos.sort(key=lambda n: (n["lat"], n["lon"]))
    for i, n in enumerate(nodos, start=1):
        n["id"] = i
    return [{"id": n["id"], **{k: v for k, v in n.items() if k != "id"}} for n in nodos]


def construir_aristas(nodos: list[dict]) -> list[dict]:
    n = len(nodos)
    if n < 2:
        sys.exit("Se necesitan al menos 2 nodos.")
    tr = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    xy = np.array([tr.transform(nd["lon"], nd["lat"]) for nd in nodos])

    k = min(K_VECINOS + 1, n)
    _, idx = cKDTree(xy).query(xy, k=k)
    pares = {
        tuple(sorted((i, int(j))))
        for i in range(n)
        for j in np.atleast_1d(idx[i])[1:]
    }

    uf = UnionFind(n)
    for a, b in pares:
        uf.union(a, b)
    n_comp = len({uf.find(i) for i in range(n)})

    tipo = {p: "knn" for p in pares}
    if n_comp > 1:
        if n > MAX_NODOS_MST:
            print(
                f"AVISO: {n_comp} componentes y {n} nodos (> {MAX_NODOS_MST}); "
                "no se reparó la conectividad."
            )
        else:
            dist = cdist(xy, xy)
            mst = minimum_spanning_tree(csr_matrix(dist)).tocoo()
            for a, b in zip(mst.row, mst.col):
                if uf.union(int(a), int(b)):
                    tipo[tuple(sorted((int(a), int(b))))] = "conexion"

    aristas = []
    for eid, (a, b) in enumerate(sorted(tipo), start=1):
        d = float(np.hypot(*(xy[a] - xy[b])))
        aristas.append({
            "id": eid,
            "source": nodos[a]["id"],
            "target": nodos[b]["id"],
            "distancia_m": round(d, 1),
            "costo_km": round(d / 1000.0, 4),
            "tipo": tipo[(a, b)],
            "excede_max": bool(d > MAX_ARISTA_M),
            "coordenadas": [
                [nodos[a]["lon"], nodos[a]["lat"]],
                [nodos[b]["lon"], nodos[b]["lat"]],
            ],
        })
    return aristas


def agregar_nodos_exploracion(
    nodos: list[dict],
    aristas: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Crea nodos auxiliares (es_camara=False):
    1. Anillo de 4 waypoints alrededor de cada cámara.
    2. Corredores laterales paralelos alrededor de las aristas entre cámaras.
    """
    to_utm = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    to_wgs = Transformer.from_crs(CRS_METRICO, "EPSG:4326", always_xy=True)

    nodo_por_id = {nd["id"]: nd for nd in nodos}
    utm_por_id = {
        nd["id"]: np.array(to_utm.transform(nd["lon"], nd["lat"]))
        for nd in nodos
    }
    pares_existentes = {
        tuple(sorted((e["source"], e["target"]))) for e in aristas
    }

    camaras_originales = list(nodos)
    aristas_originales = list(aristas)

    def crear_waypoint(xy_utm: np.ndarray, nombre: str, tipo_nodo: str, localidad: str) -> int:
        lon, lat = to_wgs.transform(float(xy_utm[0]), float(xy_utm[1]))
        nuevo_id = len(nodos) + 1
        nuevo_nodo = {
            "id": nuevo_id,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "nombre": nombre,
            "es_camara": False,
            "tipo_nodo": tipo_nodo,
            "codigos_estacion": [],
            "localidad": localidad,
            "n_registros": 0,
            "anios": [],
            "especies": [],
        }
        nodos.append(nuevo_nodo)
        nodo_por_id[nuevo_id] = nuevo_nodo
        utm_por_id[nuevo_id] = xy_utm
        return nuevo_id

    def crear_arista(u: int, v: int, tipo_arista: str):
        par = tuple(sorted((u, v)))
        if par in pares_existentes or u == v:
            return
        pares_existentes.add(par)
        d = float(np.hypot(*(utm_por_id[u] - utm_por_id[v])))
        aristas.append({
            "id": len(aristas) + 1,
            "source": u,
            "target": v,
            "distancia_m": round(d, 1),
            "costo_km": round(d / 1000.0, 4),
            "tipo": tipo_arista,
            "excede_max": bool(d > MAX_ARISTA_M),
            "coordenadas": [
                [nodo_por_id[u]["lon"], nodo_por_id[u]["lat"]],
                [nodo_por_id[v]["lon"], nodo_por_id[v]["lat"]],
            ],
        })

    # 1. Anillo de exploración alrededor de cada cámara (4 puntos cardinales)
    anillos_camara: dict[int, list[int]] = {}
    puntos_cardinales = [
        ("N", np.array([0.0, 1.0])),
        ("SE", np.array([0.866, -0.5])),
        ("SO", np.array([-0.866, -0.5])),
    ]

    for cam in camaras_originales:
        cid = cam["id"]
        centro = utm_por_id[cid]
        wps_anillo = []
        for sufijo_card, dir_vec in puntos_cardinales:
            wp_id = crear_waypoint(
                centro + dir_vec * RADIO_ANILLO_CAMARA_M,
                f"WP Anillo C{cid}-{sufijo_card}",
                "waypoint_camara",
                cam["localidad"],
            )
            wps_anillo.append(wp_id)
            # Conexión radial cámara <-> perímetro
            crear_arista(cid, wp_id, "radio_camara")

        # Cerrar el perímetro alrededor de la cámara
        for i in range(len(wps_anillo)):
            crear_arista(
                wps_anillo[i],
                wps_anillo[(i + 1) % len(wps_anillo)],
                "anillo_camara",
            )
        anillos_camara[cid] = wps_anillo

    # 2. Corredores laterales alrededor de las aristas conectadas a las cámaras
    for e in aristas_originales:
        u, v = e["source"], e["target"]
        p1, p2 = utm_por_id[u], utm_por_id[v]
        vec = p2 - p1
        largo = float(np.hypot(*vec))
        if largo < 2000.0:
            continue

        unit = vec / largo
        perp = np.array([-unit[1], unit[0]])

        # En tramos largos (> 2.8 km) creamos 2 waypoints por lado; en medianos, 1 por lado
        fracciones = [0.50]

        for signo, lado in ((1.0, "Izq"), (-1.0, "Der")):
            wps_lado = []
            for idx_f, frac in enumerate(fracciones, start=1):
                punto_base = p1 + vec * frac
                wp_xy = punto_base + signo * OFFSET_LATERAL_ARISTA_M * perp
                wp_id = crear_waypoint(
                    wp_xy,
                    f"WP Desvio C{u}-C{v} {lado}-{idx_f}",
                    "waypoint_arista",
                    nodo_por_id[u]["localidad"],
                )
                wps_lado.append(wp_id)

            # Conectar secuencia del desvío: Cámara U -> WP1 -> (WP2) -> Cámara V
            secuencia = [u] + wps_lado + [v]
            for i in range(len(secuencia) - 1):
                crear_arista(secuencia[i], secuencia[i + 1], "desvio_arista")

            # Enlazar también con el nodo más cercano del anillo de cada cámara
            if u in anillos_camara:
                wp_cercano_u = min(
                    anillos_camara[u],
                    key=lambda wid: float(np.hypot(*(utm_por_id[wid] - utm_por_id[wps_lado[0]]))),
                )
                crear_arista(wp_cercano_u, wps_lado[0], "enlace_anillo")

            if v in anillos_camara:
                wp_cercano_v = min(
                    anillos_camara[v],
                    key=lambda wid: float(np.hypot(*(utm_por_id[wid] - utm_por_id[wps_lado[-1]]))),
                )
                crear_arista(wps_lado[-1], wp_cercano_v, "enlace_anillo")

    return nodos, aristas


def main():
    df = cargar_ocurrencias()
    nodos = construir_nodos(df)
    aristas = construir_aristas(nodos)

    n_camaras = len(nodos)
    n_aristas_base = len(aristas)
    nodos, aristas = agregar_nodos_exploracion(nodos, aristas)

    largos = np.array([e["distancia_m"] for e in aristas])
    print(f"Cámaras reales: {n_camaras} | Nodos totales (con waypoints): {len(nodos)}")
    print(f"Aristas base: {n_aristas_base} | Aristas totales: {len(aristas)}")
    print(
        f"Largo aristas (m): min {largos.min():.0f} | media {largos.mean():.0f} | "
        f"max {largos.max():.0f}"
    )

    meta = {
        "fuente": "GBIF Chile - fotomonitoreo CONAF 2021 (occurrence.txt)",
        "area": "Parque Nacional Pumalín Douglas Tompkins",
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filtro_localidad": LOCALIDAD,
        "bbox": BBOX,
        "k_vecinos": K_VECINOS,
        "max_arista_m": MAX_ARISTA_M,
        "radio_anillo_camara_m": RADIO_ANILLO_CAMARA_M,
        "offset_lateral_arista_m": OFFSET_LATERAL_ARISTA_M,
        "crs": "EPSG:4326",
        "crs_metrico": CRS_METRICO,
        "n_camaras": n_camaras,
        "n_nodos": len(nodos),
        "n_aristas": len(aristas),
        "nota_grafo": (
            "Grafo no dirigido con nodos cámara (es_camara=true) y waypoints "
            "de exploración/evasión (es_camara=false). En pgr_dijkstra usar directed => false."
        ),
    }
    SALIDA_NODOS.write_text(
        json.dumps({"meta": meta, "nodos": nodos}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    SALIDA_ARISTAS.write_text(
        json.dumps({"meta": meta, "aristas": aristas}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Escritos: {SALIDA_NODOS.name}, {SALIDA_ARISTAS.name}")


if __name__ == "__main__":
    main()