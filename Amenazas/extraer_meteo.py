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
SALIDA = AQUI / "amenaza_meteo.json"

SOURCE = os.getenv("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
DAY_RANGE = int(os.getenv("FIRMS_DAY_RANGE", "5"))
FECHA = os.getenv("FIRMS_FECHA", "").strip()
MARGEN = float(os.getenv("FIRMS_MARGEN_GRADOS", "0.05"))
UMBRAL_M = float(os.getenv("UMBRAL_AMENAZA_M", "1000"))
PENALIZACION_KM = float(os.getenv("PENALIZACION_KM", "1000"))
CRS_METRICO = "EPSG:32718"
API = "https://api.open-meteo.com/v1/forecast"


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

def consultar_clima_nodo(lat: float, lon: float) -> dict:
    "Consulta la API de Open-Meteo para un nodo específico."
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
                "cloud_cover,"
                "wind_speed_80m,"
                "wind_direction_80m,"
                "wind_gusts_10m,"
                "precipitation"
            ),
        "timezone": "auto"
    }
    
    try:
        resp = requests.get(API, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("current", {})
    except Exception as e:
        print(f"Error consultando Open-Meteo para ({lat}, {lon}): {e}")
    
    return {}

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


def cruzar_con_clima(nodos: list[dict], aristas: list[dict]) -> list[dict]:
    """
    Consulta Open-Meteo para cada nodo y usa la geometría para encontrar 
    qué aristas (tramos) están cerca de nodos con clima peligroso.
    """
    tr = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    xy_nodo = {n["id"]: proyectar(tr, n["lon"], n["lat"]) for n in nodos}
    
    puntos_criticos = []

    print("Consultando Open-Meteo por nodo y evaluando riesgos...")
    for nodo in nodos:
        nid = nodo["id"]
        lat = nodo["lat"]
        lon = nodo["lon"]
        
        clima = consultar_clima_nodo(lat, lon)
        temp = clima.get("temperature_2m", 0.0)
        humedad = clima.get("relative_humidity_2m", 100.0)
        viento = clima.get("wind_speed_10m", 0.0)
        
        es_amenaza = (temp > 35.0) and (humedad < 30.0) and (viento > 30.0)
        
        if es_amenaza:
            p = xy_nodo[nid]
            # Encontrar aristas afectadas alrededor de este nodo crítico dentro del umbral
            aristas_afectadas = []
            for ar in aristas:
                d = distancia_a_tramo(p, xy_nodo[ar["source"]], xy_nodo[ar["target"]])
                if d <= UMBRAL_M:
                    aristas_afectadas.append({
                        "id": ar["id"],
                        "source": ar["source"],
                        "target": ar["target"],
                        "distancia_m": round(d, 1)
                    })
            
            puntos_criticos.append({
                "nodo_origen_alerta": nid,
                "lat": lat,
                "lon": lon,
                "temperatura": temp,
                "humedad": humedad,
                "viento": viento,
                "aristas_dentro_umbral": aristas_afectadas
            })
            
    return puntos_criticos

def afectados(puntos_criticos: list[dict], aristas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Agrupa nodos y aristas que deben evitarse debido a las alertas meteorológicas."""
    nodos_afectados: dict[int, dict] = {}
    ars_afectadas: dict[int, dict] = {}
    costo = {a["id"]: a["costo_km"] for a in aristas}
    
    for alerta in puntos_criticos:
        nid = alerta["nodo_origen_alerta"]
        nodos_afectados[nid] = {
            "nodo_id": nid,
            "distancia_min_m": 0.0,
            "motivo": f"Alerta meteorológica directa (Temp: {alerta['temperatura']}°C, Humedad: {alerta['humedad']}%)",
            "evitar": True
        }
        
        for item in alerta["aristas_dentro_umbral"]:
            aid = item["id"]
            base = costo[aid]
            bloque = ars_afectadas.setdefault(aid, {
                "arista_id": aid,
                "source": item["source"],
                "target": item["target"],
                "distancia_min_m": item["distancia_m"],
                "costo_km": base,
                "evitar": True
            })
            bloque["distancia_min_m"] = min(bloque["distancia_min_m"], item["distancia_m"])
            
    for bloque in ars_afectadas.values():
        bloque["costo_resiliente_km"] = round(bloque["costo_km"] + PENALIZACION_KM, 4)
        
    return list(nodos_afectados.values()), list(ars_afectadas.values())
def main():
    nodos = leer_json(NODOS_PATH, "nodos")
    aristas = leer_json(ARISTAS_PATH, "aristas")
    
    puntos_criticos = cruzar_con_clima(nodos, aristas)
    nodos_af, aristas_af = afectados(puntos_criticos, aristas)
    
    print(f"Nodos críticos por clima: {len(puntos_criticos)} | Aristas afectadas: {len(aristas_af)}")
    
    documento = {
        "meta": {
            "fuente": "Open-Meteo API",
            "endpoint": API,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "umbral_amenaza_m": UMBRAL_M,
            "n_aristas_afectadas": len(aristas_af)
        },
        "alertas_meteorologicas": puntos_criticos,
        "nodos_afectados": nodos_af,
        "aristas_afectadas": aristas_af
    }
    
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito: {SALIDA}")

if __name__ == "__main__":
    main()