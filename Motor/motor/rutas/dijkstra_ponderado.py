import time

from .comun import ProblemaSector, resultado, vecino_mas_cercano

TECNICA, ETIQUETA = "dijkstra_ponderado", "pgr_dijkstra (ponderado)"


def resolver(prob: ProblemaSector, conn=None) -> dict:
    t0 = time.perf_counter()
    tramos = prob.tramos_modelo or prob.calcular_tramos("modelo", conn)
    viables, motivos = prob.viables(tramos)
    vuelos = vecino_mas_cercano(prob, tramos, viables, con_clima=True)
    ms = (time.perf_counter() - t0) * 1000
    return resultado(prob, TECNICA, ETIQUETA, vuelos, tramos, ms, no_viables=motivos,
                     extra={"motor": prob.motor_tramos, "orden": "vecino más cercano por costo del modelo",
                            "cierre": "vuelve a la base cuando la siguiente cámara no cabe en la batería"})
