import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import grafo, probabilidades, servicio
from .config import fuente_por_defecto

app = FastAPI(title="Motor de rutas resilientes - Pumalín", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Restricciones(BaseModel):
    solo_bosque: bool = False
    evitar_senderos: bool = False
    evitar_clima: bool = False
    evitar_aves: bool = False
    excluir_nodos: list[int] = Field(default_factory=list)


class ConsultaIn(BaseModel):
    origen_id: int
    destino_id: int
    restricciones: Restricciones = Field(default_factory=Restricciones)
    autonomia_m: float | None = None
    theta: float = Field(0.5, ge=0, le=1)
    overrides_prob: dict = Field(default_factory=dict)
    r_min: float | None = Field(None, gt=0, le=1)
    tecnicas: list[str] | None = None
    aco_config: str | None = None
    semilla: int = 0


class OverridesIn(BaseModel):
    overrides_prob: dict = Field(default_factory=dict)
    semilla: int | None = None


def _escenario():
    try:
        return grafo.cargar(fuente_por_defecto(), os.getenv("MOTOR_GRAFO_JSON") or None)
    except Exception as exc:
        raise HTTPException(503, f"No se pudo cargar el grafo: {exc}") from exc


@app.get("/health")
def health():
    estado = {"fuente": fuente_por_defecto()}
    try:
        esc = _escenario()
        estado.update(esc.resumen())
        estado["base"] = "ok"
    except HTTPException as exc:
        estado["base"] = exc.detail
    try:
        import gurobipy

        estado["gurobi"] = ".".join(map(str, gurobipy.gurobi.version()))
    except Exception as exc:
        estado["gurobi"] = f"no disponible: {exc}"
    return estado


@app.post("/api/rutas")
def rutas(consulta: ConsultaIn):
    return servicio.calcular_rutas(consulta.model_dump(), _escenario())


@app.get("/api/probabilidades")
def probabilidades_get():
    return probabilidades.calcular(_escenario())


@app.post("/api/probabilidades")
def probabilidades_post(cuerpo: OverridesIn):
    return probabilidades.calcular(_escenario(), overrides=cuerpo.overrides_prob)


@app.post("/api/fallas")
def fallas(cuerpo: OverridesIn):
    return servicio.simular_fallas(_escenario(), cuerpo.overrides_prob, cuerpo.semilla)


def main():
    import uvicorn

    uvicorn.run("motor.api:app", host="0.0.0.0", port=int(os.getenv("MOTOR_PORT", "8001")))


if __name__ == "__main__":
    main()
