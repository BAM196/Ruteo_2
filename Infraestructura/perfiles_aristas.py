import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from terreno import DEM, a_metrico, parametros, perfil

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
ARISTAS_PATH = Path(os.getenv("ARISTAS_PATH", AQUI / "aristasv2.json"))
DEM_PATH = Path(os.getenv("DEM_PATH", RAIZ / "data" / "dem_pumalin.tif"))
SALIDA = AQUI / "perfiles_aristas.json"


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def main():
    if not DEM_PATH.exists():
        sys.exit(f"No existe {DEM_PATH}. Corre Metadata/extraer_dem.py primero.")
    aristas = json.loads(ARISTAS_PATH.read_text(encoding="utf-8"))["aristas"]
    p = parametros()
    dem = DEM(DEM_PATH, p["paso"])

    perfiles = []
    for a in aristas:
        lon, lat = zip(*[(c[0], c[1]) for c in a["coordenadas"]])
        x, y = a_metrico(list(lon), list(lat))
        r = dem_perfil(dem, np.column_stack([x, y]), p)
        perfiles.append({"arista_id": a["id"], "source": a["source"], "target": a["target"], **r})

    bloqueadas = [x for x in perfiles if x["bloqueada"]]
    densificadas = [x for x in perfiles if x.get("densificada")]
    documento = {
        "meta": {
            "fuente": "Copernicus DEM GLO-30 sobre las aristas de aristasv2.json",
            "dem": ruta_repo(DEM_PATH),
            "aristas_origen": ruta_repo(ARISTAS_PATH),
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "altura_vuelo_m": p["altura"],
            "techo_m": p["techo"],
            "despeje_minimo_m": round(p["c_min"], 2),
            "regla_despeje": "c_min = error del DEM (4 m) + error vertical del dron (0,5 m) + margen por árboles (20 m)",
            "paso_muestreo_m": p["paso"],
            "regla_densificacion": (
                "Los extremos se vuelan a 80 m sobre la superficie. Si la recta entre dos puntos pasa "
                "a menos de c_min sobre la superficie o a más del techo, se agrega un punto intermedio "
                "a 80 m sobre la superficie; se usan los menos puntos posibles."
            ),
            "regla_bloqueo": (
                "La arista se bloquea si en un solo paso del perfil el desnivel supera techo − c_min: "
                "mantener el despeje mínimo exigiría volar sobre el techo legal."
            ),
            "n_aristas": len(perfiles),
            "n_densificadas": len(densificadas),
            "n_bloqueadas": len(bloqueadas),
        },
        "perfiles": perfiles,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Perfiles: {len(perfiles)} aristas, {len(densificadas)} densificadas, "
          f"{len(bloqueadas)} bloqueadas por altura. Escrito: {ruta_repo(SALIDA)}")


def dem_perfil(dem, coords_xy, p):
    r = perfil(dem, coords_xy, p)
    r.pop("muestras_xy", None)
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()}


if __name__ == "__main__":
    main()
