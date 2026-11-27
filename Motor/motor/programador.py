import argparse
import json
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from . import grafo
from .config import RESULTADOS, conectar, fuente_por_defecto, parametros_mision

ESTADOS_DIA = ("programada", "volada", "postergada", "por_reprogramar")


def dias_habiles_antes(fecha: date, n: int) -> date:
    d = fecha
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def temporada_de(fecha: date, m: dict) -> str:
    for nombre, meses in m["temporadas"].items():
        if fecha.month in meses:
            return nombre
    return "sin temporada"


def fin_temporada(fecha: date, m: dict) -> date:
    meses = m["temporadas"][temporada_de(fecha, m)]
    ultimo = meses[-1]
    anio = fecha.year + (1 if ultimo < fecha.month else 0)
    siguiente = date(anio + (ultimo == 12), ultimo % 12 + 1, 1)
    return siguiente - timedelta(days=1)


class AlmacenJSON:
    def __init__(self, ruta=RESULTADOS / "campanas.json"):
        self.ruta = ruta

    def _leer(self):
        if self.ruta.exists():
            return json.loads(self.ruta.read_text(encoding="utf-8"))
        return {"campanas": [], "dias": []}

    def _guardar(self, doc):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    def crear(self, campana, dias):
        doc = self._leer()
        cid = max([c["id"] for c in doc["campanas"]] + [0]) + 1
        campana["id"] = cid
        doc["campanas"].append(campana)
        did = max([d["id"] for d in doc["dias"]] + [0])
        for d in dias:
            did += 1
            doc["dias"].append({**d, "id": did, "campana_id": cid})
        self._guardar(doc)
        return cid

    def campanas(self):
        doc = self._leer()
        return [{**c, "dias": [d for d in doc["dias"] if d["campana_id"] == c["id"]]} for c in doc["campanas"]]

    def actualizar_dia(self, did, **campos):
        doc = self._leer()
        for d in doc["dias"]:
            if d["id"] == did:
                d.update(campos)
        self._guardar(doc)

    def actualizar_campana(self, cid, **campos):
        doc = self._leer()
        for c in doc["campanas"]:
            if c["id"] == cid:
                c.update(campos)
        self._guardar(doc)


class AlmacenBD:
    @contextmanager
    def _cur(self):
        conn = conectar()
        try:
            with conn, conn.cursor() as cur:
                yield cur
        finally:
            conn.close()

    def crear(self, campana, dias):
        from psycopg2.extras import Json

        with self._cur() as cur:
            cur.execute("""INSERT INTO campanas (nombre, tipo, modo, consulta, temporada, fecha_inicio, fecha_limite,
                           visitas_objetivo, estado, completa, motivo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           RETURNING id""",
                        (campana["nombre"], campana["tipo"], campana["modo"], Json(campana["consulta"]),
                         campana["temporada"], campana["fecha_inicio"], campana["fecha_limite"],
                         campana["visitas_objetivo"], campana["estado"], campana["completa"], campana.get("motivo")))
            cid = cur.fetchone()[0]
            for d in dias:
                cur.execute("INSERT INTO campana_dia (campana_id, visita, fecha, estado) VALUES (%s,%s,%s,%s)",
                            (cid, d["visita"], d["fecha"], d["estado"]))
        return cid

    def campanas(self):
        with self._cur() as cur:
            cur.execute("SELECT id, nombre, tipo, modo, consulta, temporada, fecha_inicio::text, fecha_limite::text, "
                        "visitas_objetivo, estado, completa, motivo FROM campanas ORDER BY fecha_inicio, id")
            cols = ["id", "nombre", "tipo", "modo", "consulta", "temporada", "fecha_inicio", "fecha_limite",
                    "visitas_objetivo", "estado", "completa", "motivo"]
            camps = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute("SELECT id, campana_id, visita, fecha::text, estado, decision, r_plan, plan IS NOT NULL "
                        "FROM campana_dia ORDER BY fecha, visita")
            dias = [dict(zip(["id", "campana_id", "visita", "fecha", "estado", "decision", "r_plan", "con_plan"], r))
                    for r in cur.fetchall()]
        return [{**c, "dias": [d for d in dias if d["campana_id"] == c["id"]]} for c in camps]

    def actualizar_dia(self, did, **campos):
        from psycopg2.extras import Json

        if not campos:
            return
        sets = ", ".join(f"{k} = %s" for k in campos) + ", actualizado = now()"
        vals = [Json(v) if k == "plan" else v for k, v in campos.items()]
        with self._cur() as cur:
            cur.execute(f"UPDATE campana_dia SET {sets} WHERE id = %s", (*vals, did))

    def actualizar_campana(self, cid, **campos):
        if not campos:
            return
        sets = ", ".join(f"{k} = %s" for k in campos)
        with self._cur() as cur:
            cur.execute(f"UPDATE campanas SET {sets} WHERE id = %s", (*campos.values(), cid))


def almacen():
    if fuente_por_defecto() == "db":
        try:
            conectar().close()
            return AlmacenBD()
        except Exception:
            pass
    return AlmacenJSON()


def nombre_campana(consulta: dict) -> str:
    modo = consulta.get("modo", "sector")
    if modo == "sector":
        return f"Sector {consulta.get('sector_id') or 'de mayor prioridad'}"
    if modo == "especie":
        return f"Especie {consulta.get('especie')}"
    if modo == "camaras":
        return "Cámaras " + ", ".join(map(str, consulta.get("camaras") or []))
    return "Todo el parque"


def crear(consulta: dict, fecha_inicio: str, nombre: str | None = None, tipo: str = "ronda",
          dias_disponibles: int | None = None, store=None) -> dict:
    m = parametros_mision()
    store = store or almacen()
    inicio = date.fromisoformat(fecha_inicio)
    visitas = m["visitas"]
    parcial = dias_disponibles is not None and dias_disponibles < visitas
    n = max(1, dias_disponibles) if parcial else visitas
    campana = {
        "nombre": nombre or nombre_campana(consulta),
        "tipo": tipo, "modo": consulta.get("modo", "sector"), "consulta": consulta,
        "temporada": temporada_de(inicio, m), "fecha_inicio": inicio.isoformat(),
        "fecha_limite": fin_temporada(inicio, m).isoformat(), "visitas_objetivo": n,
        "estado": "programada", "completa": False,
        "motivo": (f"Campaña parcial: {n} de {visitas} mañanas. No cuenta como completa y el sector pasa "
                   "primero a la siguiente ronda.") if parcial else None,
    }
    dias = [{"visita": k + 1, "fecha": (inicio + timedelta(days=k)).isoformat(), "estado": "programada"}
            for k in range(n)]
    cid = store.crear(campana, dias)
    return {**campana, "id": cid, "dias": dias,
            "plan_provisorio": dias_habiles_antes(inicio, m["anticipacion_dias_habiles"]).isoformat(),
            "avisos": [campana["motivo"]] if campana["motivo"] else []}


def _plan(consulta: dict, fecha: str, esc=None):
    from . import servicio

    return servicio.planificar({**consulta, "fecha": fecha}, esc or grafo.cargar(), n_mc=2000)


def decidir(campana: dict, dia: dict, store=None, esc=None) -> dict:
    m = parametros_mision()
    store = store or almacen()
    res = _plan(campana["consulta"], dia["fecha"], esc)
    mejor = next((p for p in res["planes"] if p["tecnica"] == res["mas_resiliente"]), None)
    r = mejor["R"] if mejor else None
    clima = max([v["p_clima"] for p in res["planes"] for v in p["vuelos"]] + [0.0])
    umbral = res["parametros"]["umbral_R"]
    coma = lambda x, d=3: f"{x:.{d}f}".replace(".", ",")
    if r is not None and r >= umbral and clima < 0.5:
        decision, estado = f"Volar: R del plan {coma(r)} ≥ {coma(umbral, 2)}", "programada"
    else:
        por_clima = any("clima" in str(m) for m in res["no_visitadas"].values())
        motivo = "clima fuera de los límites del dron" if (clima >= 0.5 or por_clima) else (
            f"R del plan {coma(r)} < {coma(umbral, 2)}" if r is not None else "no hay un plan factible")
        decision, estado = f"Postergar: {motivo}", "postergada"
    resumen = {"tecnica": res["mas_resiliente"], "leyendas": [p["leyenda"] for p in res["planes"]],
               "vuelos": [{"vuelo": v["vuelo"], "camaras": v["camaras"], "nodos": v["nodos"], "aristas": v["aristas"]}
                          for v in (mejor["vuelos"] if mejor else [])]}
    store.actualizar_dia(dia["id"], estado=estado, decision=decision, r_plan=r, plan=resumen)
    if estado == "postergada":
        reprogramar_desde(campana, dia, store, m)
    return {"dia": dia["id"], "fecha": dia["fecha"], "decision": decision, "R": r, "p_clima_max": clima}


def reprogramar_desde(campana: dict, dia: dict, store, m: dict):
    limite = date.fromisoformat(campana["fecha_limite"])
    siguientes = [d for d in campana["dias"] if d["visita"] >= dia["visita"] and d["estado"] != "volada"]
    for d in sorted(siguientes, key=lambda d: d["visita"]):
        nueva = date.fromisoformat(d["fecha"]) + timedelta(days=1)
        if nueva > limite:
            store.actualizar_dia(d["id"], estado="por_reprogramar", fecha=nueva.isoformat(),
                                 decision="La temporada terminó antes de completar las visitas")
            store.actualizar_campana(campana["id"], estado="incompleta", completa=False,
                                     motivo="Campaña incompleta: el sector pasa primero a la siguiente ronda.")
        else:
            store.actualizar_dia(d["id"], fecha=nueva.isoformat(),
                                 estado="postergada" if d["id"] == dia["id"] else d["estado"])


def reprogramar(campana_id: int, nueva_fecha: str, store=None) -> dict:
    store = store or almacen()
    camp = next(c for c in store.campanas() if c["id"] == campana_id)
    inicio = date.fromisoformat(nueva_fecha)
    pendientes = sorted([d for d in camp["dias"] if d["estado"] != "volada"], key=lambda d: d["visita"])
    for k, d in enumerate(pendientes):
        store.actualizar_dia(d["id"], fecha=(inicio + timedelta(days=k)).isoformat(), estado="programada")
    store.actualizar_campana(campana_id, estado="programada")
    return next(c for c in store.campanas() if c["id"] == campana_id)


def marcar_volada(campana_id: int, dia_id: int, store=None) -> dict:
    store = store or almacen()
    store.actualizar_dia(dia_id, estado="volada")
    camp = next(c for c in store.campanas() if c["id"] == campana_id)
    voladas = sum(1 for d in camp["dias"] if d["estado"] == "volada")
    if voladas >= parametros_mision()["visitas"]:
        store.actualizar_campana(campana_id, estado="completa", completa=True)
    elif voladas >= camp["visitas_objetivo"]:
        store.actualizar_campana(campana_id, estado="incompleta")
    return next(c for c in store.campanas() if c["id"] == campana_id)


def tareas(hoy: date | None = None, store=None) -> list:
    hoy = hoy or date.today()
    m = parametros_mision()
    store = store or almacen()
    salida = []
    for c in store.campanas():
        for d in c["dias"]:
            if d["estado"] not in ("programada", "postergada"):
                continue
            f = date.fromisoformat(d["fecha"])
            if dias_habiles_antes(f, m["anticipacion_dias_habiles"]) == hoy and d["visita"] == 1:
                salida.append(("provisorio", c, d))
            if f in (hoy, hoy + timedelta(days=1)) and not str(d.get("decision") or "").startswith(f"[{hoy}]"):
                salida.append(("decidir", c, d))
    return salida


def ejecutar_tareas(hoy: date | None = None, store=None) -> list:
    hoy = hoy or date.today()
    store = store or almacen()
    salida = []
    for tipo, c, d in tareas(hoy, store):
        try:
            if tipo == "provisorio":
                res = _plan(c["consulta"], d["fecha"])
                store.actualizar_dia(d["id"], decision=f"[{hoy}] Plan provisorio listo para la solicitud a la DGAC",
                                     r_plan=next((p["R"] for p in res["planes"] if p["tecnica"] == res["mas_resiliente"]), None))
                salida.append({"campana": c["id"], "dia": d["id"], "tarea": "plan provisorio"})
            else:
                r = decidir(c, d, store)
                store.actualizar_dia(d["id"], decision=f"[{hoy}] {r['decision']}")
                salida.append({"campana": c["id"], "dia": d["id"], "tarea": "decisión", **r})
        except Exception as exc:
            salida.append({"campana": c["id"], "dia": d["id"], "tarea": tipo, "error": str(exc)})
    return salida


def iniciar_en_segundo_plano(intervalo_s: int = 1800):
    def bucle():
        while True:
            try:
                ejecutar_tareas()
            except Exception:
                pass
            time.sleep(intervalo_s)

    hilo = threading.Thread(target=bucle, name="programador-campanas", daemon=True)
    hilo.start()
    return hilo


def main():
    ap = argparse.ArgumentParser(description="Campañas programadas: plan provisorio y decisión de volar o postergar.")
    ap.add_argument("--hoy", default=None, help="YYYY-MM-DD para simular otro día")
    args = ap.parse_args()
    hoy = date.fromisoformat(args.hoy) if args.hoy else date.today()
    for r in ejecutar_tareas(hoy):
        print(r)
    print(f"Tareas revisadas el {hoy} a las {datetime.now():%H:%M}.")


if __name__ == "__main__":
    main()
