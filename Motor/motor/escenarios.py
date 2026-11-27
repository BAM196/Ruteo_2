import csv
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from . import grafo
from .config import ESCENARIOS, cargar_env, parametros_mision

API_METEO = "https://api.open-meteo.com/v1/forecast"
API_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
API_FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
API_EBIRD = "https://api.ebird.org/v2/data/obs"
REGION_EBIRD = "CL-LL"
DIAS_NRT = 60
GENEROS_AVES = ("buteo", "geranoaetus", "falco", "caracara", "milvago", "parabuteo", "bubo", "glaucidium",
                "strix", "vultur", "cathartes", "coragyps", "larus", "chroicocephalus", "sterna",
                "leucophaeus", "vanellus")


def _get(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 120) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "wildward-motor"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _bbox(esc, margen=0.05):
    lons = [n["lon"] for n in esc.nodos.values()]
    lats = [n["lat"] for n in esc.nodos.values()]
    return min(lons) - margen, min(lats) - margen, max(lons) + margen, max(lats) + margen


def focos(esc, fecha: date, dias: int = 5) -> tuple[list, dict]:
    cargar_env()
    key = os.getenv("FIRMS_MAP_KEY", "").strip()
    if not key:
        return [], {"firms": "sin FIRMS_MAP_KEY: no se consultaron focos"}
    fuente = "VIIRS_SNPP_SP" if (date.today() - fecha).days > DIAS_NRT else "VIIRS_SNPP_NRT"
    desde = fecha - timedelta(days=dias - 1)
    area = ",".join(f"{v:.4f}" for v in _bbox(esc))
    texto = _get(f"{API_FIRMS}/{key}/{fuente}/{area}/{dias}/{desde.isoformat()}").decode("utf-8", "replace").strip()
    filas = list(csv.DictReader(io.StringIO(texto))) if texto and "latitude" in texto[:200] else []
    salida = [{"id": i, "lon": float(f["longitude"]), "lat": float(f["latitude"]), "confidence": f.get("confidence"),
               "frp": float(f["frp"]) if f.get("frp") else None, "fecha": f.get("acq_date")}
              for i, f in enumerate(filas, start=1)]
    return salida, {"firms": f"{fuente}, {desde} a {fecha}, {len(salida)} focos"}


def meteo(esc, fecha: date) -> tuple[dict, dict, str]:
    m = parametros_mision()
    camaras = [esc.nodos[v] for v in esc.camaras()]
    historico = fecha < date.today()
    variables = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_gusts_10m", "precipitation"]
    params = {"latitude": ",".join(f"{n['lat']:.6f}" for n in camaras),
              "longitude": ",".join(f"{n['lon']:.6f}" for n in camaras),
              "daily": "sunrise", "wind_speed_unit": "ms", "timezone": "America/Santiago",
              "start_date": fecha.isoformat(), "end_date": fecha.isoformat()}
    if not historico:
        variables.append("precipitation_probability")
    params["hourly"] = ",".join(variables)
    datos = json.loads(_get(API_ARCHIVO if historico else API_METEO, params))
    datos = datos if isinstance(datos, list) else [datos]
    salida = {}
    for n, r in zip(camaras, datos):
        sr = datetime.fromisoformat(r["daily"]["sunrise"][0])
        primera = (sr + timedelta(minutes=m["inicio_ventana_min"])).replace(minute=0, second=0)
        horas = [(primera + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M") for k in range(int(round(m["ventana_h"])))]
        h = r["hourly"]
        idx = [h["time"].index(t) for t in horas if t in h["time"]]

        def serie(var):
            return [h[var][i] for i in idx if var in h and h[var][i] is not None]

        temp, prec, prob = serie("temperature_2m"), serie("precipitation"), serie("precipitation_probability")
        salida[n["id"]] = grafo.lectura_meteo({
            "temperatura": sum(temp) / len(temp) if temp else None,
            "temperatura_min": min(temp) if temp else None, "temperatura_max": max(temp) if temp else None,
            "humedad": max(serie("relative_humidity_2m") or [0]), "viento": max(serie("wind_speed_10m") or [0]),
            "rafaga": max(serie("wind_gusts_10m")) if serie("wind_gusts_10m") else None,
            "precipitacion_mm": sum(prec) if prec else None,
            "prob_lluvia": max(prob) if prob else None, "fecha": fecha.isoformat()}, "m/s")
    modo = "historico" if historico else "pronostico"
    return salida, {"meteo": f"Open-Meteo {modo}, ventana de la mañana del {fecha}"}, modo


def aves(esc, fecha: date, dias: int = 14) -> tuple[list, dict]:
    cargar_env()
    token = os.getenv("EBIRD_API_KEY", "").strip()
    if not token:
        return list(esc.aves), {"ebird": "sin EBIRD_API_KEY: se usan los avistamientos cargados"}
    oeste, sur, este, norte = _bbox(esc)
    crudos = []
    for k in range(dias):
        d = fecha - timedelta(days=k)
        try:
            crudos += json.loads(_get(f"{API_EBIRD}/{REGION_EBIRD}/historic/{d.year}/{d.month}/{d.day}",
                                      {"rank": "mrec", "detail": "simple"}, {"X-eBirdApiToken": token}))
        except Exception:
            continue
    salida, vistos = [], set()
    for o in crudos:
        sci = (o.get("sciName") or "").lower()
        if not any(sci.startswith(g) for g in GENEROS_AVES) or "lat" not in o:
            continue
        clave = f"{o.get('subId')}:{o.get('speciesCode')}"
        if clave in vistos or not (oeste <= o["lng"] <= este and sur <= o["lat"] <= norte):
            continue
        vistos.add(clave)
        salida.append({"id": clave, "lon": o["lng"], "lat": o["lat"], "cientifico": o.get("sciName"),
                       "comun": o.get("comName"), "cantidad": o.get("howMany") or 1,
                       "fecha_obs": grafo.fecha(o.get("obsDt"))})
    return salida, {"ebird": f"eBird {REGION_EBIRD}, {dias} días hasta {fecha}, {len(salida)} avistamientos"}


def cargar(esc, fecha_txt: str, usar_cache: bool = True) -> dict:
    fecha = date.fromisoformat(fecha_txt)
    ESCENARIOS.mkdir(parents=True, exist_ok=True)
    ruta = ESCENARIOS / f"{fecha.isoformat()}.json"
    pasado = fecha < date.today()
    if usar_cache and pasado and ruta.exists():
        doc = json.loads(ruta.read_text(encoding="utf-8"))
    else:
        try:
            f, nf = focos(esc, fecha)
        except Exception as exc:
            f, nf = list(esc.focos), {"firms": f"no se pudo consultar FIRMS ({exc}); se usan los focos cargados"}
        try:
            mt, nm, modo = meteo(esc, fecha)
        except Exception as exc:
            mt = {k: v for k, v in esc.meteo.items() if esc.nodos.get(k, {}).get("es_camara")}
            nm, modo = {"meteo": f"no se pudo consultar Open-Meteo ({exc}); se usa el clima cargado"}, esc.modo_meteo
        try:
            av, na = aves(esc, fecha)
        except Exception as exc:
            av, na = list(esc.aves), {"ebird": f"no se pudo consultar eBird ({exc}); se usan los avistamientos cargados"}
        pasado = pasado and not any(k.startswith("no se pudo") for k in (nf.get("firms", ""), nm.get("meteo", ""), na.get("ebird", "")))
        doc = {"fecha": fecha.isoformat(), "modo_meteo": modo, "focos": f,
               "meteo": {str(k): v for k, v in mt.items()},
               "aves": [{**a, "fecha_obs": a["fecha_obs"].isoformat() if a.get("fecha_obs") else None} for a in av],
               "fuentes": {**nf, **nm, **na}}
        if pasado:
            ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def aplicar(esc, fecha_txt: str, doc: dict | None = None):
    doc = doc or cargar(esc, fecha_txt)
    nuevo = esc.copia_amenazas(
        focos=doc["focos"], aves=[{**a, "fecha_obs": grafo.fecha(a.get("fecha_obs"))} for a in doc["aves"]],
        meteo={int(k): v for k, v in doc["meteo"].items()}, fecha=doc["fecha"], modo_meteo=doc["modo_meteo"])
    grafo.completar_meteo_bases(nuevo)
    nuevo.fuentes_escenario = doc.get("fuentes", {})
    return nuevo
