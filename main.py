import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_URL = "http://127.0.0.1:8000"

STEPS = (
    (
        "Generando nodos y aristas",
        [sys.executable, "Infraestructura/generar_nodos_v2.py"],
    ),
    ("Extrayendo cobertura de suelo", [sys.executable, "Metadata/extraer_gee.py"]),
    ("Extrayendo focos de incendio", [sys.executable, "Amenazas/extraer_firms.py"]),
    #("Extrayendo datos de animales", [sys.executable, "Metadata/extraer_fauna.py"]),
    ("Extrayendo rutas de sendero", [sys.executable, "Metadata/extraer_senderos.py"]),
    ("Extrayendo avistamiento de aves", [sys.executable, "Amenazas/extraer_ebird.py"]),
    ("Levantando la base y el sitio", ["docker", "compose", "up", "-d"]),
    (
        "Cargando infraestructura",
        [sys.executable, "Infraestructura/cargar_infraestructura.py"],
    ),
    ("Cargando cobertura de suelo", [sys.executable, "Metadata/cargar_gee.py"]),
    ("Cargando focos de incendio", [sys.executable, "Amenazas/cargar_firms.py"]),
    ("Cargando amenazas meteorológicas", [sys.executable, "Amenazas/cargar_meteo.py"]),
    #("Cargando datos de animales", [sys.executable, "Metadata/cargar_fauna.py"])
    ("Cargando cobertura de suelo", [sys.executable, "Metadata/cargar_senderos.py"]),
    ("Cargando focos de incendio", [sys.executable, "Amenazas/cargar_ebird.py"]),
)


def run_step(label, command):
    print(label)
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        print(f"Falló: {label}.")
        raise SystemExit(completed.returncode)


def main():
    for label, command in STEPS:
        run_step(label, command)
    print(f"Listo. El mapa está en {SITE_URL}.")


if __name__ == "__main__":
    main()
