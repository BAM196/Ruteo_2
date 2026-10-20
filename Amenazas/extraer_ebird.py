import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from pyproj import Transformer

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
ARISTAS_PATH = Path(os.getenv("ARISTAS_PATH", RAIZ / "Infraestructura" / "aristasv2.json"))
SALIDA = AQUI / "amenaza_ebird.json"

DIAS = int(os.getenv("EBIRD_BACK_DAYS", "14"))
UMBRAL_M = float(os.getenv("UMBRAL_EBIRD_M", "500"))
PENALIZACION_KM = float(os.getenv("PENALIZACION_KM", "200"))
CRS_METRICO = "EPSG:32718"


RAPACES_TERRITORIALES = (
    "buteo",           # Aguilucho chico (B. albigula), Aguilucho común (B. polyosoma), Aguilucho cola rojiza (B. ventralis)
    "geranoaetus",     # Águila mora (G. melanoleucus) / sinónimo eBird de Buteo polyosoma
    "falco",           # Halcón peregrino (F. peregrinus), Halcón perdiguero (F. femoralis), Cernícalo (F. sparverius)
    "caracara",        # Traro (Caracara plancus)
    "milvago",         # Tiuque (Milvago chimango)
    "parabuteo",       # Peuco (Parabuteo unicinctus)
    "bubo",            # Tucúquere (Bubo magellanicus)
    "glaucidium",      # Chuncho (Glaucidium nana)
    "strix",           # Concón (Strix rufipes)
    "vultur",          # Cóndor andino (Vultur gryphus)
    "cathartes",       # Jote de cabeza colorada (Cathartes aura)
    "coragyps",        # Jote de cabeza negra (Coragyps atratus)
    "larus",           # Gaviota dominicana (Larus dominicanus)
    "chroicocephalus", # Gaviota cáhuil (Chroicocephalus maculipennis)
    "sterna",          # Gaviotín sudamericano (Sterna hirundinacea)
    "leucophaeus",     # Gaviota austral / Franklin
    "vanellus",        # Queltehue (Vanellus chilensis)
)


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def cargar_env():
    env = RAIZ / ".env"
    if env.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env)
        except ImportError:
            pass


def leer_json(path: Path, clave: str) -> list[dict]:
    if not path.exists():
        sys.exit(f"No existe {path}.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data[clave] if isinstance(data, dict) else data


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


def consultar_ebird(lat_center: float, lon_center: float, dist_km: int = 50) -> list[dict]:
    token = os.getenv("EBIRD_API_KEY", "").strip()
    if not token:
        print("AVISO: EBIRD_API_KEY no definida. Se retorna lista vacía.")
        return []

    url = f"https://api.ebird.org/v2/data/obs/geo/recent?lat={lat_center}&lng={lon_center}&dist={dist_km}&back={DIAS}"
    headers = {"X-eBirdApiToken": token}
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"Error eBird API ({resp.status_code}): {resp.text[:200]}")
            return []
        
        datos = resp.json()
        filtrados = []
        for obs in datos:
            sci = obs.get("sciName", "").lower()
            if any(rapaz in sci for rapaz in RAPACES_TERRITORIALES):
                filtrados.append({
                    "id": obs.get("subId"),
                    "cientifico": obs.get("sciName"),
                    "comun": obs.get("comName"),
                    "fecha_obs": obs.get("obsDt"),
                    "cantidad": obs.get("howMany", 1),
                    "localidad": obs.get("locName"),
                    "lat": float(obs["lat"]),
                    "lon": float(obs["lng"])
                })
        return filtrados
    except Exception as e:
        print(f"Excepción consultando eBird: {e}")
        return []


def cruzar(avistamientos: list[dict], nodos: list[dict], aristas: list[dict]):
    tr = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    xy_nodo = {n["id"]: proyectar(tr, n["lon"], n["lat"]) for n in nodos}

    for av in avistamientos:
        p = proyectar(tr, av["lon"], av["lat"])
        dist_n = sorted(
            ((nid, float(np.linalg.norm(p - xy))) for nid, xy in xy_nodo.items()),
            key=lambda t: t[1],
        )
        cerca = dist_n[0]
        av["nodo_mas_cercano"] = {"id": cerca[0], "distancia_m": round(cerca[1], 1)}
        av["nodos_dentro_umbral"] = [
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
        av["aristas_dentro_umbral"] = afectadas


def calcular_afectados(avistamientos: list[dict], aristas: list[dict]):
    nodos_af: dict[int, dict] = {}
    aristas_af: dict[int, dict] = {}
    costos = {a["id"]: a["costo_km"] for a in aristas}

    for av in avistamientos:
        for item in av["nodos_dentro_umbral"]:
            b = nodos_af.setdefault(item["id"], {
                "nodo_id": item["id"],
                "distancia_min_m": item["distancia_m"],
                "avistamientos": [],
                "evitar": True,
                "motivo": "Presencia reciente de ave rapaz territorial con riesgo de ataque aéreo."
            })
            b["distancia_min_m"] = min(b["distancia_min_m"], item["distancia_m"])
            b["avistamientos"].append(av["id"])

        for item in av["aristas_dentro_umbral"]:
            base = costos[item["id"]]
            b = aristas_af.setdefault(item["id"], {
                "arista_id": item["id"],
                "source": item["source"],
                "target": item["target"],
                "distancia_min_m": item["distancia_m"],
                "costo_km": base,
                "costo_resiliente_km": round(base + PENALIZACION_KM, 4),
                "avistamientos": [],
                "evitar": True
            })
            b["distancia_min_m"] = min(b["distancia_min_m"], item["distancia_m"])
            b["avistamientos"].append(av["id"])

    return list(nodos_af.values()), list(aristas_af.values())


def main():
    cargar_env()
    nodos = leer_json(NODOS_PATH, "nodos")
    aristas = leer_json(ARISTAS_PATH, "aristas")

    lat_c = float(np.mean([n["lat"] for n in nodos]))
    lon_c = float(np.mean([n["lon"] for n in nodos]))

    print(f"Consultando eBird en Centroide: ({lat_c:.4f}, {lon_c:.4f}) con radio de 50 km")
    avistamientos = consultar_ebird(lat_c, lon_c)
    cruzar(avistamientos, nodos, aristas)
    nodos_af, aristas_af = calcular_afectados(avistamientos, aristas)

    documento = {
        "meta": {
            "fuente": "eBird API 2.0 (The Cornell Lab of Ornithology)",
            "endpoint": "https://api.ebird.org/v2/data/obs/geo/recent",
            "dias_atras": DIAS,
            "umbral_amenaza_m": UMBRAL_M,
            "penalizacion_km": PENALIZACION_KM,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_avistamientos": len(avistamientos),
            "n_nodos_afectados": len(nodos_af),
            "n_aristas_afectadas": len(aristas_af),
            "resultado": "con_amenazas" if avistamientos else "sin_amenazas_en_radio",
            "regla_peso": (
                f"Si la distancia al avistamiento de rapaz es <= {UMBRAL_M:.0f} m, "
                f"evitar = true y costo_resiliente_km = costo_km + {PENALIZACION_KM:.0f}."
            )
        },
        "avistamientos": avistamientos,
        "nodos_afectados": nodos_af,
        "aristas_afectadas": aristas_af
    }

    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito: {SALIDA} | Rapaces detectadas: {len(avistamientos)}")


if __name__ == "__main__":
    main()