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
    n_comp_final = len({uf.find(i) for i in range(n)})

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

    largos = np.array([e["distancia_m"] for e in aristas])
    print(
        f"Nodos: {n} | Aristas: {len(aristas)} "
        f"({sum(e['tipo'] == 'conexion' for e in aristas)} de conexión)"
    )
    print(f"Componentes: {n_comp} -> {n_comp_final}")
    print(
        f"Largo aristas (m): min {largos.min():.0f} | media {largos.mean():.0f} | "
        f"max {largos.max():.0f} | > {MAX_ARISTA_M:.0f} m: {int((largos > MAX_ARISTA_M).sum())}"
    )
    return aristas


def main():
    df = cargar_ocurrencias()
    nodos = construir_nodos(df)
    aristas = construir_aristas(nodos)
    meta = {
        "fuente": "GBIF Chile - fotomonitoreo CONAF 2021 (occurrence.txt)",
        "area": "Parque Nacional Pumalín Douglas Tompkins",
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filtro_localidad": LOCALIDAD,
        "bbox": BBOX,
        "k_vecinos": K_VECINOS,
        "max_arista_m": MAX_ARISTA_M,
        "crs": "EPSG:4326",
        "crs_metrico": CRS_METRICO,
        "n_nodos": len(nodos),
        "n_aristas": len(aristas),
        "nota_grafo": (
            "Grafo no dirigido. En pgr_dijkstra usar directed => false, "
            "o cargar cada arista en los dos sentidos. El costo base es costo_km."
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
