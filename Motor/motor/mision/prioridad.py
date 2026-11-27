def binomio(nombre: str) -> str:
    partes = str(nombre).replace("(", " ").split()
    if len(partes) > 2 and partes[2].isalpha() and partes[2].islower():
        return " ".join(partes[:3])
    return " ".join(partes[:2])


def especies_camara(esc, c: int) -> dict:
    return {binomio(sp["cientifico"]): sp["registros"] for sp in esc.nodos[c].get("especies", [])}


def componentes(esc, camaras: list, peso_rli: dict) -> dict:
    n = len(camaras) or 1
    presencia, registros = {}, {}
    exoticas = 0
    for c in camaras:
        sp = especies_camara(esc, c)
        hay_presion = False
        for e, r in sp.items():
            presencia[e] = presencia.get(e, 0) + 1
            registros[e] = registros.get(e, 0) + r
            info = esc.especies.get(e, {})
            if info.get("presion"):
                hay_presion = True
        exoticas += hay_presion
    V = 0.0
    for e, k in presencia.items():
        info = esc.especies.get(e, {})
        if info.get("origen") == "nativa" and info.get("peso_w") is not None:
            V += float(info["peso_w"]) * k / n
    P = exoticas / n
    return {"V": V, "P": P, "presencia": presencia, "registros": registros}


def etiqueta(esc, e: str) -> str:
    info = esc.especies.get(e, {})
    nombre = (info.get("comun") or e).lower()
    cat = info.get("categoria_los_lagos")
    return f"{nombre} ({cat})" if cat and info.get("objetivo") else nombre


def describir(esc, comp: dict) -> dict:
    reg = comp["registros"]
    predominan = sorted(reg, key=lambda e: -reg[e])[:2]
    objetivo = [e for e in sorted(reg, key=lambda e: -reg[e]) if esc.especies.get(e, {}).get("objetivo")]
    exoticas = [e for e in sorted(reg, key=lambda e: -reg[e]) if esc.especies.get(e, {}).get("presion")]
    return {
        "predominan": [(esc.especies.get(e, {}).get("comun") or e).lower() for e in predominan],
        "objetivo": [etiqueta(esc, e) for e in objetivo],
        "exoticas": [(esc.especies.get(e, {}).get("comun") or e).lower() for e in exoticas],
    }


def normalizar(sectores: list, peso_valor: float) -> None:
    vmax = max([s["valor_conservacion"] for s in sectores] + [1e-12])
    pmax = max([s["presion_exoticas"] for s in sectores] + [1e-12])
    for s in sectores:
        s["V_norm"] = s["valor_conservacion"] / vmax
        s["P_norm"] = s["presion_exoticas"] / pmax
        s["prioridad"] = round(100 * (peso_valor * s["V_norm"] + (1 - peso_valor) * s["P_norm"]), 1)


def subtitulo(s: dict) -> str:
    d = s["descripcion"]
    partes = [f"Sector {s['id']}", f"Prioridad {s['prioridad']:.0f} %"]
    if d["predominan"]:
        partes.append("Predominan: " + ", ".join(d["predominan"]))
    if d["objetivo"]:
        partes.append("Objetivo: " + ", ".join(d["objetivo"]))
    if d["exoticas"]:
        partes.append("Exóticas: " + ", ".join(d["exoticas"]))
    return " · ".join(partes)


def kendall_tau(a: list, b: list) -> float:
    pos_b = {x: i for i, x in enumerate(b)}
    n = len(a)
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (pos_b[a[i]] - pos_b[a[j]])
            if s > 0:
                disc += 1
            elif s < 0:
                conc += 1
    total = n * (n - 1) / 2
    return (conc - disc) / total if total else 1.0
