import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

AQUI = Path(__file__).resolve().parent
EBIRD = AQUI / "amenaza_ebird.json"
TABLA = AQUI / "aves_desplazamiento.yaml"
SALIDA = AQUI / "aves_desplazamiento.json"


def main():
    tabla = yaml.safe_load(TABLA.read_text(encoding="utf-8"))
    provisional = float(tabla["provisional_km"]["valor"])
    datos = tabla["especies"]
    avist = json.loads(EBIRD.read_text(encoding="utf-8")).get("avistamientos", []) if EBIRD.exists() else []
    registros = Counter(a["cientifico"] for a in avist)
    nombres = {a["cientifico"]: a.get("comun") for a in avist}

    filas, suma, peso = [], 0.0, 0
    for sp, n in registros.most_common():
        dato = datos.get(sp)
        km = float(dato["desplazamiento_km"]) if dato else provisional
        filas.append({"cientifico": sp, "comun": (dato or {}).get("comun") or nombres.get(sp),
                      "registros": n, "desplazamiento_km": km, "con_fuente": bool(dato),
                      "medida": (dato or {}).get("medida"), "fuente": (dato or {}).get("fuente")})
        suma += km * n
        peso += n
    r_mov_km = suma / peso if peso else provisional
    documento = {
        "meta": {
            "regla": "r_mov = Σ (desplazamiento_e · registros_e) / Σ registros_e sobre las aves que eBird registra en el parque",
            "fuente_registros": EBIRD.name,
            "tabla": TABLA.name,
            "provisional_km": provisional,
            "n_especies": len(filas),
            "n_con_fuente": sum(1 for f in filas if f["con_fuente"]),
            "n_registros": peso,
            "r_mov_km": round(r_mov_km, 3),
            "r_mov_m": round(r_mov_km * 1000),
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "especies": filas,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"r_mov = {r_mov_km:.2f} km con {peso} registros de {len(filas)} especies "
          f"({documento['meta']['n_con_fuente']} con dato publicado). Escrito: {SALIDA.name}")


if __name__ == "__main__":
    main()
