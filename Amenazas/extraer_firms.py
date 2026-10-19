import json
import os
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
ARISTAS_PATH = Path(os.getenv("ARISTAS_PATH", RAIZ / "Infraestructura" / "aristasv2.json"))
SALIDA = AQUI / "amenaza_firms.json"

SOURCE = os.getenv("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
DAY_RANGE = int(os.getenv("FIRMS_DAY_RANGE", "5"))
FECHA = os.getenv("FIRMS_FECHA", "").strip()
MARGEN = float(os.getenv("FIRMS_MARGEN_GRADOS", "0.05"))
UMBRAL_M = float(os.getenv("UMBRAL_AMENAZA_M", "1000"))
PENALIZACION_KM = float(os.getenv("PENALIZACION_KM", "1000"))
CRS_METRICO = "EPSG:32718"
API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def cargar_env():
    env = RAIZ / ".env"
    if not env.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env)


def leer_json(path: Path, clave: str) -> list[dict]:
    if not path.exists():
        sys.exit(f"No existe {path}.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data[clave] if isinstance(data, dict) else data


def bbox_de_nodos(nodos: list[dict]) -> tuple[float, float, float, float]:
    lons = [n["lon"] for n in nodos]
    lats = [n["lat"] for n in nodos]
    return (
        min(lons) - MARGEN,
        min(lats) - MARGEN,
        max(lons) + MARGEN,
        max(lats) + MARGEN,
    )


def descargar(bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    key = os.getenv("FIRMS_MAP_KEY", "").strip()
    if not key:
        sys.exit(
            "Falta FIRMS_MAP_KEY. Pídela en "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ "
            "y expórtala en el entorno o en .env."
        )
    if not 1 <= DAY_RANGE <= 5:
        sys.exit("FIRMS_DAY_RANGE debe estar entre 1 y 5.")
    area = ",".join(f"{v:.4f}" for v in bbox)
    url = f"{API}/{key}/{SOURCE}/{area}/{DAY_RANGE}"
    if FECHA:
        url = f"{url}/{FECHA}"
    print(f"Consultando {SOURCE} bbox={area} dias={DAY_RANGE} fecha={FECHA or 'reciente'}")
    resp = requests.get(url, timeout=60)
    texto = resp.text.strip()
    if resp.status_code != 200 or texto.lower().startswith("<") or "invalid" in texto.lower():
        sys.exit(f"FIRMS respondió {resp.status_code}: {texto[:400]}")
    if not texto or texto.lower().startswith("no ") or "count" in texto[:40].lower() and "," not in texto:
        return pd.DataFrame()
    df = pd.read_csv(StringIO(texto))
    if df.empty or "latitude" not in df.columns:
        return pd.DataFrame()
    return df


def proyectar(tr: Transformer, lon: float, lat: float) -> np.ndarray:
    x, y = tr.transform(lon, lat)
    return np.array([x, y], dtype=float)


def distancia_a_tramo(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    den = float(np.dot(ab, ab))
    if den == 0:
        return float(np.linalg.norm(p - a))
    t = float(np.clip(np.dot(p - a, ab) / den, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def cruzar(focos: list[dict], nodos: list[dict], aristas: list[dict]) -> None:
    tr = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    xy_nodo = {n["id"]: proyectar(tr, n["lon"], n["lat"]) for n in nodos}
    for foco in focos:
        p = proyectar(tr, foco["lon"], foco["lat"])
        dist_n = sorted(
            ((nid, float(np.linalg.norm(p - xy))) for nid, xy in xy_nodo.items()),
            key=lambda t: t[1],
        )
        cerca = dist_n[0]
        foco["nodo_mas_cercano"] = {"id": cerca[0], "distancia_m": round(cerca[1], 1)}
        foco["nodos_dentro_umbral"] = [
            {"id": nid, "distancia_m": round(d, 1)} for nid, d in dist_n if d <= UMBRAL_M
        ]
        afectadas = []
        for ar in aristas:
            d = distancia_a_tramo(p, xy_nodo[ar["source"]], xy_nodo[ar["target"]])
            if d <= UMBRAL_M:
                afectadas.append({
                    "id": ar["id"],
                    "source": ar["source"],
                    "target": ar["target"],
                    "distancia_m": round(d, 1),
                })
        foco["aristas_dentro_umbral"] = afectadas


def afectados(focos: list[dict], aristas: list[dict]) -> tuple[list[dict], list[dict]]:
    nodos: dict[int, dict] = {}
    ars: dict[int, dict] = {}
    costo = {a["id"]: a["costo_km"] for a in aristas}
    for foco in focos:
        for item in foco["nodos_dentro_umbral"]:
            bloque = nodos.setdefault(item["id"], {
                "nodo_id": item["id"],
                "distancia_min_m": item["distancia_m"],
                "focos": [],
                "evitar": True,
                "motivo": "Foco activo dentro del umbral: no se espera fauna en esa cámara.",
            })
            bloque["distancia_min_m"] = min(bloque["distancia_min_m"], item["distancia_m"])
            bloque["focos"].append(foco["id"])
        for item in foco["aristas_dentro_umbral"]:
            base = costo[item["id"]]
            bloque = ars.setdefault(item["id"], {
                "arista_id": item["id"],
                "source": item["source"],
                "target": item["target"],
                "distancia_min_m": item["distancia_m"],
                "costo_km": base,
                "focos": [],
                "evitar": True,
            })
            bloque["distancia_min_m"] = min(bloque["distancia_min_m"], item["distancia_m"])
            bloque["focos"].append(foco["id"])
    for bloque in ars.values():
        bloque["costo_resiliente_km"] = round(bloque["costo_km"] + PENALIZACION_KM, 4)
    return list(nodos.values()), list(ars.values())


def filas_a_focos(df: pd.DataFrame) -> list[dict]:
    focos = []
    for i, (_, fila) in enumerate(df.iterrows(), start=1):
        def num(col):
            valor = fila.get(col)
            if valor is None or (isinstance(valor, float) and np.isnan(valor)):
                return None
            try:
                return float(valor)
            except (TypeError, ValueError):
                return None

        def texto(col):
            valor = fila.get(col)
            if valor is None or (isinstance(valor, float) and np.isnan(valor)):
                return None
            return str(valor)

        focos.append({
            "id": i,
            "lat": num("latitude"),
            "lon": num("longitude"),
            "acq_date": texto("acq_date"),
            "acq_time": texto("acq_time"),
            "satellite": texto("satellite"),
            "confidence": texto("confidence"),
            "frp": num("frp"),
            "daynight": texto("daynight"),
            "bright_ti4": num("bright_ti4"),
        })
    return focos


def main():
    cargar_env()
    nodos = leer_json(NODOS_PATH, "nodos")
    aristas = leer_json(ARISTAS_PATH, "aristas")
    bbox = bbox_de_nodos(nodos)
    df = descargar(bbox)
    focos = filas_a_focos(df) if not df.empty else []
    cruzar(focos, nodos, aristas)
    nodos_af, aristas_af = afectados(focos, aristas)
    print(f"Focos: {len(focos)} | Nodos dentro de {UMBRAL_M:.0f} m: {len(nodos_af)} | "
          f"Aristas: {len(aristas_af)}")
    documento = {
        "meta": {
            "fuente": "NASA FIRMS",
            "source": SOURCE,
            "endpoint": API,
            "bbox": {"west": bbox[0], "south": bbox[1], "east": bbox[2], "north": bbox[3]},
            "margen_grados": MARGEN,
            "day_range": DAY_RANGE,
            "fecha": FECHA or None,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nodos_origen": ruta_repo(NODOS_PATH),
            "aristas_origen": ruta_repo(ARISTAS_PATH),
            "crs_metrico": CRS_METRICO,
            "umbral_amenaza_m": UMBRAL_M,
            "penalizacion_km": PENALIZACION_KM,
            "regla_peso": (
                f"Si la distancia de un tramo al foco es <= {UMBRAL_M:.0f} m, "
                f"evitar = true y costo_resiliente_km = costo_km + {PENALIZACION_KM:.0f}. "
                "El Dijkstra de la fase 2 no usa este costo: solo costo_km. "
                "El costo penalizado queda para el algoritmo de la fase 3."
            ),
            "n_focos": len(focos),
            "n_nodos_afectados": len(nodos_af),
            "n_aristas_afectadas": len(aristas_af),
            "resultado": "con_focos" if focos else "sin_focos_en_area",
        },
        "focos": focos,
        "nodos_afectados": nodos_af,
        "aristas_afectadas": aristas_af,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito: {SALIDA}")


if __name__ == "__main__":
    main()
