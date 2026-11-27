import io
import zipfile
from datetime import date

import pytest

from motor import exportar, programador, servicio


@pytest.fixture
def store(tmp_path):
    return programador.AlmacenJSON(tmp_path / "campanas.json")


def test_dias_habiles():
    assert programador.dias_habiles_antes(date(2026, 12, 14), 7) == date(2026, 12, 3)


def test_fin_de_temporada(m):
    assert programador.fin_temporada(date(2026, 12, 20), m) == date(2027, 2, 28)
    assert programador.temporada_de(date(2026, 7, 1), m) == "invierno"


def test_campana_de_tres_mananas(store, consulta):
    c = programador.crear(consulta, "2026-12-14", store=store)
    assert [d["fecha"] for d in c["dias"]] == ["2026-12-14", "2026-12-15", "2026-12-16"]
    assert c["plan_provisorio"] == "2026-12-03"


def test_campana_parcial_queda_marcada(store, consulta):
    c = programador.crear(consulta, "2026-12-14", dias_disponibles=2, store=store)
    assert c["visitas_objetivo"] == 2 and c["avisos"]


def test_postergar_al_final_de_la_temporada(store, consulta, m):
    programador.crear(consulta, "2027-02-27", store=store)
    camp = store.campanas()[0]
    programador.reprogramar_desde(camp, camp["dias"][0], store, m)
    camp = store.campanas()[0]
    assert camp["estado"] == "incompleta"
    assert any(d["estado"] == "por_reprogramar" for d in camp["dias"])


def test_volada_completa_la_campana(store, consulta):
    programador.crear(consulta, "2026-12-14", store=store)
    camp = store.campanas()[0]
    for d in camp["dias"]:
        programador.marcar_volada(camp["id"], d["id"], store)
    assert store.campanas()[0]["completa"]


def test_kml_con_bloques_de_muestreo(esc, consulta, m):
    res = servicio.planificar(consulta, esc, n_mc=200)
    plan = res["planes"][1]
    v = plan["vuelos"][0]
    pts = exportar.waypoints(esc, v, m)
    assert len([p for p in pts if "ShootPhoto" in p["acciones"]]) == 25 * len(set(v["camaras"]))
    contenido = exportar.zip_plan(esc, plan)
    z = zipfile.ZipFile(io.BytesIO(contenido))
    assert "solicitud_dgac.json" in z.namelist()
    kml = z.read(next(n for n in z.namelist() if n.endswith(".kml"))).decode()
    assert "mis:actions" in kml and "relativeToGround" in kml
