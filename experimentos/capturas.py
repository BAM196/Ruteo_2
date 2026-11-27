import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
FIG = RAIZ / "experimentos" / "img"
SITIO = "http://127.0.0.1:8000"
MOTOR = "http://127.0.0.1:8001"
errores = []


def estado(pag, nombre, extra=""):
    info = pag.evaluate("""() => ({
        modo: state.mode,
        sector: document.querySelector('#sector-id').value,
        fecha: state.dateMode === 'pick' ? document.querySelector('#scenario-date').value : 'datos actuales',
        theta: document.querySelector('#theta').value,
        focos_simulados: (state.focosSimulados || []).length,
        restricciones: {solo_bosque: document.querySelector('#forest-only').checked,
                        evitar_senderos: document.querySelector('#avoid-trails').checked,
                        evitar_clima: document.querySelector('#avoid-weather').checked,
                        evitar_aves: document.querySelector('#avoid-birds').checked},
        tecnicas_visibles: [...state.visiblePlans],
        capas_encendidas: Object.entries(layers).filter(([k, l]) => map.hasLayer(l.group)).map(([k, l]) => l.name),
        zoom: map.getZoom(), centro: map.getCenter()
    })""")
    texto = "\n".join(f"{k}: {v}" for k, v in info.items())
    (FIG / f"{nombre}.txt").write_text(texto + ("\n" + extra if extra else "") + "\n", encoding="utf-8")


def capas(pag, encender=(), apagar=()):
    pag.evaluate("""([on, off]) => {
        for (const k of on) { layers[k].on = true; layers[k].group.addTo(map); }
        for (const k of off) { layers[k].on = false; map.removeLayer(layers[k].group); }
        document.querySelectorAll('#layer-list input').forEach(i => i.checked = layers[i.dataset.layer].on);
    }""", [list(encender), list(apagar)])


def esperar_mapa(pag, ms=2500):
    pag.wait_for_load_state("networkidle")
    pag.wait_for_timeout(ms)


def abrir(nav):
    pag = nav.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2, color_scheme="light")
    pag.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
    pag.on("pageerror", lambda e: errores.append(str(e)))
    pag.goto(SITIO, wait_until="networkidle")
    pag.wait_for_function("document.querySelector('#sector-id').options.length > 0", timeout=60000)
    return pag


def caso_ejemplo(pag):
    pag.click("#example-button")
    pag.wait_for_selector("#plan-list li", timeout=180000)
    pag.wait_for_function("!document.querySelector('#plan-button').disabled", timeout=180000)
    esperar_mapa(pag)


def captura_bloqueo(nav):
    import csv

    filas = list(csv.DictReader(open(RAIZ / "experimentos" / "resultados" / "E1_bloqueos_por_base.csv", encoding="utf-8")))
    sector = max(filas, key=lambda f: int(f["bloqueadas_linea_de_vista"]))["sector"]
    pag = abrir(nav)
    pag.select_option("#sector-id", sector)
    pag.click("#plan-button")
    pag.wait_for_selector("#plan-list li", timeout=180000)
    pag.wait_for_function("!document.querySelector('#plan-button').disabled", timeout=180000)
    esperar_mapa(pag)
    capas(pag, encender=("blocked", "radius", "bases"), apagar=("trails", "birds", "edges", "weather", "sectors", "routes"))
    bloqueo = pag.evaluate("""() => {
        const ls = layers.blocked.group.getLayers();
        if (!ls.length) return null;
        map.fitBounds(L.featureGroup([...ls, ...layers.radius.group.getLayers()]).getBounds().pad(0.05));
        ls[0].openPopup(ls[0].getBounds().getCenter());
        return state.plan.capas.aristas_bloqueadas.length;
    }""")
    pag.wait_for_timeout(1500)
    pag.locator("#map").screenshot(path=str(FIG / "fig_bloqueo.png"))
    estado(pag, "fig_bloqueo", f"Sector {sector}: {bloqueo} tramos bloqueados desde su base (rojo discontinuo); popup de uno de ellos.")
    pag.close()


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", headless=True)
        captura_bloqueo(nav)
        if "--solo-bloqueo" in sys.argv:
            nav.close()
            return

        pag = abrir(nav)
        pag.click("#options summary")
        pag.evaluate("document.querySelector('#panel').style.height = 'auto'")
        pag.wait_for_timeout(400)
        pag.locator("#panel").screenshot(path=str(FIG / "fig_formulario.png"))
        estado(pag, "fig_formulario", "Solo el panel, con las opciones desplegadas.")

        capas(pag, apagar=("trails", "birds", "fires", "edges", "weather"))
        pag.evaluate("""() => {
            const g = L.layerGroup().addTo(map);
            for (const s of state.sectors) {
                const c = state.sectorShapes.get(String(s.id)).getBounds().getCenter();
                if (s.base) L.circleMarker([s.base.lat, s.base.lon], {radius: 4, color: '#2f6f9f', weight: 2, fillColor: '#fff', fillOpacity: 1}).addTo(g);
                L.circleMarker(c, {radius: 9, color: '#1f2a24', weight: 1, fillColor: priorityColor(s.prioridad), fillOpacity: 0.95})
                  .bindTooltip(String(s.id), {permanent: true, direction: 'right', offset: [8, 0], className: 'etiqueta-sector'}).addTo(g);
            }
            const st = document.createElement('style');
            st.textContent = '.etiqueta-sector{background:rgba(255,255,255,.85);border:0;box-shadow:none;font:600 12px Outfit,sans-serif;padding:0 3px;color:#1f2a24}.etiqueta-sector:before{display:none}';
            document.head.appendChild(st);
            window._sectores = g;
            const todas = L.featureGroup([...state.sectorShapes.values()]);
            map.fitBounds(todas.getBounds().pad(0.03));
            return null;
        }""")
        esperar_mapa(pag)
        top = pag.evaluate("[...state.sectors].sort((a,b)=>b.prioridad-a.prioridad).find(s=>s.base).id")
        pag.evaluate(f"void state.sectorShapes.get('{top}').openPopup(state.sectorShapes.get('{top}').getBounds().getCenter())")
        pag.wait_for_timeout(800)
        pag.locator("#map").screenshot(path=str(FIG / "fig_sectores.png"))
        estado(pag, "fig_sectores", f"Popup abierto: sector {top} (mayor prioridad con base). Marcadores azules: base de cada sector.")
        pag.evaluate("void map.closePopup()")
        for mitad, sel in (("norte", "Math.max"), ("sur", "Math.min")):
            pag.evaluate(f"""() => {{
                const lats = [...state.sectorShapes.values()].map(sh => sh.getBounds().getCenter().lat).sort((a, b) => a - b);
                const corte = lats[Math.floor(lats.length / 2)];
                const grupo = L.featureGroup([...state.sectorShapes.entries()].filter(([k, sh]) =>
                    ('{mitad}' === 'norte') === (sh.getBounds().getCenter().lat >= corte)).map(([k, sh]) => sh));
                map.fitBounds(grupo.getBounds().pad(0.08));
                return null;
            }}""")
            esperar_mapa(pag)
            pag.locator("#map").screenshot(path=str(FIG / f"fig_sectores_{mitad}.png"))
            estado(pag, f"fig_sectores_{mitad}", f"Mitad {mitad} del parque.")
        pag.close()

        pag = abrir(nav)
        caso_ejemplo(pag)
        capas(pag, apagar=("trails", "birds", "edges", "weather", "sectors"))
        pag.evaluate("void (window._vista = [map.getCenter(), map.getZoom()])")
        pag.locator("#map").screenshot(path=str(FIG / "fig_caso_rutas.png"))
        estado(pag, "fig_caso_rutas", "Las 4 técnicas superpuestas. Foco simulado en naranjo, base y radio de 1.500 m en azul.")
        pag.locator("#plan-list").screenshot(path=str(FIG / "fig_leyenda.png"))
        leyendas = pag.evaluate("state.plan.planes.map(p => (p.tecnica === state.plan.mas_resiliente ? '★ ' : '') + p.leyenda)")
        (FIG / "fig_leyenda.txt").write_text("\n".join(leyendas) + "\n", encoding="utf-8")
        tecnicas = ["dijkstra_distancia", "milp", "dijkstra_ponderado", "aco"]
        for k, t in enumerate(tecnicas, start=1):
            pag.evaluate(f"""() => {{
                state.visiblePlans = new Set(['{t}']);
                document.querySelectorAll('#plan-list input[data-plan]').forEach(i => i.checked = i.dataset.plan === '{t}');
                drawPlan();
                map.setView(window._vista[0], window._vista[1], {{animate: false}});
                return null;
            }}""")
            esperar_mapa(pag, 1500)
            pag.locator("#map").screenshot(path=str(FIG / f"fig_caso_t{k}.png"))
            estado(pag, f"fig_caso_t{k}", f"Solo la técnica {k} ({t}), mismo encuadre que fig_caso_rutas.")
        pag.evaluate("""() => {
            state.visiblePlans = new Set(['dijkstra_distancia', 'milp', 'dijkstra_ponderado', 'aco']);
            document.querySelectorAll('#plan-list input[data-plan]').forEach(i => i.checked = true);
            drawPlan();
            map.setView(window._vista[0], window._vista[1], {animate: false});
            return null;
        }""")
        pag.click("#fail-button")
        pag.wait_for_selector("#fail-result:not([hidden])", timeout=60000)
        pag.evaluate("document.querySelector('#fail-result').scrollIntoView({block: 'end'})")
        esperar_mapa(pag, 1500)
        pag.screenshot(path=str(FIG / "fig_fallas.png"))
        (FIG / "fig_fallas_resultado.txt").write_text(pag.inner_text("#fail-result"), encoding="utf-8")
        estado(pag, "fig_fallas", "Página completa: panel con el resultado del sorteo y mapa con lo que falló (rombos y tramos rojos).")

        capas(pag, encender=("edges",), apagar=("routes", "failures", "blocks"))
        perfil = pag.evaluate("""() => {
            let elegido = null;
            const base = state.plan.capas.bases[0];
            const c = L.latLng(base.lat, base.lon);
            layers.edges.group.eachLayer(g => g.eachLayer(l => {
                const p = l.feature.properties;
                if (p.densified && !p.blocked && p.climb_m > 20) {
                    const d = c.distanceTo(l.getBounds().getCenter());
                    if (!elegido || d < elegido[1]) elegido = [l, d];
                }
            }));
            if (!elegido) return null;
            map.fitBounds(elegido[0].getBounds().pad(1.2));
            elegido[0].setStyle({color: '#1c4330', weight: 5});
            elegido[0].openPopup(elegido[0].getBounds().getCenter());
            return elegido[0].feature.properties.id;
        }""")
        pag.wait_for_timeout(1500)
        pag.locator("#map").screenshot(path=str(FIG / "fig_perfil.png"))
        estado(pag, "fig_perfil", f"Tramo {perfil}: densificado para seguir el relieve, con su popup de perfil.")
        pag.evaluate("void map.closePopup()")
        pag.close()

        cuerpo = json.dumps({"consulta": {"modo": "sector", "sector_id": 20}, "fecha_inicio": "2026-12-14",
                             "tipo": "ronda", "dias_disponibles": 3}).encode()
        req = urllib.request.Request(f"{MOTOR}/api/campanas", data=cuerpo, headers={"Content-Type": "application/json"})
        camp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        parcial = json.dumps({"consulta": {"modo": "sector", "sector_id": 22}, "fecha_inicio": "2026-12-21",
                              "tipo": "evento: incendio apagado", "dias_disponibles": 2}).encode()
        urllib.request.urlopen(urllib.request.Request(f"{MOTOR}/api/campanas", data=parcial,
                                                      headers={"Content-Type": "application/json"}), timeout=60)
        pag = abrir(nav)
        pag.click(".tab[data-tab='campaigns']")
        pag.wait_for_selector("#campaign-list li", timeout=60000)
        pag.click(f"#campaign-list button[data-decide='{camp['id']}']")
        pag.wait_for_function("document.querySelector('#campaign-status').textContent.match(/^(Volar|Postergar)/)", timeout=300000)
        pag.wait_for_timeout(2500)
        pag.evaluate("document.querySelector('#panel').style.height = 'auto'")
        pag.locator("#panel").screenshot(path=str(FIG / "fig_campanas.png"))
        estado(pag, "fig_campanas", f"Campañas de ejemplo creadas para la captura (ids {camp['id']} y siguiente). "
                                    f"Decisión mostrada: {pag.inner_text('#campaign-status')}")
        pag.close()
        nav.close()
    print("Capturas listas.", "Errores del navegador: " + ("; ".join(errores) if errores else "ninguno"))
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
