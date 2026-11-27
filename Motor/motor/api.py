import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import capacidad, escenarios, exportar, grafo, probabilidades, programador, servicio
from .config import fuente_por_defecto, parametros_mision
from .mision import bateria, sectores as mod_sectores

_CACHE = {"t": 0.0, "esc": None}
TTL_S = 120


@asynccontextmanager
async def ciclo(app):
    if os.getenv("MOTOR_PROGRAMADOR", "1") == "1":
        programador.iniciar_en_segundo_plano()
    yield


app = FastAPI(title="WildWard: motor de misiones de monitoreo", version="2.0", lifespan=ciclo)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Restricciones(BaseModel):
    solo_bosque: bool = False
    evitar_senderos: bool = False
    evitar_clima: bool = False
    evitar_aves: bool = False
    excluir_nodos: list[int] = Field(default_factory=list)


class PlanIn(BaseModel):
    modo: str = "sector"
    sector_id: int | None = None
    especie: str | None = None
    camaras: list[int] = Field(default_factory=list)
    base_id: int | None = None
    fecha: str | None = None
    restricciones: Restricciones = Field(default_factory=Restricciones)
    theta: float = Field(0.5, ge=0, le=1)
    overrides_prob: dict = Field(default_factory=dict)
    focos_simulados: list[dict] = Field(default_factory=list)
    r_min: float | None = Field(None, gt=0, le=1)
    tecnicas: list[str] | None = None
    aco_config: str | None = None
    semilla: int = 0


class FallasIn(BaseModel):
    vuelos: list[dict] | None = None
    overrides_prob: dict = Field(default_factory=dict)
    semilla: int | None = None


class OverridesIn(BaseModel):
    overrides_prob: dict = Field(default_factory=dict)


class EscenarioIn(BaseModel):
    fecha: str


class KmlIn(BaseModel):
    plan: dict
    fecha: str | None = None


class CampanaIn(BaseModel):
    consulta: dict
    fecha_inicio: str
    nombre: str | None = None
    tipo: str = "ronda"
    dias_disponibles: int | None = None


class ReprogramarIn(BaseModel):
    fecha: str


def _escenario():
    ahora = time.time()
    if _CACHE["esc"] is None or ahora - _CACHE["t"] > TTL_S:
        try:
            grafo.limpiar_cache()
            _CACHE["esc"] = grafo.cargar(fuente_por_defecto(), os.getenv("MOTOR_GRAFO_JSON") or None)
            _CACHE["t"] = ahora
        except Exception as exc:
            raise HTTPException(503, f"No se pudo cargar la red: {exc}") from exc
    return _CACHE["esc"]


def _error(exc: Exception):
    raise HTTPException(400, str(exc)) from exc


@app.get("/health")
def health():
    estado = {"fuente": fuente_por_defecto()}
    try:
        estado.update(_escenario().resumen())
        estado["base"] = "ok"
    except HTTPException as exc:
        estado["base"] = exc.detail
    try:
        import gurobipy

        estado["gurobi"] = ".".join(map(str, gurobipy.gurobi.version()))
    except Exception as exc:
        estado["gurobi"] = f"no disponible: {exc}"
    return estado


@app.get("/api/parametros")
def parametros():
    m = parametros_mision()
    return {"bateria": bateria.resumen(m), "radio_operacion_m": m["r_op"], "altura_m": m["altura"],
            "alcance_m": m["alcance"], "diametro_sector_m": m["diametro_max"], "umbral_R": m["r_min_plan"],
            "visitas": m["visitas"], "ventana_h": m["ventana_h"]}


@app.get("/api/sectores")
def sectores():
    esc = _escenario()
    return {"sectores": mod_sectores.leer_sectores(esc)}


@app.get("/api/bases")
def bases():
    esc = _escenario()
    return {"bases": [{"id": b["id"], "tipo": b["tipo"], "nombre": b.get("nombre"), "lon": b["lon"], "lat": b["lat"],
                       "elevacion_m": b.get("elevacion_m"),
                       "camaras": sorted(c for c, x in b["camaras"].items() if x["bloque_visible"])}
                      for b in esc.bases.values()]}


@app.get("/api/caso-ejemplo")
def caso_ejemplo():
    import json

    from .config import CONFIG

    ruta = CONFIG / "caso_ejemplo.json"
    if not ruta.exists():
        raise HTTPException(404, "Todavía no hay un caso de ejemplo. Corre python -m motor.buscar_caso.")
    return json.loads(ruta.read_text(encoding="utf-8"))


@app.get("/api/especies")
def especies():
    return {"especies": sorted(_escenario().especies.values(), key=lambda e: -e["registros"])}


@app.post("/api/plan")
def plan(consulta: PlanIn):
    try:
        return servicio.planificar(consulta.model_dump(), _escenario())
    except ValueError as exc:
        _error(exc)


@app.post("/api/fallas")
def fallas(cuerpo: FallasIn):
    return servicio.simular_fallas(cuerpo.vuelos, _escenario(), cuerpo.overrides_prob, cuerpo.semilla)


@app.get("/api/probabilidades")
def probabilidades_get():
    return probabilidades.calcular(_escenario())


@app.post("/api/probabilidades")
def probabilidades_post(cuerpo: OverridesIn):
    return probabilidades.calcular(_escenario(), overrides=cuerpo.overrides_prob)


@app.post("/api/escenario")
def escenario(cuerpo: EscenarioIn):
    try:
        doc = escenarios.cargar(_escenario(), cuerpo.fecha)
    except ValueError as exc:
        _error(exc)
    return {"fecha": doc["fecha"], "modo_meteo": doc["modo_meteo"], "n_focos": len(doc["focos"]),
            "n_avistamientos": len(doc["aves"]), "fuentes": doc["fuentes"], "focos": doc["focos"]}


@app.post("/api/kml")
def kml(cuerpo: KmlIn):
    contenido = exportar.zip_plan(_escenario(), cuerpo.plan, cuerpo.fecha)
    nombre = f"plan_{cuerpo.plan.get('tecnica', 'vuelos')}.zip"
    return Response(contenido, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@app.get("/api/capacidad")
def capacidad_get(verano: int = 51, otono: int = 36, invierno: int = 25, primavera: int = 37):
    return capacidad.informe(_escenario(), {"verano": verano, "otono": otono, "invierno": invierno,
                                            "primavera": primavera})


@app.get("/api/campanas")
def campanas():
    return {"campanas": programador.almacen().campanas(), "tareas_de_hoy": [
        {"tipo": t, "campana": c["id"], "dia": d["id"], "fecha": d["fecha"]} for t, c, d in programador.tareas()]}


@app.post("/api/campanas")
def crear_campana(cuerpo: CampanaIn):
    try:
        return programador.crear(cuerpo.consulta, cuerpo.fecha_inicio, cuerpo.nombre, cuerpo.tipo,
                                 cuerpo.dias_disponibles)
    except (ValueError, KeyError) as exc:
        _error(exc)


def _campana(cid: int):
    store = programador.almacen()
    camp = next((c for c in store.campanas() if c["id"] == cid), None)
    if camp is None:
        raise HTTPException(404, "La campaña no existe.")
    return store, camp


@app.post("/api/campanas/{cid}/reprogramar")
def reprogramar(cid: int, cuerpo: ReprogramarIn):
    store, _ = _campana(cid)
    return programador.reprogramar(cid, cuerpo.fecha, store)


@app.post("/api/campanas/{cid}/decidir")
def decidir(cid: int):
    store, camp = _campana(cid)
    dia = next((d for d in sorted(camp["dias"], key=lambda d: d["visita"])
                if d["estado"] in ("programada", "postergada")), None)
    if dia is None:
        raise HTTPException(400, "La campaña no tiene visitas pendientes.")
    return programador.decidir(camp, dia, store, _escenario())


@app.post("/api/campanas/{cid}/volada/{did}")
def volada(cid: int, did: int):
    store, _ = _campana(cid)
    return programador.marcar_volada(cid, did, store)


@app.get("/api/campanas/{cid}/kml")
def kml_campana(cid: int):
    store, camp = _campana(cid)
    res = servicio.planificar({**camp["consulta"], "fecha": None}, _escenario(), n_mc=1000)
    mejor = next(p for p in res["planes"] if p["tecnica"] == (res["mas_resiliente"] or "dijkstra_distancia"))
    contenido = exportar.zip_plan(_escenario(), mejor, camp["fecha_inicio"])
    return Response(contenido, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="campana_{cid}.zip"'})


def main():
    import uvicorn

    uvicorn.run("motor.api:app", host="0.0.0.0", port=int(os.getenv("MOTOR_PORT", "8001")))


if __name__ == "__main__":
    main()
