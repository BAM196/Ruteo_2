import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
SALIDA = AQUI / "metadata_gee.json"
MODO = os.getenv("GEE_MODO", "auto").lower()

CLASES = {
    10: ("Tree cover", "Cobertura arbórea"),
    20: ("Shrubland", "Matorral"),
    30: ("Grassland", "Pastizal"),
    40: ("Cropland", "Cultivo"),
    50: ("Built-up", "Zona construida"),
    60: ("Bare / sparse vegetation", "Suelo desnudo o vegetación escasa"),
    70: ("Snow and ice", "Nieve y hielo"),
    80: ("Permanent water bodies", "Cuerpo de agua permanente"),
    90: ("Herbaceous wetland", "Humedal herbáceo"),
    95: ("Mangroves", "Manglar"),
    100: ("Moss and lichen", "Musgo y liquen"),
}

OBJETIVO = tuple(
    s.strip() for s in os.getenv(
        "ESPECIES_OBJETIVO",
        "Pudu puda,Leopardus guigna,Puma concolor,Lycalopex culpaeus,Galictis cuja",
    ).split(",") if s.strip()
)
INVASORAS = (
    "Neovison vison", "Lepus europaeus", "Canis lupus familiaris", "Bos taurus",
)
COG_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def cargar_nodos() -> list[dict]:
    if not NODOS_PATH.exists():
        sys.exit(f"No existe {NODOS_PATH}. Primero corre Infraestructura/generar_nodos_v2.py.")
    data = json.loads(NODOS_PATH.read_text(encoding="utf-8"))
    nodos = data["nodos"] if isinstance(data, dict) else data
    if not nodos:
        sys.exit("nodosv2.json no trae nodos.")
    return nodos


def _empieza(nombre: str, lista: tuple[str, ...]) -> bool:
    return any(nombre.startswith(b) for b in lista)


def tile_worldcover(lat: float, lon: float) -> str:
    """El manual v200 nombra el tile por su esquina inferior izquierda, cada 3°."""
    lat_ll = math.floor(lat / 3.0) * 3
    lon_ll = math.floor(lon / 3.0) * 3
    ns = "N" if lat_ll >= 0 else "S"
    ew = "E" if lon_ll >= 0 else "W"
    return f"{ns}{abs(int(lat_ll)):02d}{ew}{abs(int(lon_ll)):03d}"


def hay_credenciales_gee() -> bool:
    if os.getenv("EARTHENGINE_PROJECT") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    cred = Path.home() / ".config" / "earthengine" / "credentials"
    return cred.exists()


def muestrear_gee(nodos: list[dict]) -> dict[int, int]:
    try:
        import ee
    except ImportError:
        sys.exit("Falta earthengine-api. Instálalo o usa GEE_MODO=cog.")
    project = os.getenv("EARTHENGINE_PROJECT")
    if project:
        ee.Initialize(project=project)
    else:
        ee.Initialize()
    imagen = ee.Image("ESA/WorldCover/v200/2021").select("Map")
    fc = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([n["lon"], n["lat"]]), {"nodo_id": int(n["id"])})
        for n in nodos
    ])
    muestreo = imagen.sampleRegions(collection=fc, scale=10, geometries=False)
    salida = {}
    for feat in muestreo.getInfo()["features"]:
        props = feat["properties"]
        valor = props.get("Map")
        if valor is not None:
            salida[int(props["nodo_id"])] = int(valor)
    return salida


def muestrear_cog(nodos: list[dict]) -> dict[int, int]:
    import rasterio

    por_tile: dict[str, list[dict]] = {}
    for n in nodos:
        por_tile.setdefault(tile_worldcover(n["lat"], n["lon"]), []).append(n)

    salida = {}
    gdal_env = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_TIMEOUT": "60",
    }
    with rasterio.Env(**gdal_env):
        for tile, grupo in por_tile.items():
            url = COG_URL.format(tile=tile)
            print(f"Leyendo tile {tile} ({len(grupo)} nodos)...")
            with rasterio.open(url) as src:
                coords = [(n["lon"], n["lat"]) for n in grupo]
                for n, muestra in zip(grupo, src.sample(coords)):
                    valor = int(muestra[0])
                    if valor != 0:
                        salida[int(n["id"])] = valor
    return salida


def resumir(registros: list[dict]) -> dict:
    resumen: dict[str, dict] = {}
    for r in registros:
        clave = str(r["landcover_code"]) if r["landcover_code"] is not None else "sin_dato"
        bloque = resumen.setdefault(clave, {
            "clase": r["landcover_clase"],
            "clase_es": r["landcover_clase_es"],
            "n_nodos": 0,
            "especies": {},
        })
        bloque["n_nodos"] += 1
        for sp in r["especies"]:
            acum = bloque["especies"].setdefault(sp["cientifico"], {
                "cientifico": sp["cientifico"],
                "comun": sp["comun"],
                "nodos": 0,
                "registros": 0,
            })
            acum["nodos"] += 1
            acum["registros"] += sp["registros"]
    for bloque in resumen.values():
        bloque["especies"] = sorted(
            bloque["especies"].values(), key=lambda e: (-e["registros"], e["cientifico"]),
        )
    return resumen


def clases_prioritarias(registros: list[dict]) -> list[int]:
    """La clase por defecto es la que concentra más cámaras con especie objetivo."""
    conteo: dict[int, int] = {}
    for r in registros:
        codigo = r["landcover_code"]
        if r["tiene_especie_objetivo"] and codigo is not None:
            conteo[codigo] = conteo.get(codigo, 0) + 1
    if not conteo:
        return [10, 20]
    mejor = max(conteo.values())
    return sorted(c for c, n in conteo.items() if n == mejor)


def main():
    nodos = cargar_nodos()
    if MODO == "gee":
        modo_usado = "gee"
        clases = muestrear_gee(nodos)
    elif MODO == "cog":
        modo_usado = "cog"
        clases = muestrear_cog(nodos)
    elif MODO == "auto":
        if hay_credenciales_gee():
            modo_usado = "gee"
            clases = muestrear_gee(nodos)
        else:
            print("Sin credenciales de Earth Engine: se usa el COG público del mismo dataset.")
            modo_usado = "cog"
            clases = muestrear_cog(nodos)
    else:
        sys.exit("GEE_MODO debe ser auto, gee o cog.")

    registros = []
    for n in nodos:
        codigo = clases.get(int(n["id"]))
        nombre_en, nombre_es = CLASES.get(codigo, ("Sin dato", "Sin dato"))
        especies = n.get("especies", [])
        registros.append({
            "nodo_id": n["id"],
            "nombre": n.get("nombre"),
            "lat": n["lat"],
            "lon": n["lon"],
            "codigos_estacion": n.get("codigos_estacion", []),
            "landcover_code": codigo,
            "landcover_clase": nombre_en,
            "landcover_clase_es": nombre_es,
            "especies": especies,
            "tiene_especie_objetivo": any(_empieza(e["cientifico"], OBJETIVO) for e in especies),
            "tiene_especie_invasora": any(_empieza(e["cientifico"], INVASORAS) for e in especies),
            "nota_pixel": (
                "Pixel de agua permanente. En un parque de fiordos el pixel de 10 m "
                "puede caer en el canal aunque la camara este en la orilla."
                if codigo == 80 else None
            ),
        })

    prioritarias = clases_prioritarias(registros)
    for r in registros:
        r["clase_prioritaria_default"] = r["landcover_code"] in prioritarias
        r["preferencia_default"] = (
            "priorizar" if r["clase_prioritaria_default"] else "sin_prioridad"
        )
        r["restriccion_default"] = None

    conteo = {}
    for r in registros:
        conteo[r["landcover_clase_es"]] = conteo.get(r["landcover_clase_es"], 0) + 1
    print("Nodos por clase:", conteo)
    print("Clases con especie objetivo:", prioritarias)

    documento = {
        "meta": {
            "fuente": "ESA WorldCover 10 m 2021 v200",
            "dataset_gee": "ESA/WorldCover/v200/2021",
            "banda": "Map",
            "modo_extraccion": modo_usado,
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nodos_origen": ruta_repo(NODOS_PATH),
            "cita": (
                "Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200. "
                "https://doi.org/10.5281/zenodo.7254221"
            ),
            "especies_objetivo": list(OBJETIVO),
            "especies_invasoras": list(INVASORAS),
            "clases_prioritarias_default": prioritarias,
            "preferencias_default": (
                "Si el usuario no indica un hábitat, no se bloquea ninguna clase. "
                "Se prioriza solo la clase que concentra más cámaras con especie "
                "objetivo. El resto queda visitable, con preferencia sin_prioridad. "
                "El Dijkstra de la fase 2 ignora esta marca y usa solo costo_km."
            ),
            "ejemplo_restriccion_usuario": (
                "Si el usuario pide solo cobertura arbórea, los nodos con "
                "landcover_code distinto de 10 pasan a restriccion = 'excluir'. "
                "Eso es una preferencia simulada, no el comportamiento por defecto."
            ),
            "clases": {str(k): {"en": v[0], "es": v[1]} for k, v in CLASES.items()},
            "resumen_por_clase": resumir(registros),
        },
        "registros": registros,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito: {SALIDA}")


if __name__ == "__main__":
    main()
