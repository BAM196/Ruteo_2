import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
import yaml
from pyproj import Transformer

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
ARISTAS_PATH = Path(os.getenv("ARISTAS_PATH", RAIZ / "Infraestructura" / "aristasv2.json"))
AMENAZAS_YAML = RAIZ / "Motor" / "config" / "amenazas.yaml"
SALIDA = AQUI / "amenaza_ebird.json"

API = "https://api.ebird.org/v2/data/obs"
REGION = os.getenv("EBIRD_REGION", "CL-LL")
DIAS = int(os.getenv("EBIRD_BACK_DAYS", "14"))
RADIO_CONSULTA_KM = 50
CRS_METRICO = "EPSG:32718"

GENEROS = (
    "buteo", "geranoaetus", "falco", "caracara", "milvago", "parabuteo", "bubo", "glaucidium",
    "strix", "vultur", "cathartes", "coragyps", "larus", "chroicocephalus", "sterna",
    "leucophaeus", "vanellus",
)


def valor(x):
    return x["valor"] if isinstance(x, dict) and "valor" in x else x


def radio_amenaza() -> float:
    eb = yaml.safe_load(AMENAZAS_YAML.read_text(encoding="utf-8"))["amenazas"]["ebird"]
    r_mov = float(valor(eb["r_mov_m"]))
    calculado = AQUI / "aves_desplazamiento.json"
    if calculado.exists():
        r_mov = float(json.loads(calculado.read_text(encoding="utf-8"))["meta"]["r_mov_m"])
    return float(valor(eb["distancia_precaucion_m"])) + r_mov


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
    return json.loads(path.read_text(encoding="utf-8"))[clave]


def distancia_a_tramo(p, a, b) -> float:
    ab = b - a
    den = float(np.dot(ab, ab))
    if den == 0:
        return float(np.linalg.norm(p - a))
    t = float(np.clip(np.dot(p - a, ab) / den, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def es_objetivo(obs: dict) -> bool:
    sci = (obs.get("sciName") or "").lower()
    return any(sci.startswith(g) for g in GENEROS)


def a_registro(obs: dict) -> dict:
    return {
        "id": f"{obs.get('subId')}:{obs.get('speciesCode')}",
        "lista": obs.get("subId"),
        "cientifico": obs.get("sciName"),
        "comun": obs.get("comName"),
        "fecha_obs": obs.get("obsDt"),
        "cantidad": obs.get("howMany") or 1,
        "localidad": obs.get("locName"),
        "lat": float(obs["lat"]),
        "lon": float(obs["lng"]),
    }


def pedir(url: str, params: dict, token: str) -> list[dict]:
    resp = requests.get(url, params=params, headers={"X-eBirdApiToken": token}, timeout=60)
    if resp.status_code != 200:
        print(f"eBird respondió {resp.status_code}: {resp.text[:200]}")
        return []
    return resp.json()


def recientes(centros, token: str) -> list[dict]:
    salida = []
    for lat, lon in centros:
        salida += pedir(f"{API}/geo/recent", {"lat": f"{lat:.4f}", "lng": f"{lon:.4f}",
                                               "dist": RADIO_CONSULTA_KM, "back": DIAS}, token)
    return salida


def historicos(fecha: date, token: str) -> list[dict]:
    salida = []
    for k in range(DIAS):
        d = fecha - timedelta(days=k)
        salida += pedir(f"{API}/{REGION}/historic/{d.year}/{d.month}/{d.day}",
                        {"rank": "mrec", "detail": "simple"}, token)
    return salida


def dentro_del_parque(av: dict, bbox) -> bool:
    return bbox[0] <= av["lon"] <= bbox[2] and bbox[1] <= av["lat"] <= bbox[3]


def main():
    ap = argparse.ArgumentParser(description="Avistamientos de aves de eBird cerca de la red.")
    ap.add_argument("--fecha", default=os.getenv("ESCENARIO_FECHA") or None,
                    help="YYYY-MM-DD: observaciones de los 14 días que terminan en esa fecha")
    args = ap.parse_args()
    cargar_env()
    nodos = leer_json(NODOS_PATH, "nodos")
    aristas = leer_json(ARISTAS_PATH, "aristas")
    umbral = radio_amenaza()
    lats = [n["lat"] for n in nodos]
    lons = [n["lon"] for n in nodos]
    margen = 0.05
    bbox = (min(lons) - margen, min(lats) - margen, max(lons) + margen, max(lats) + margen)
    lon_c = float(np.mean(lons))
    tercio = (max(lats) - min(lats)) / 4
    centros = [(min(lats) + tercio, lon_c), (max(lats) - tercio, lon_c)]

    token = os.getenv("EBIRD_API_KEY", "").strip()
    if not token:
        if SALIDA.exists():
            print(f"Falta EBIRD_API_KEY en .env: se mantiene {ruta_repo(SALIDA)} sin cambios.")
            return
        print("Aviso: falta EBIRD_API_KEY; se guarda una lista vacía.")
        crudos = []
    elif args.fecha:
        print(f"Consultando eBird histórico en {REGION}, {DIAS} días hasta {args.fecha}")
        crudos = historicos(date.fromisoformat(args.fecha), token)
    else:
        print(f"Consultando eBird reciente ({DIAS} días) desde {len(centros)} puntos con radio de {RADIO_CONSULTA_KM} km")
        crudos = recientes(centros, token)

    vistos, avistamientos = set(), []
    for obs in crudos:
        if not es_objetivo(obs) or "lat" not in obs:
            continue
        av = a_registro(obs)
        if av["id"] in vistos or not dentro_del_parque(av, bbox):
            continue
        vistos.add(av["id"])
        avistamientos.append(av)

    tr = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)
    xy = {n["id"]: np.array(tr.transform(n["lon"], n["lat"])) for n in nodos}
    nodos_af, aristas_af = {}, {}
    for av in avistamientos:
        p = np.array(tr.transform(av["lon"], av["lat"]))
        av["nodos_dentro_umbral"] = [
            {"id": nid, "distancia_m": round(float(np.linalg.norm(p - q)), 1)}
            for nid, q in xy.items() if np.linalg.norm(p - q) <= umbral]
        av["aristas_dentro_umbral"] = []
        for ar in aristas:
            d = distancia_a_tramo(p, xy[ar["source"]], xy[ar["target"]])
            if d <= umbral:
                av["aristas_dentro_umbral"].append({"id": ar["id"], "source": ar["source"],
                                                    "target": ar["target"], "distancia_m": round(d, 1)})
        for item in av["nodos_dentro_umbral"]:
            b = nodos_af.setdefault(item["id"], {"nodo_id": item["id"], "distancia_min_m": item["distancia_m"],
                                                 "avistamientos": []})
            b["distancia_min_m"] = min(b["distancia_min_m"], item["distancia_m"])
            b["avistamientos"].append(av["id"])
        for item in av["aristas_dentro_umbral"]:
            b = aristas_af.setdefault(item["id"], {"arista_id": item["id"], "source": item["source"],
                                                   "target": item["target"],
                                                   "distancia_min_m": item["distancia_m"], "avistamientos": []})
            b["distancia_min_m"] = min(b["distancia_min_m"], item["distancia_m"])
            b["avistamientos"].append(av["id"])

    documento = {
        "meta": {
            "fuente": "eBird API 2.0 (The Cornell Lab of Ornithology)",
            "endpoint": f"{API}/{REGION}/historic/{{y}}/{{m}}/{{d}}" if args.fecha else f"{API}/geo/recent",
            "modo": "historico" if args.fecha else "reciente",
            "fecha_escenario": args.fecha,
            "region": REGION,
            "dias_atras": DIAS,
            "puntos_consulta": [] if args.fecha else [{"lat": round(a, 4), "lon": round(b, 4)} for a, b in centros],
            "radio_consulta_km": RADIO_CONSULTA_KM,
            "filtro": "Rapaces, carroñeras, gaviotas y queltehues: aves grandes o territoriales que pueden atacar o chocar con el dron",
            "generos": list(GENEROS),
            "umbral_amenaza_m": umbral,
            "regla": "Se listan los nodos y aristas a <= 100 m + r_mov de cada avistamiento; la probabilidad se calcula en el motor.",
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_avistamientos": len(avistamientos),
            "n_nodos_afectados": len(nodos_af),
            "n_aristas_afectadas": len(aristas_af),
        },
        "avistamientos": avistamientos,
        "nodos_afectados": list(nodos_af.values()),
        "aristas_afectadas": list(aristas_af.values()),
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Avistamientos: {len(avistamientos)} | radio de amenaza {umbral:.0f} m. Escrito: {ruta_repo(SALIDA)}")


if __name__ == "__main__":
    main()
