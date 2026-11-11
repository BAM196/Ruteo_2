import argparse
import copy
import csv
import itertools
import json
import random
import statistics as st
from pathlib import Path

from . import grafo, servicio
from .config import MOTOR, RESULTADOS, aco_cfg, fuente_por_defecto
from .rutas import aco, dijkstra_distancia, milp

CORRIDAS = 30


def _csv(path: Path, filas: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def tabla_rutas(res: dict) -> list[dict]:
    filas = []
    for r in res["rutas"]:
        filas.append({
            "tecnica": r["tecnica"], "etiqueta": r["etiqueta"],
            "nodos": "-".join(map(str, r["nodos"])),
            "distancia_m": r["distancia_m"],
            "R_analitico": None if r["R"] is None else round(r["R"], 6),
            "R_montecarlo": None if r["R_montecarlo"] is None else round(r["R_montecarlo"], 6),
            "ic95_inf": None if r["ic95"] is None else round(r["ic95"][0], 6),
            "ic95_sup": None if r["ic95"] is None else round(r["ic95"][1], 6),
            "delta_R": None if r["delta_R"] is None else round(r["delta_R"], 6),
            "costo_C": None if r["costo"] is None else round(r["costo"], 6),
            "tiempo_ms": r["tiempo_ms"], "factible": r["factible"], "mensaje": r["mensaje"],
            "mas_resiliente": r["tecnica"] == res["mas_resiliente"],
        })
    return filas


def corridas_aco(prob, c_opt: float) -> tuple[list, list, dict]:
    filas, resumen, curvas = [], [], {}
    for nombre in ("config_mai", "config_zhang"):
        costos, tiempos, curvas[nombre] = [], [], []
        for s in range(CORRIDAS):
            r = aco.resolver(prob, config=nombre, semilla=s)
            gap = (r["costo"] - c_opt) / c_opt * 100 if r["costo"] is not None else None
            filas.append({"config": nombre, "semilla": s, "costo_C": r["costo"], "gap_pct": gap,
                          "distancia_m": r["distancia_m"], "factible": r["factible"],
                          "nodos": "-".join(map(str, r["nodos"])), "tiempo_ms": r["tiempo_ms"],
                          "iteraciones": r["extra"]["iteraciones_corridas"]})
            if r["costo"] is not None:
                costos.append(r["costo"])
            tiempos.append(r["tiempo_ms"])
            curvas[nombre].append(r["extra"]["convergencia"])
        mejor, prom = min(costos), st.mean(costos)
        resumen.append({
            "config": nombre, "corridas": CORRIDAS, "C_optimo_milp": c_opt,
            "C_mejor": mejor, "C_promedio": prom, "C_desv": st.pstdev(costos),
            "gap_mejor_pct": (mejor - c_opt) / c_opt * 100,
            "gap_promedio_pct": (prom - c_opt) / c_opt * 100,
            "aciertos_optimo": sum(abs(c - c_opt) < 1e-9 for c in costos),
            "tiempo_ms_promedio": st.mean(tiempos), "tiempo_ms_desv": st.pstdev(tiempos),
        })
    return filas, resumen, curvas


def sensibilidad(prob, c_opt: float) -> list[dict]:
    cfg = aco_cfg()["sensibilidad"]
    filas = []
    for a, b, rho, h, q0i in itertools.product(cfg["alpha"], cfg["beta"], cfg["rho"], cfg["hormigas"],
                                               cfg.get("q0_inicial", [0.9])):
        costos, tiempos = [], []
        for s in range(cfg["semillas"]):
            r = aco.resolver(prob, config=cfg["base"], semilla=s,
                             params={"alpha": a, "beta": b, "rho": rho, "hormigas": h,
                                     "q0_inicial": q0i, "iteraciones": cfg["iteraciones"]})
            costos.append(r["costo"])
            tiempos.append(r["tiempo_ms"])
        prom = st.mean(costos)
        filas.append({"alpha": a, "beta": b, "rho": rho, "hormigas": h, "q0_inicial": q0i,
                      "iteraciones": cfg["iteraciones"], "semillas": cfg["semillas"],
                      "C_promedio": prom, "gap_promedio_pct": (prom - c_opt) / c_opt * 100,
                      "tiempo_ms_promedio": st.mean(tiempos)})
    return filas


def banco(esc, instancias: int = 12, semillas: int = 5) -> tuple[list, list]:
    rng = random.Random(1)
    ids, aids = sorted(esc.nodos), sorted(esc.aristas)
    casos = []
    for _ in range(instancias):
        s, t = rng.sample(ids, 2)
        ov = {str(a): round(rng.uniform(0.2, 0.9), 2) for a in rng.sample(aids, 15)}
        casos.append({"origen_id": s, "destino_id": t, "theta": 0.5, "autonomia_m": 60_000,
                      "overrides_prob": {"aristas": ov}})
    filas = []
    for k, c in enumerate(casos):
        prob, _ = servicio.preparar(c, esc)
        dijkstra_distancia.resolver(prob)
        m = milp.resolver(prob)
        for nombre in ("config_mai", "config_zhang"):
            for ls in (0, 10):
                for sem in range(semillas):
                    r = aco.resolver(prob, config=nombre, semilla=sem, params={"pasos_busqueda_local": ls})
                    ok = m["costo"] is not None and r["costo"] is not None and r["factible"]
                    filas.append({
                        "instancia": k, "origen": c["origen_id"], "destino": c["destino_id"],
                        "config": nombre, "busqueda_local": ls, "semilla": sem,
                        "milp_factible": m["factible"], "C_optimo": m["costo"],
                        "aco_factible": r["factible"], "C_aco": r["costo"],
                        "gap_pct": (r["costo"] - m["costo"]) / m["costo"] * 100 if ok else None,
                        "tiempo_aco_ms": r["tiempo_ms"], "tiempo_milp_ms": m["tiempo_ms"],
                    })
    resumen = []
    for nombre in ("config_mai", "config_zhang"):
        for ls in (0, 10):
            sub = [f for f in filas if f["config"] == nombre and f["busqueda_local"] == ls
                   and f["milp_factible"]]
            gaps = [f["gap_pct"] for f in sub if f["gap_pct"] is not None]
            resumen.append({
                "config": nombre, "busqueda_local": ls, "corridas": len(sub),
                "aco_sin_ruta_factible": sum(1 for f in sub if f["gap_pct"] is None),
                "gap_promedio_pct": st.mean(gaps) if gaps else None,
                "gap_max_pct": max(gaps) if gaps else None,
                "optimos": sum(1 for g in gaps if g < 1e-7),
                "tiempo_aco_ms_prom": st.mean(f["tiempo_aco_ms"] for f in sub),
                "tiempo_milp_ms_prom": st.mean(f["tiempo_milp_ms"] for f in sub),
            })
    return filas, resumen


def convergencia(curvas: dict, carpeta: Path):
    filas, series = [], {}
    for nombre, cs in curvas.items():
        largo = max(len(c) for c in cs)
        prom, desv = [], []
        for i in range(largo):
            vals = [(c[i] if i < len(c) else c[-1]) for c in cs]
            vals = [v for v in vals if v is not None]
            prom.append(st.mean(vals))
            desv.append(st.pstdev(vals))
            filas.append({"config": nombre, "iteracion": i + 1, "f_promedio": prom[-1], "f_desv": desv[-1]})
        series[nombre] = (prom, desv)
    _csv(carpeta / "aco_convergencia.csv", filas)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    for (nombre, (prom, desv)), color in zip(series.items(), ("#1f6f8b", "#c8553d")):
        x = range(1, len(prom) + 1)
        ax.plot(x, prom, color=color, label=nombre)
        ax.fill_between(x, [p - d for p, d in zip(prom, desv)], [p + d for p, d in zip(prom, desv)],
                        color=color, alpha=0.2)
    ax.set_xscale("log")
    ax.set_xlabel("Iteración")
    ax.set_ylabel("Mejor f (promedio de 30 corridas)")
    ax.set_title("Convergencia del ACO")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(carpeta / "aco_convergencia.png", dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Evaluación de las 4 técnicas y del ACO.")
    ap.add_argument("--fuente", choices=["db", "json"], default=None)
    ap.add_argument("--consulta", default=str(MOTOR / "config" / "consulta_ejemplo.json"))
    ap.add_argument("--sin-sensibilidad", action="store_true")
    args = ap.parse_args()

    RESULTADOS.mkdir(exist_ok=True)
    esc = grafo.cargar(args.fuente or fuente_por_defecto())
    consulta = json.loads(Path(args.consulta).read_text(encoding="utf-8"))

    res = servicio.calcular_rutas(consulta, esc)
    (RESULTADOS / "ejemplo_rutas.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _csv(RESULTADOS / "tabla_rutas.csv", tabla_rutas(res))
    print(f"Más resiliente: {res['mas_resiliente']}")
    for r in res["rutas"]:
        print("  " + r["leyenda"])

    c2 = copy.deepcopy(consulta)
    c2["autonomia_m"] = 7000
    res2 = servicio.calcular_rutas(c2, esc)
    _csv(RESULTADOS / "tabla_rutas_autonomia.csv", tabla_rutas(res2))

    prob, _ = servicio.preparar(consulta, esc)
    dijkstra_distancia.resolver(prob)
    c_opt = milp.resolver(prob)["costo"]
    filas, resumen, curvas = corridas_aco(prob, c_opt)
    _csv(RESULTADOS / "aco_corridas.csv", filas)
    _csv(RESULTADOS / "aco_resumen.csv", resumen)
    convergencia(curvas, RESULTADOS)
    for r in resumen:
        print(f"  {r['config']}: brecha mejor {r['gap_mejor_pct']:.3f} %, promedio "
              f"{r['gap_promedio_pct']:.3f} %, {r['aciertos_optimo']}/{CORRIDAS} óptimos, "
              f"{r['tiempo_ms_promedio']:.1f} ms")
    filas_b, resumen_b = banco(esc)
    _csv(RESULTADOS / "aco_banco.csv", filas_b)
    _csv(RESULTADOS / "aco_banco_resumen.csv", resumen_b)
    for r in resumen_b:
        print(f"  banco {r['config']} (búsqueda local {r['busqueda_local']}): brecha promedio "
              f"{r['gap_promedio_pct']:.2f} %, máx {r['gap_max_pct']:.2f} %, "
              f"{r['optimos']}/{r['corridas']} óptimos, {r['aco_sin_ruta_factible']} sin ruta factible")
    if not args.sin_sensibilidad:
        _csv(RESULTADOS / "aco_sensibilidad.csv", sensibilidad(prob, c_opt))
    print(f"Resultados en {RESULTADOS}")


if __name__ == "__main__":
    main()
