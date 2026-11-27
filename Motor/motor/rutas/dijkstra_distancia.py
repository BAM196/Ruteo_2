import time

from .comun import ProblemaSector, resultado, vecino_mas_cercano

TECNICA, ETIQUETA = "dijkstra_distancia", "pgr_dijkstra (distancia)"


def resolver(prob: ProblemaSector, conn=None) -> dict:
    t0 = time.perf_counter()
    tramos = prob.calcular_tramos("distancia", conn)
    viables, motivos = prob.viables(tramos)
    vuelos = vecino_mas_cercano(prob, tramos, viables)
    ms = (time.perf_counter() - t0) * 1000
    traslado = sum(prob.tramos_dist[(a, b)].tiempo
                   for seq in vuelos for a, b in zip([prob.b] + seq, seq + [prob.b]) if (a, b) in tramos)
    prob.t_ref = traslado if traslado > 0 else max([t.tiempo for t in tramos.values()] + [1.0])
    return resultado(prob, TECNICA, ETIQUETA, vuelos, tramos, ms, no_viables=motivos,
                     extra={"motor": prob.motor_tramos, "orden": "vecino más cercano por distancia",
                            "cierre": "vuelve a la base cuando la siguiente cámara no cabe en la batería",
                            "t_ref_s": round(prob.t_ref, 2)})
