from ..config import parametros_mision


def reserva_s(m: dict | None = None) -> float:
    return (m or parametros_mision())["t_res_s"]


def tiempo_util_s(m: dict | None = None) -> float:
    return (m or parametros_mision())["t_util_s"]


def tiempo_vuelo_s(tiempos_tramos: list, n_camaras: int, m: dict | None = None) -> float:
    m = m or parametros_mision()
    return sum(tiempos_tramos) + m["s_i"] * n_camaras


def cabe(tiempos_tramos: list, n_camaras: int, m: dict | None = None) -> bool:
    m = m or parametros_mision()
    return tiempo_vuelo_s(tiempos_tramos, n_camaras, m) <= m["t_util_s"] + 1e-9


def tiempo_tramo_s(distancia_m: float, ascenso_m: float, m: dict | None = None) -> float:
    m = m or parametros_mision()
    return distancia_m / m["v_c"] + ascenso_m / m["v_sub"]


def tiempo_sector_s(tiempos_vuelos: list, m: dict | None = None) -> float:
    m = m or parametros_mision()
    return sum(tiempos_vuelos) + m["t_cambio_s"] * max(0, len(tiempos_vuelos) - 1)


def resumen(m: dict | None = None) -> dict:
    m = m or parametros_mision()
    return {
        "bateria_s": m["t_bat_s"],
        "reserva_s": round(m["t_res_s"], 1),
        "util_s": round(m["t_util_s"], 1),
        "regla_reserva": "t_res = R_op / (v_max − viento límite) + t_aterrizaje: el peor regreso desde el borde del radio",
        "muestreo_por_camara_s": m["s_i"],
        "velocidad_crucero_ms": m["v_c"],
        "velocidad_ascenso_ms": m["v_sub"],
        "cambio_bateria_s": m["t_cambio_s"],
    }
