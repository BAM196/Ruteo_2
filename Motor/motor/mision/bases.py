def sirve(base: dict, camaras) -> bool:
    return all(c in base["camaras"] and base["camaras"][c]["bloque_visible"] for c in camaras)


def candidatas(esc, camaras) -> list:
    return [b for b in esc.bases.values() if sirve(b, camaras)]


def suma_distancias(base: dict, camaras) -> float:
    return sum(base["camaras"][c]["distancia_m"] for c in camaras)


def elegir(esc, camaras, forzada: int | None = None) -> tuple[dict | None, str]:
    camaras = list(camaras)
    if forzada is not None:
        b = esc.bases.get(forzada)
        if b is None:
            return None, f"La base {forzada} no existe."
        if not sirve(b, camaras):
            fuera = [c for c in camaras if c not in b["camaras"] or not b["camaras"][c]["bloque_visible"]]
            return b, f"Desde la base elegida no se alcanzan o no se ven las cámaras {fuera}."
        return b, "elegida por el usuario"
    opciones = candidatas(esc, camaras)
    if not opciones:
        return None, "Ninguna base deja todas las cámaras dentro del radio y a la vista."
    mejor = min(opciones, key=lambda b: (suma_distancias(b, camaras), b["tipo"] != "camara", b["id"]))
    return mejor, "mínima suma de distancias a las cámaras"


def resumen(base: dict | None) -> dict | None:
    if base is None:
        return None
    return {"id": base["id"], "tipo": base["tipo"], "nombre": base.get("nombre"), "nodo": base["nodo"],
            "lon": base["lon"], "lat": base["lat"], "elevacion_m": base.get("elevacion_m")}
