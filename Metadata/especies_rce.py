import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yaml

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
NODOS_PATH = Path(os.getenv("NODOS_PATH", RAIZ / "Infraestructura" / "nodosv2.json"))
FICHAS = AQUI / "fichas_especies.yaml"
MISION = RAIZ / "Motor" / "config" / "mision.yaml"
SALIDA = AQUI / "especies_rce.json"
URL = os.getenv(
    "RCE_XLSX_URL",
    "https://clasificacionespecies.mma.gob.cl/wp-content/uploads/2026/10/"
    "NominaDeEspecies_SegunEstadoConservacion-Chile_actualizado_20mProcesoRCE_20octubre2026.xlsx",
)
XLSX = Path(os.getenv("RCE_XLSX_PATH", RAIZ / "data" / "rce_nomina.xlsx"))
REGION = "X"
COLUMNA_REGION = "De Los Lagos"
ORDEN_REGIONES = ["XV", "I", "II", "III", "IV", "V", "XIII", "VI", "VII", "XVI", "VIII",
                  "IX", "XIV", "X", "XI", "XII"]
NOMBRES = {
    "Pudu pudu": "Pudú", "Leopardus guigna": "Güiña", "Puma concolor": "Puma",
    "Lycalopex culpaeus": "Zorro culpeo", "Galictis cuja": "Quique",
}


def ruta_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(RAIZ).as_posix()
    except ValueError:
        return str(path)


def descargar():
    if XLSX.exists():
        return
    print("Descargando la nómina RCE del Ministerio del Medio Ambiente")
    resp = requests.get(URL, timeout=120)
    if resp.status_code != 200 or not resp.content.startswith(b"PK"):
        sys.exit(f"No se pudo descargar la nómina RCE ({resp.status_code}). Bájala desde "
                 f"https://clasificacionespecies.mma.gob.cl/ y guárdala en {ruta_repo(XLSX)}.")
    XLSX.parent.mkdir(parents=True, exist_ok=True)
    XLSX.write_bytes(resp.content)


def binomio(nombre: str) -> str:
    partes = str(nombre).replace("(", " ").split()
    if len(partes) > 2 and partes[2].isalpha() and partes[2].islower():
        return " ".join(partes[:3])
    return " ".join(partes[:2])


def columna(df, prefijo: str) -> str:
    for c in df.columns:
        if str(c).replace("\n", " ").strip().upper().startswith(prefijo.upper()):
            return c
    raise KeyError(prefijo)


def en_rango(rango: str, region: str) -> bool:
    partes = [r.strip() for r in rango.split("-")]
    if len(partes) == 1:
        return partes[0] == region
    try:
        a, b = ORDEN_REGIONES.index(partes[0]), ORDEN_REGIONES.index(partes[1])
    except ValueError:
        return False
    k = ORDEN_REGIONES.index(region)
    return min(a, b) <= k <= max(a, b)


def categoria_region(texto: str, region: str = REGION) -> str:
    texto = str(texto).strip()
    if "[" in texto:
        for cat, quien in re.findall(r"([A-Z]{2})\s*\[([^\]]+)\]", texto):
            if "resto" in quien.lower():
                return cat
    zonas = re.findall(r"([A-Z]{2})\s*\(([^)]+)\)", texto)
    if zonas:
        for cat, rango in zonas:
            if en_rango(rango, region):
                return cat
    m = re.match(r"^([A-Z]{2})\b", texto)
    return m.group(1) if m else texto


def main():
    descargar()
    df = pd.read_excel(XLSX, sheet_name="Especies")
    c_cient = columna(df, "NOMBRE CIENTÍFICO")
    c_comun = columna(df, "NOMBRE COMÚN")
    c_sinon = columna(df, "SINONIMIA")
    c_cat = columna(df, "CATEGORÍA VIGENTE")
    c_dec = columna(df, "REFERENCIA o DECRETO")
    c_proc = columna(df, "NÚMERO PROCESO")
    ayuda = pd.read_excel(XLSX, sheet_name="Ayuda", header=None).iloc[0, 0]

    nodos = json.loads(NODOS_PATH.read_text(encoding="utf-8"))["nodos"]
    fichas = yaml.safe_load(FICHAS.read_text(encoding="utf-8"))
    pesos_rli = yaml.safe_load(MISION.read_text(encoding="utf-8"))["prioridad"]["peso_rli"]["valor"]

    registros, camaras = {}, {}
    for n in nodos:
        for sp in n.get("especies", []):
            b = binomio(sp["cientifico"])
            registros[b] = registros.get(b, 0) + sp["registros"]
            camaras.setdefault(b, set()).add(n["id"])

    especies = []
    for b in sorted(registros, key=lambda k: -registros[k]):
        fila = df[df[c_cient].astype(str).str.strip() == b]
        if fila.empty:
            fila = df[df[c_sinon].astype(str).str.contains(rf"\b{re.escape(b)}\b", regex=True, na=False)]
        ficha = fichas.get(b, {})
        item = {
            "cientifico": b,
            "comun": ficha.get("comun") or b,
            "registros": registros[b],
            "camaras": len(camaras[b]),
            "origen": ficha.get("origen", "sin dato"),
        }
        if not fila.empty:
            f = fila.iloc[0]
            cat_texto = str(f[c_cat]).strip()
            cat = categoria_region(cat_texto)
            presente = int(f.get(COLUMNA_REGION, 0) or 0) == 1
            item.update({
                "nombre_rce": str(f[c_cient]).strip(),
                "comun_rce": str(f[c_comun]).strip(),
                "categoria_vigente": cat_texto,
                "categoria_los_lagos": cat,
                "presente_en_los_lagos": presente,
                "decreto": " ".join(str(f[c_dec]).split()),
                "proceso_rce": None if pd.isna(f[c_proc]) else str(f[c_proc]),
                "peso_rli": pesos_rli.get(cat),
                "peso_w": None if pesos_rli.get(cat) is None else 1 + pesos_rli[cat],
                "objetivo": cat in ("VU", "NT", "EN", "CR"),
            })
            if item["origen"] == "sin dato":
                item["origen"] = "nativa"
        else:
            item.update({"nombre_rce": None, "categoria_vigente": None, "categoria_los_lagos": None,
                         "decreto": None, "peso_rli": None, "peso_w": None, "objetivo": False,
                         "nota": "No figura en la nómina RCE: no es una especie nativa clasificada."})
        item["presion"] = item["origen"] in ("doméstica", "exótica", "exótica invasora")
        for k in ("amenazas", "comportamiento"):
            if k in ficha:
                item[k] = ficha[k]
        if "presion" in ficha:
            item["como_presiona"] = ficha["presion"]
        especies.append(item)

    documento = {
        "meta": {
            "fuente": "Ministerio del Medio Ambiente, Nómina de especies según estado de conservación (RCE)",
            "version": " ".join(str(ayuda).split()),
            "url": URL,
            "archivo_local": ruta_repo(XLSX),
            "region": "Los Lagos (X)",
            "regla_categoria": (
                "Se usa la categoría vigente en la Región de Los Lagos: si la nómina da categorías por "
                "zona, se toma la del rango que incluye la región X; si las da por subespecie, la del resto."
            ),
            "regla_peso": "w = 1 + peso del Red List Index (LC 0, NT 1, VU 2, EN 3, CR 4), Butchart et al. (2007)",
            "regla_objetivo": "Especie objetivo: nativa con categoría VU, NT, EN o CR en Los Lagos",
            "regla_presion": "Especies domésticas o exóticas registradas por las cámaras: presionan a las nativas",
            "nota_uicn": (
                "La UICN bajó a la güiña a Preocupación menor en octubre de 2025; en Chile rige la "
                "categoría RCE, que en Los Lagos es Casi amenazada (NT)."
            ),
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nodos_origen": ruta_repo(NODOS_PATH),
            "n_especies": len(especies),
        },
        "especies": especies,
    }
    SALIDA.write_text(json.dumps(documento, ensure_ascii=False, indent=2), encoding="utf-8")
    for e in especies:
        print(f"  {e['comun']:<16} {e.get('categoria_los_lagos') or '—':<3} w={e.get('peso_w') or '—'} "
              f"{e['origen']:<17} {e['registros']:>5} registros en {e['camaras']} cámaras")
    print(f"Escrito: {ruta_repo(SALIDA)}")


if __name__ == "__main__":
    main()
