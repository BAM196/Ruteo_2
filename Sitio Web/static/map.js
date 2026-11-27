const MOTOR = `${window.location.protocol}//${window.location.hostname}:8001`;

const TECH = {
  dijkstra_distancia: { color: "#7d8590", dash: "10 6", weight: 7, short: "Solo distancia" },
  milp: { color: "#2f6f9f", dash: null, weight: 5, short: "Óptimo (Gurobi)" },
  dijkstra_ponderado: { color: "#c98a1b", dash: "2 7", weight: 5, short: "Ponderado" },
  aco: { color: "#7b3fa0", dash: "14 8", weight: 3, short: "Colonia de hormigas" },
};

const COVER = { 10: "#2f7d4f", 20: "#8aa35a", 30: "#b9c46a", 60: "#b6a58c", 80: "#4f8fc0", 90: "#6fb3a0" };

const state = {
  mode: "sector",
  dateMode: "now",
  cameras: new Set(),
  threat: null,
  plan: null,
  data: {},
  sectors: [],
  bases: [],
  species: [],
  nodesById: new Map(),
  edgesById: new Map(),
  cameraMarkers: new Map(),
  sectorShapes: new Map(),
  visiblePlans: new Set(Object.keys(TECH)),
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const num = (x, d = 0) => (x === null || x === undefined || Number.isNaN(x) ? "—" : Number(x).toLocaleString("es-CL", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (p) => `${num(100 * p, p < 0.1 ? 1 : 0)} %`;

const map = L.map("map", { zoomControl: true, preferCanvas: true }).setView([-42.5, -72.6], 10);
const baseLayers = {
  Relieve: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", { maxZoom: 16, attribution: "© OpenStreetMap, SRTM · OpenTopoMap" }),
  Satélite: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 18, attribution: "© Esri" }),
  Calles: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }),
};
baseLayers.Relieve.addTo(map);
L.control.layers(baseLayers, null, { position: "topright" }).addTo(map);

const layers = {
  sectors: { name: "Sectores", group: L.layerGroup().addTo(map), on: true },
  cameras: { name: "Cámaras", group: L.layerGroup().addTo(map), on: true },
  routes: { name: "Vuelos planificados", group: L.layerGroup().addTo(map), on: true },
  bases: { name: "Bases del plan", group: L.layerGroup().addTo(map), on: true },
  radius: { name: "Radio de operación", group: L.layerGroup().addTo(map), on: true },
  blocks: { name: "Bloques de muestreo", group: L.layerGroup().addTo(map), on: true },
  blocked: { name: "Tramos bloqueados", group: L.layerGroup().addTo(map), on: true },
  edges: { name: "Tramos de la red", group: L.layerGroup(), on: false },
  trails: { name: "Senderos", group: L.layerGroup().addTo(map), on: true },
  fires: { name: "Focos de incendio", group: L.layerGroup().addTo(map), on: true },
  birds: { name: "Aves", group: L.layerGroup().addTo(map), on: true },
  weather: { name: "Clima en las cámaras", group: L.layerGroup(), on: false },
  threat: { name: "Amenaza simulada", group: L.layerGroup().addTo(map), on: true },
  failures: { name: "Fallas sorteadas", group: L.layerGroup().addTo(map), on: true },
};

async function getJSON(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || body.error || `Error ${res.status}`);
  return body;
}

function setStatus(text) {
  $("#plan-status").textContent = text || "";
}

function showError(text) {
  const el = $("#plan-error");
  el.hidden = !text;
  el.textContent = text || "";
}

function speciesTags(list) {
  return list
    .map((s) => {
      const cls = s.target ? (s.category === "VU" ? "vu" : "nt") : s.pressure ? "exotic" : "";
      const cat = s.target && s.category ? ` ${s.category}` : s.pressure ? " exótica" : "";
      return `<span class="tag ${cls}">${esc(s.common || s.scientific)}${cat}</span>`;
    })
    .join("");
}

function priorityColor(p) {
  const t = Math.max(0, Math.min(1, (p || 0) / 100));
  const a = [243, 227, 176];
  const b = [182, 58, 43];
  const c = a.map((x, i) => Math.round(x + (b[i] - x) * t));
  return `rgb(${c.join(",")})`;
}

function sectorById(id) {
  return state.sectors.find((s) => String(s.id) === String(id));
}

function cameraName(id) {
  const n = state.nodesById.get(Number(id));
  return n ? n.name.replace(/^Camara\s*/i, "") : `#${id}`;
}

function cameraPopup(f) {
  const p = f.properties;
  const sector = state.sectors.find((s) => s.camaras.includes(p.id));
  const rows = (p.species || [])
    .map((s) => `<tr><td>${esc(s.common || s.scientific)} ${s.target ? `<span class="tag ${s.category === "VU" ? "vu" : "nt"}">${esc(s.category)}</span>` : s.pressure ? '<span class="tag exotic">exótica</span>' : ""}</td><td>${num(s.records)}</td></tr>`)
    .join("");
  const action = state.mode === "camaras"
    ? `<button class="popup-button" data-toggle-camera="${p.id}">${state.cameras.has(p.id) ? "Quitar de la selección" : "Agregar a la selección"}</button>`
    : sector ? `<button class="popup-button" data-plan-sector="${sector.id}">Planificar el sector ${sector.id}</button>` : "";
  return `<h4>Cámara ${esc(cameraName(p.id))}</h4>
    <p>${esc(p.land_cover_label || "Sin dato de cobertura")} · ${num(p.elevation_m)} m s. n. m.${sector ? ` · Sector ${sector.id}` : ""}</p>
    <table><tr><td><b>Especie registrada</b></td><td><b>Registros</b></td></tr>${rows || '<tr><td colspan="2">Sin registros</td></tr>'}</table>${action}`;
}

function edgePopup(p, extra = "") {
  const kind = { knn: "Entre cámaras", conexion: "Conexión", radio_camara: "Hacia el anillo", anillo_camara: "Anillo de la cámara", desvio_arista: "Desvío", enlace_anillo: "Enlace", enlace_base: "Desde la base" }[p.kind] || "Tramo";
  const risk = state.plan?.probabilidades?.aristas_con_riesgo?.[p.id];
  const rows = [
    ["Largo en vuelo", `${num((p.length_3d_m || p.distance_m) / 1000, 2)} km`],
    ["Ascenso (ida / vuelta)", `${num(p.climb_m)} / ${num(p.climb_back_m)} m`],
    ["Despeje mínimo sobre el terreno", `${num(p.clearance_m)} m`],
    ["Sigue el relieve", p.densified ? "sí" : "no"],
  ];
  if (risk !== undefined) rows.push(["Probabilidad de falla", pct(risk)]);
  const blocked = p.blocked ? `<p class="hint" style="color:#b63a2b">Bloqueado: ${esc(p.blocked_reason)}</p>` : "";
  return `<h4>${kind} · tramo ${p.id}</h4><table>${rows.map((r) => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join("")}</table>${blocked}${extra}
    ${p.blocked ? "" : `<button class="popup-button" data-threat-edge="${p.id}">Simular amenaza en este tramo</button>`}`;
}

function drawStatic() {
  const d = state.data;
  layers.edges.group.clearLayers();
  L.geoJSON(d.edges, {
    style: (f) => (f.properties.blocked ? { color: "#b63a2b", weight: 2, dashArray: "4 4", opacity: 0.8 } : { color: "#8f9b93", weight: 1.4, opacity: 0.7 }),
    onEachFeature: (f, l) => l.bindPopup(() => edgePopup(f.properties)),
  }).addTo(layers.edges.group);

  layers.cameras.group.clearLayers();
  state.cameraMarkers.clear();
  for (const f of d.nodes.features) {
    const p = f.properties;
    if (!p.is_camera) continue;
    const [lon, lat] = f.geometry.coordinates;
    const target = (p.species || []).some((s) => s.target);
    const m = L.circleMarker([lat, lon], { radius: 6, color: "#fff", weight: 1.5, fillColor: COVER[p.land_cover_code] || "#285c3f", fillOpacity: 1 });
    m.bindPopup(() => cameraPopup(f));
    m.bindTooltip(cameraName(p.id), { direction: "top", offset: [0, -6] });
    m.on("click", () => {
      if (state.mode === "camaras") toggleCamera(p.id);
    });
    if (target) m.options.radius = 7;
    m.addTo(layers.cameras.group);
    state.cameraMarkers.set(p.id, m);
  }

  layers.trails.group.clearLayers();
  L.geoJSON(d.trails, {
    style: { color: "#7b5a3c", weight: 2.5, opacity: 0.85 },
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4, color: "#7b5a3c", fillColor: "#e9dcc8", fillOpacity: 1, weight: 1.5 }),
    onEachFeature: (f, l) => l.bindPopup(`<h4>${esc(f.properties.name)}</h4><p>${f.properties.length_km ? `${num(f.properties.length_km, 1)} km · ` : ""}Los vuelos pueden evitar sobrevolar a los visitantes.</p>`),
  }).addTo(layers.trails.group);

  drawFires(d.fires);

  layers.birds.group.clearLayers();
  L.geoJSON(d.ebird, {
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 6, color: "#fff", weight: 1.5, fillColor: "#6a4c93", fillOpacity: 0.95 }),
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindPopup(`<h4>${esc(p.common_name)}</h4><p><i>${esc(p.scientific_name)}</i><br>${num(p.count)} ave(s) · ${esc(p.observed_at || "")}<br>${esc(p.location || "")}</p>`);
    },
  }).addTo(layers.birds.group);

  layers.weather.group.clearLayers();
  L.geoJSON(d.meteo, {
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 11, color: "#2f6f9f", weight: 1, fillColor: "#2f6f9f", fillOpacity: 0.12 }),
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindPopup(`<h4>Clima en la mañana</h4><table>
        <tr><td>Ráfaga a 10 m</td><td>${num(p.gust ?? p.wind_speed, 1)} m/s</td></tr>
        <tr><td>Temperatura</td><td>${num(p.temp_min ?? p.temperature, 1)} a ${num(p.temp_max ?? p.temperature, 1)} °C</td></tr>
        <tr><td>Probabilidad de lluvia</td><td>${p.rain_probability === null || p.rain_probability === undefined ? "—" : `${num(p.rain_probability)} %`}</td></tr>
        <tr><td>Lluvia</td><td>${num(p.rain_mm, 1)} mm</td></tr></table><p class="hint">${esc(p.date || "")} · ${p.mode === "historico" ? "histórico" : "pronóstico"}</p>`);
    },
  }).addTo(layers.weather.group);

  drawSectors();
}

function drawFires(fc) {
  layers.fires.group.clearLayers();
  L.geoJSON(fc, {
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 7, color: "#fff", weight: 1.5, fillColor: "#e4572e", fillOpacity: 0.95 }),
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindPopup(`<h4>Foco de incendio</h4><p>${esc(p.acquired_on || p.fecha || "")} · confianza ${esc(p.confidence ?? "—")}<br>Potencia ${num(p.frp, 1)} MW</p>`);
    },
  }).addTo(layers.fires.group);
}

function drawSectors() {
  layers.sectors.group.clearLayers();
  state.sectorShapes.clear();
  for (const s of state.sectors) {
    const ring = s.poligono[0].map(([lon, lat]) => [lat, lon]);
    const shape = L.polygon(ring, { color: priorityColor(s.prioridad), weight: 1.5, fillColor: priorityColor(s.prioridad), fillOpacity: 0.28 });
    shape.bindPopup(() => `<h4>Sector ${s.id}</h4><p>${esc(s.subtitulo.split(" · ").slice(1).join(" · "))}</p>
      <p class="hint">${s.n_camaras} cámara(s): ${s.camaras.map(cameraName).join(", ")}${s.base ? ` · base ${esc(s.base.nombre || s.base.id)}` : " · sin base con línea de vista"}</p>
      <button class="popup-button" data-plan-sector="${s.id}">Planificar este sector</button>`);
    shape.addTo(layers.sectors.group);
    state.sectorShapes.set(String(s.id), shape);
  }
}

function fillSelects() {
  const sectors = [...state.sectors].sort((a, b) => b.prioridad - a.prioridad);
  $("#sector-id").innerHTML = sectors
    .map((s) => `<option value="${s.id}">Sector ${s.id} · prioridad ${num(s.prioridad)} % · ${s.n_camaras} cámara${s.n_camaras > 1 ? "s" : ""}${s.base ? "" : " · sin base"}</option>`)
    .join("");
  const firstWithBase = sectors.find((s) => s.base);
  if (firstWithBase) $("#sector-id").value = firstWithBase.id;

  const sp = [...state.species].sort((a, b) => (b.objetivo - a.objetivo) || (b.registros - a.registros));
  $("#species-id").innerHTML = sp
    .map((s) => `<option value="${esc(s.cientifico)}">${esc(s.comun)}${s.objetivo ? ` (${s.categoria_los_lagos})` : s.presion ? " (exótica)" : ""} · ${s.camaras} cámaras</option>`)
    .join("");

  $("#exclude-ids").innerHTML = state.data.nodes.features
    .filter((f) => f.properties.is_camera)
    .map((f) => `<option value="${f.properties.id}">${esc(cameraName(f.properties.id))}</option>`)
    .join("");

  const sinBase = state.sectors.filter((s) => !s.base).length;
  $("#park-info").innerHTML = `<b>${state.sectors.length} sectores</b> ordenados por prioridad, cada uno desde su base.${sinBase ? ` ${sinBase} cámara(s) no tienen base con línea de vista y quedan fuera.` : ""}`;
  updateModeInfo();
}

function updateModeInfo() {
  const s = sectorById($("#sector-id").value);
  if (s) {
    const d = s.descripcion;
    $("#sector-info").innerHTML = `${d.predominan.length ? `Predominan: <b>${esc(d.predominan.join(", "))}</b><br>` : ""}
      ${d.objetivo.length ? `Objetivo: ${d.objetivo.map((x) => `<span class="tag ${/\(VU\)/.test(x) ? "vu" : "nt"}">${esc(x)}</span>`).join("")}<br>` : ""}
      ${d.exoticas.length ? `Presión: ${d.exoticas.map((x) => `<span class="tag exotic">${esc(x)}</span>`).join("")}<br>` : ""}
      <span class="hint">Cámara${s.camaras.length > 1 ? "s" : ""}: ${s.camaras.map(cameraName).join(", ")}${s.base ? "" : " · no hay base con línea de vista"}</span>`;
  }
  const sp = state.species.find((x) => x.cientifico === $("#species-id").value);
  if (sp) {
    const amen = sp.amenazas ? `<br><span class="hint">Amenazas: ${esc(sp.amenazas.texto)}</span>` : sp.como_presiona ? `<br><span class="hint">${esc(sp.como_presiona)}</span>` : "";
    const comp = sp.comportamiento ? `<br><span class="hint">${esc(sp.comportamiento.social)} · ${esc(sp.comportamiento.actividad)}</span>` : "";
    $("#species-info").innerHTML = `${sp.objetivo ? `<span class="tag ${sp.categoria_los_lagos === "VU" ? "vu" : "nt"}">${esc(sp.categoria_los_lagos)} en Los Lagos</span>` : sp.presion ? '<span class="tag exotic">Exótica o doméstica</span>' : `<span class="tag">${esc(sp.categoria_los_lagos || "")}</span>`}
      Registrada en <b>${sp.camaras} cámaras</b> (${num(sp.registros)} registros).${comp}${amen}`;
  }
  fillBases();
}

function selectionCameras() {
  if (state.mode === "sector") return sectorById($("#sector-id").value)?.camaras || [];
  if (state.mode === "camaras") return [...state.cameras];
  return [];
}

function fillBases() {
  const cams = selectionCameras();
  const select = $("#base-id");
  const current = select.value;
  const options = cams.length
    ? state.bases.filter((b) => cams.every((c) => b.camaras.includes(c))).slice(0, 60)
    : [];
  select.innerHTML = `<option value="">Automática (la más cercana a las cámaras)</option>` +
    options.map((b) => `<option value="${b.id}">${esc(b.tipo === "camara" ? `Junto a la cámara ${cameraName(b.id)}` : b.nombre)}</option>`).join("");
  select.disabled = !(state.mode === "sector" || state.mode === "camaras");
  if ([...select.options].some((o) => o.value === current)) select.value = current;
}

function setMode(mode) {
  state.mode = mode;
  $$("#mode-picker button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  $$(".mode-body").forEach((el) => (el.hidden = el.dataset.for !== mode));
  refreshCameraStyles();
  updateModeInfo();
  if (mode === "sector") focusSector($("#sector-id").value);
}

function focusSector(id) {
  const shape = state.sectorShapes.get(String(id));
  state.sectorShapes.forEach((sh, key) => sh.setStyle({ weight: key === String(id) ? 3.5 : 1.5 }));
  if (shape) map.fitBounds(shape.getBounds().pad(0.8), { maxZoom: 14 });
}

function toggleCamera(id) {
  if (state.cameras.has(id)) state.cameras.delete(id);
  else state.cameras.add(id);
  renderChips();
  refreshCameraStyles();
  fillBases();
}

function renderChips() {
  $("#camera-chips").innerHTML = state.cameras.size
    ? [...state.cameras].map((c) => `<button type="button" class="chip" data-remove-camera="${c}">${esc(cameraName(c))}</button>`).join("")
    : '<span class="hint">Todavía no eliges cámaras.</span>';
}

function refreshCameraStyles() {
  state.cameraMarkers.forEach((m, id) => {
    const sel = state.mode === "camaras" && state.cameras.has(id);
    m.setStyle({ color: sel ? "#c98a1b" : "#fff", weight: sel ? 4 : 1.5 });
  });
}

function thetaLabel(v) {
  if (v <= 0.15) return "solo distancia";
  if (v < 0.4) return "más corto";
  if (v <= 0.6) return "equilibrado";
  if (v < 0.85) return "más seguro";
  return "solo riesgo";
}

function buildQuery() {
  const q = {
    modo: state.mode,
    theta: Number($("#theta").value),
    restricciones: {
      solo_bosque: $("#forest-only").checked,
      evitar_senderos: $("#avoid-trails").checked,
      evitar_clima: $("#avoid-weather").checked,
      evitar_aves: $("#avoid-birds").checked,
      excluir_nodos: [...$("#exclude-ids").selectedOptions].map((o) => Number(o.value)),
    },
    overrides_prob: state.threat ? { aristas: { [state.threat.edge]: Number($("#threat-p").value) } } : {},
  };
  if (state.mode === "sector") q.sector_id = Number($("#sector-id").value);
  if (state.mode === "especie") q.especie = $("#species-id").value;
  if (state.mode === "camaras") q.camaras = [...state.cameras];
  if ($("#base-id").value && !$("#base-id").disabled) q.base_id = Number($("#base-id").value);
  if (state.dateMode === "pick" && $("#scenario-date").value) q.fecha = $("#scenario-date").value;
  if (state.focosSimulados?.length) q.focos_simulados = state.focosSimulados;
  return q;
}

function setThreat(edgeId) {
  state.threat = edgeId ? { edge: edgeId } : null;
  layers.threat.group.clearLayers();
  $("#threat-clear").hidden = !edgeId;
  $("#threat-p-box").hidden = !edgeId;
  if (!edgeId) {
    $("#threat-info").textContent = "Toca un tramo en el mapa y elige «Simular amenaza».";
    return;
  }
  const f = state.edgesById.get(edgeId);
  $("#threat-info").innerHTML = `Tramo <b>${edgeId}</b> con una amenaza simulada.`;
  $("#options").open = true;
  if (f) L.geoJSON(f, { style: { color: "#e4572e", weight: 9, opacity: 0.55 } }).addTo(layers.threat.group);
  map.closePopup();
}

function shade(hex, k, n) {
  if (n <= 1) return hex;
  const f = 0.75 + (0.5 * k) / (n - 1);
  const c = [1, 3, 5].map((i) => Math.max(0, Math.min(255, Math.round(parseInt(hex.slice(i, i + 2), 16) * f))));
  return `rgb(${c.join(",")})`;
}

function drawPlan() {
  layers.routes.group.clearLayers();
  layers.bases.group.clearLayers();
  layers.radius.group.clearLayers();
  layers.blocks.group.clearLayers();
  layers.blocked.group.clearLayers();
  const r = state.plan;
  if (!r) return;
  const bounds = [];
  const order = ["dijkstra_distancia", "dijkstra_ponderado", "aco", "milp"];
  for (const tech of order) {
    const p = r.planes.find((x) => x.tecnica === tech);
    if (!p || !state.visiblePlans.has(tech)) continue;
    const st = TECH[tech];
    p.vuelos.forEach((v, k) => {
      const line = L.geoJSON(v.geojson, { style: { color: shade(st.color, k, p.vuelos.length), weight: st.weight, dashArray: st.dash, opacity: 0.9, lineCap: "round" } });
      line.bindTooltip(`${esc(p.etiqueta)} · vuelo ${v.vuelo} · R ${num(v.R, 3)}`, { sticky: true });
      line.addTo(layers.routes.group);
      line.eachLayer((l) => bounds.push(l.getBounds()));
    });
  }
  for (const b of r.capas.bases) {
    if (!b) continue;
    L.circle([b.lat, b.lon], { radius: r.capas.radio_m, color: "#2f6f9f", weight: 1.5, dashArray: "6 6", fill: false }).addTo(layers.radius.group);
    L.circleMarker([b.lat, b.lon], { radius: 7, color: "#2f6f9f", weight: 3, fillColor: "#fff", fillOpacity: 1 })
      .bindPopup(`<h4>Base del operador</h4><p>${esc(b.nombre || b.id)}<br>${b.tipo === "camara" ? "Junto a una cámara" : b.tipo === "sendero" ? "Sobre un sendero oficial" : "En la caminata entre cámaras"} · ${num(b.elevacion_m)} m s. n. m.</p>`)
      .addTo(layers.bases.group);
  }
  L.geoJSON(r.capas.bloques, {
    style: { color: "#2f6f9f", weight: 1, fillColor: "#2f6f9f", fillOpacity: 0.18 },
    onEachFeature: (f, l) => l.bindPopup(`<h4>Bloque de muestreo</h4><p>${esc(cameraName(f.properties.camara_id))}: ${f.properties.puntos} fotos térmicas cada 50 m, a ${f.properties.altura_m} m sobre el terreno.</p>`),
  }).addTo(layers.blocks.group);
  for (const b of r.capas.aristas_bloqueadas) {
    const f = state.edgesById.get(b.id);
    if (!f) continue;
    L.geoJSON(f, { style: { color: "#b63a2b", weight: 2.5, dashArray: "5 5", opacity: 0.85 } })
      .bindPopup(() => edgePopup(f.properties, `<p class="hint" style="color:#b63a2b">No se puede volar desde esta base: ${b.motivo === "linea_de_vista" ? "un cerro corta la línea de vista" : "exige pasar los 120 m sobre el terreno"}.</p>`))
      .addTo(layers.blocked.group);
  }
  if (bounds.length) {
    const all = bounds.reduce((acc, b) => acc.extend(b), L.latLngBounds(bounds[0].getSouthWest(), bounds[0].getNorthEast()));
    map.fitBounds(all.pad(0.35), { maxZoom: 15 });
  } else if (r.capas.bases.length) {
    map.setView([r.capas.bases[0].lat, r.capas.bases[0].lon], 14);
  }
}

function renderResults() {
  const r = state.plan;
  const best = r.planes.find((p) => p.tecnica === r.mas_resiliente);
  const nCams = new Set(r.sectores.flatMap((s) => s.camaras_plan || [])).size;
  const noVis = Object.entries(r.no_visitadas);
  const bases = r.sectores.filter((s) => s.base);
  $("#summary-card").innerHTML = `<h3>${esc(r.titulo)}</h3>
    <p>${nCams} cámara${nCams === 1 ? "" : "s"} en ${bases.length} sector${bases.length === 1 ? "" : "es"}${bases.length === 1 ? ` · base: ${esc(bases[0].base.nombre || bases[0].base.id)}` : ""}${r.escenario.fecha_escenario ? ` · datos del ${esc(r.escenario.fecha_escenario)}` : ""}</p>
    ${best ? `<p>★ Más resiliente: <b>${esc(best.etiqueta)}</b>, con ${pct(best.R)} de probabilidad de completar el plan.</p>` : ""}
    ${r.resiliencia.empate_en_R.length > 1 ? `<p>${r.resiliencia.empate_en_R.length === r.planes.length ? "Las cuatro técnicas" : `${r.resiliencia.empate_en_R.length} técnicas`} empatan en R: se destaca la de menor tiempo de vuelo y, luego, la más rápida de calcular.</p>` : ""}
    ${r.resiliencia.aviso ? `<p class="warn">${esc(r.resiliencia.aviso)}</p>` : ""}
    ${noVis.length ? `<p class="warn">Sin visitar: ${noVis.map(([c, m]) => `${esc(cameraName(c))} (${esc(m)})`).join("; ")}</p>` : ""}`;

  $("#plan-list").innerHTML = r.planes
    .map((p) => {
      const st = TECH[p.tecnica];
      const isBest = p.tecnica === r.mas_resiliente;
      const flights = p.vuelos
        .map((v, k) => `<li data-flight="${v.id}"><i class="dot" style="background:${shade(st.color, k, p.vuelos.length)}"></i>
          <span>Vuelo ${v.vuelo}: ${v.camaras.map(cameraName).join(" → ")} · ${num(v.tiempo_s / 60)} min · R ${num(v.R, 3)}</span></li>`)
        .join("");
      const meta = p.vuelos.length
        ? `${p.vuelos.length} vuelo${p.vuelos.length > 1 ? "s" : ""} · ${num(p.distancia_m / 1000, 1)} km · ${num(p.tiempo_s / 60)} min · ${num(p.tiempo_ms)} ms`
        : "Sin plan";
      return `<li class="plan ${isBest ? "best" : ""}" style="--c:${st.color}">
        <div class="plan-head"><input type="checkbox" data-plan="${p.tecnica}" ${state.visiblePlans.has(p.tecnica) ? "checked" : ""} aria-label="Mostrar en el mapa">
          <span class="name">${isBest ? "★ " : ""}${esc(p.etiqueta)}</span><span class="r">${p.R === null ? "—" : `R ${num(p.R, 3)}`}</span></div>
        <div class="meta">${meta}${p.delta_R && Math.abs(p.delta_R) > 1e-9 ? ` · ΔR ${p.delta_R > 0 ? "+" : ""}${num(p.delta_R, 3)}` : ""}</div>
        ${p.factible || !p.vuelos.length ? "" : `<div class="msg">${esc(p.mensaje)}</div>`}
        ${!p.vuelos.length ? `<div class="msg">${esc(p.mensaje)}</div>` : ""}
        ${p.vuelos.length ? `<details><summary>Ver vuelos</summary><ul class="flights">${flights}</ul></details>` : ""}
      </li>`;
    })
    .join("");
  $("#results").hidden = false;
  $("#fail-result").hidden = true;
  layers.failures.group.clearLayers();
}

async function planificar(ev) {
  ev?.preventDefault();
  showError("");
  if (state.mode === "camaras" && !state.cameras.size) {
    showError("Elige al menos una cámara en el mapa.");
    return;
  }
  const q = buildQuery();
  $("#plan-button").disabled = true;
  setStatus(q.modo === "parque" ? "Calculando todos los sectores… puede tardar unos segundos." : "Calculando las cuatro técnicas…");
  try {
    const [res, escenario] = await Promise.all([
      getJSON(`${MOTOR}/api/plan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(q) }),
      q.fecha ? getJSON(`${MOTOR}/api/escenario`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fecha: q.fecha }) }).catch(() => null) : null,
    ]);
    state.plan = res;
    state.lastQuery = q;
    const simulados = (q.focos_simulados || []).map((f) => ({ type: "Feature", geometry: { type: "Point", coordinates: [f.lon, f.lat] }, properties: { ...f, acquired_on: "foco simulado" } }));
    if (escenario) {
      drawFires({ type: "FeatureCollection", features: escenario.focos.map((f) => ({ type: "Feature", geometry: { type: "Point", coordinates: [f.lon, f.lat] }, properties: { ...f, acquired_on: f.fecha } })).concat(simulados) });
    } else {
      drawFires({ type: "FeatureCollection", features: state.data.fires.features.concat(simulados) });
    }
    renderResults();
    drawPlan();
    setStatus(`Plan listo · ${res.escenario.fecha_escenario ? `datos del ${res.escenario.fecha_escenario}` : "datos actuales"} · ${res.escenario.n_focos} focos, ${res.escenario.n_avistamientos} avistamientos de aves.`);
    updateCampaignTarget();
  } catch (err) {
    showError(`No se pudo planificar: ${err.message}`);
    setStatus("");
  } finally {
    $("#plan-button").disabled = false;
  }
}

async function cargarCaso() {
  try {
    const caso = await getJSON(`${MOTOR}/api/caso-ejemplo`);
    const q = caso.consulta;
    $("#sector-id").value = q.sector_id;
    setMode("sector");
    const r = q.restricciones || {};
    $("#forest-only").checked = !!r.solo_bosque;
    $("#avoid-trails").checked = !!r.evitar_senderos;
    $("#avoid-weather").checked = !!r.evitar_clima;
    $("#avoid-birds").checked = !!r.evitar_aves;
    state.dateMode = q.fecha ? "pick" : "now";
    $$("#date-picker button").forEach((b) => b.classList.toggle("active", b.dataset.date === state.dateMode));
    $("#date-box").hidden = state.dateMode !== "pick";
    if (q.fecha) $("#scenario-date").value = q.fecha;
    state.focosSimulados = q.focos_simulados || [];
    await planificar();
    setStatus(caso.simulado ? `Caso de ejemplo del ${caso.fecha}: ${caso.nota}` : `Caso de ejemplo con datos históricos reales del ${caso.fecha}.`);
  } catch (err) {
    showError(`No se pudo cargar el caso de ejemplo: ${err.message}`);
  }
}

async function simularFallas() {
  if (!state.plan) return;
  const vuelos = state.plan.planes
    .filter((p) => state.visiblePlans.has(p.tecnica))
    .flatMap((p) => p.vuelos.map((v) => ({ id: v.id, tecnica: p.tecnica, vuelo: v.vuelo, elementos: v.elementos })));
  try {
    const res = await getJSON(`${MOTOR}/api/fallas`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vuelos }) });
    layers.failures.group.clearLayers();
    const porTecnica = {};
    for (const v of res.vuelos) (porTecnica[v.tecnica] ||= []).push(v);
    const items = Object.entries(porTecnica).map(([tech, vs]) => {
      const p = state.plan.planes.find((x) => x.tecnica === tech);
      const ok = vs.every((v) => !v.falla);
      const det = vs.map((v) => `<li>Vuelo ${v.vuelo}: ${v.falla ? `<span class="fail">falla</span> (${v.fallan.map((e) => describeElement(e)).join(", ")})` : "se completa"}</li>`).join("");
      for (const v of vs) for (const e of v.fallan) drawFailure(e);
      return `<p><b>${esc(p.etiqueta)}</b>: ${ok ? "el plan se completa" : '<span class="fail">el plan no se completa</span>'}</p><ul>${det}</ul>`;
    });
    $("#fail-result").innerHTML = `<p class="hint">Cada elemento sortea un número entre 0 y 100: falla si sale menor o igual que 100 · p. Un vuelo falla si falla alguno de sus elementos.</p>${items.join("")}`;
    $("#fail-result").hidden = false;
  } catch (err) {
    showError(`No se pudo sortear: ${err.message}`);
  }
}

function describeElement(e) {
  const r = `r = ${num(e.r, 1)} ≤ ${num(e.umbral, 1)}`;
  if (e.tipo === "clima") return `clima, ${r}`;
  if (e.tipo === "nodo") return `${state.nodesById.get(e.id)?.is_camera ? `cámara ${cameraName(e.id)}` : `punto ${e.id}`}, ${r}`;
  return `tramo ${e.id}, ${r}`;
}

function drawFailure(e) {
  if (e.tipo === "arista") {
    const f = state.edgesById.get(e.id) || state.linksById?.get(e.id);
    if (f) L.geoJSON(f, { style: { color: "#b63a2b", weight: 8, opacity: 0.6 } }).addTo(layers.failures.group);
  } else if (e.tipo === "nodo") {
    const n = state.nodesById.get(e.id);
    if (n) L.marker([n.lat, n.lon], { icon: L.divIcon({ className: "", html: '<div style="width:14px;height:14px;background:#b63a2b;transform:rotate(45deg);border:2px solid #fff"></div>', iconSize: [14, 14] }) }).addTo(layers.failures.group);
  }
}

async function descargarKml() {
  if (!state.plan) return;
  const tech = state.plan.mas_resiliente || "dijkstra_distancia";
  const plan = state.plan.planes.find((p) => p.tecnica === tech);
  try {
    const res = await fetch(`${MOTOR}/api/kml`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan: { tecnica: plan.tecnica, vuelos: plan.vuelos.map(({ elementos, geojson, ...v }) => v) }, fecha: state.lastQuery?.fecha }) });
    if (!res.ok) throw new Error(`Error ${res.status}`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `vuelos_${tech}.zip`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) {
    showError(`No se pudo descargar: ${err.message}`);
  }
}

function updateCampaignTarget() {
  const q = state.lastQuery || buildQuery();
  const label = q.modo === "sector" ? `Sector ${q.sector_id}` : q.modo === "especie" ? `Especie: ${state.species.find((s) => s.cientifico === q.especie)?.comun || q.especie}` : q.modo === "camaras" ? `${(q.camaras || []).length} cámara(s)` : "Todo el parque";
  $("#campaign-target").innerHTML = `Monitorear: <b>${esc(label)}</b> (lo elegido en «Planificar»).`;
}

async function loadCapacity() {
  try {
    const c = await getJSON(`${MOTOR}/api/capacidad`);
    const rows = Object.entries(c.rondas)
      .map(([t, r]) => `<tr><td>${{ verano: "Verano", otono: "Otoño", invierno: "Invierno", primavera: "Primavera" }[t] || t} (${r.dias} mañanas volables)</td><td>${r.cubre_parque ? "todo el parque" : `${r.sectores.length} sectores`}</td></tr>`)
      .join("");
    $("#capacity-box").innerHTML = `<h3>Capacidad del equipo</h3>
      Una pasada por el parque son <b>${c.mananas_por_pasada} mañanas</b> × 3 visitas = <b>${c.dias_por_pasada} días de terreno</b> (${num(c.horas_vuelo_parque, 1)} h de vuelo).
      <table>${rows}</table><p class="hint">Cuando no alcanza, la mitad de los días va a los sectores más prioritarios y el resto a los pendientes.</p>`;
  } catch {
    $("#capacity-box").innerHTML = '<p class="hint">No se pudo calcular la capacidad.</p>';
  }
}

const ESTADO = { programada: "Programada", volada: "Volada", postergada: "Postergada", por_reprogramar: "Por reprogramar", completa: "Completa", incompleta: "Incompleta" };

async function loadCampaigns() {
  try {
    const res = await getJSON(`${MOTOR}/api/campanas`);
    const list = res.campanas;
    $("#campaign-tasks").textContent = res.tareas_de_hoy.length
      ? `Hoy toca revisar ${res.tareas_de_hoy.length} mañana(s) programada(s).`
      : list.length ? "" : "Todavía no hay campañas.";
    $("#campaign-list").innerHTML = list
      .slice()
      .reverse()
      .map((c) => {
        const pend = c.dias.find((d) => d.estado === "programada" || d.estado === "postergada");
        const visits = c.dias
          .sort((a, b) => a.visita - b.visita)
          .map((d) => `<li>Mañana ${d.visita} · ${esc(d.fecha)} <span class="badge ${d.estado}">${ESTADO[d.estado] || d.estado}</span>${d.decision ? `<span class="decision">${esc(d.decision)}</span>` : ""}</li>`)
          .join("");
        return `<li class="campaign"><div class="row-between"><h3>${esc(c.nombre)}</h3><span class="badge ${c.estado}">${ESTADO[c.estado] || c.estado}</span></div>
          <p class="hint">${esc(c.tipo)} · ${esc(c.temporada)} · hasta el ${esc(c.fecha_limite)}${c.motivo ? `<br>${esc(c.motivo)}` : ""}</p>
          <ul class="visits">${visits}</ul>
          <div class="buttons">
            ${pend ? `<button type="button" data-decide="${c.id}">Revisar amenazas y decidir</button><button type="button" data-flown="${c.id}:${pend.id}">Marcar mañana ${pend.visita} como volada</button>` : ""}
            <button type="button" data-reschedule="${c.id}">Reprogramar</button>
            <button type="button" data-kml="${c.id}">KML</button>
          </div></li>`;
      })
      .join("");
  } catch (err) {
    $("#campaign-status").textContent = `No se pudieron cargar las campañas: ${err.message}`;
  }
}

async function crearCampana(ev) {
  ev.preventDefault();
  const q = { ...(state.lastQuery || buildQuery()) };
  delete q.fecha;
  const dias = Number($("#campaign-days").value);
  try {
    const c = await getJSON(`${MOTOR}/api/campanas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consulta: q, fecha_inicio: $("#campaign-start").value, tipo: $("#campaign-type").value, dias_disponibles: dias }),
    });
    $("#campaign-status").innerHTML = `Campaña creada. El plan provisorio para la solicitud a la DGAC queda listo el <b>${esc(c.plan_provisorio)}</b>.${c.avisos.length ? `<br>${esc(c.avisos.join(" "))}` : ""}`;
    loadCampaigns();
  } catch (err) {
    $("#campaign-status").textContent = `No se pudo crear: ${err.message}`;
  }
}

async function campaignAction(target) {
  const post = (url, body) => getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  try {
    if (target.dataset.decide) {
      target.disabled = true;
      target.textContent = "Revisando…";
      const r = await post(`${MOTOR}/api/campanas/${target.dataset.decide}/decidir`);
      $("#campaign-status").textContent = r.decision;
    } else if (target.dataset.flown) {
      const [cid, did] = target.dataset.flown.split(":");
      await post(`${MOTOR}/api/campanas/${cid}/volada/${did}`);
    } else if (target.dataset.reschedule) {
      const fecha = prompt("Nueva fecha de la próxima mañana (AAAA-MM-DD)", new Date(Date.now() + 864e5 * 10).toISOString().slice(0, 10));
      if (!fecha) return;
      await post(`${MOTOR}/api/campanas/${target.dataset.reschedule}/reprogramar`, { fecha });
    } else if (target.dataset.kml) {
      window.location.href = `${MOTOR}/api/campanas/${target.dataset.kml}/kml`;
      return;
    }
    loadCampaigns();
  } catch (err) {
    $("#campaign-status").textContent = err.message;
  }
}

function buildLayerList() {
  $("#layer-list").innerHTML = Object.entries(layers)
    .map(([k, l]) => `<label class="check"><input type="checkbox" data-layer="${k}" ${l.on ? "checked" : ""}><span>${l.name}</span></label>`)
    .join("");
}

function bindEvents() {
  $$(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
      $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${t.dataset.tab}`));
      if (t.dataset.tab === "campaigns") {
        updateCampaignTarget();
        loadCampaigns();
      }
    }),
  );
  $("#mode-picker").addEventListener("click", (e) => e.target.dataset.mode && setMode(e.target.dataset.mode));
  $("#date-picker").addEventListener("click", (e) => {
    if (!e.target.dataset.date) return;
    state.dateMode = e.target.dataset.date;
    $$("#date-picker button").forEach((b) => b.classList.toggle("active", b === e.target));
    $("#date-box").hidden = state.dateMode !== "pick";
  });
  $("#sector-id").addEventListener("change", () => {
    updateModeInfo();
    focusSector($("#sector-id").value);
  });
  $("#species-id").addEventListener("change", updateModeInfo);
  $("#theta").addEventListener("input", () => ($("#theta-value").textContent = thetaLabel(Number($("#theta").value))));
  $("#plan-form").addEventListener("submit", planificar);
  $("#threat-clear").addEventListener("click", () => setThreat(null));
  $("#example-button").addEventListener("click", cargarCaso);
  $("#mode-picker").addEventListener("click", () => (state.focosSimulados = []));
  $("#sector-id").addEventListener("change", () => (state.focosSimulados = []));
  $("#fail-button").addEventListener("click", simularFallas);
  $("#kml-button").addEventListener("click", descargarKml);
  $("#campaign-form").addEventListener("submit", crearCampana);
  $("#campaign-days").addEventListener("input", () => {
    const d = Math.max(1, Math.min(3, Number($("#campaign-days").value) || 3));
    $("#campaign-form button.primary").textContent = d >= 3 ? "Programar 3 mañanas" : `Programar ${d} mañana${d > 1 ? "s" : ""} (campaña parcial)`;
  });
  $("#campaign-list").addEventListener("click", (e) => e.target.closest("button") && campaignAction(e.target.closest("button")));
  $("#panel-toggle").addEventListener("click", () => $("#panel").classList.toggle("collapsed"));
  $("#camera-chips").addEventListener("click", (e) => e.target.dataset.removeCamera && toggleCamera(Number(e.target.dataset.removeCamera)));
  $("#plan-list").addEventListener("change", (e) => {
    const t = e.target.dataset.plan;
    if (!t) return;
    if (e.target.checked) state.visiblePlans.add(t);
    else state.visiblePlans.delete(t);
    drawPlan();
  });
  $("#layer-list").addEventListener("change", (e) => {
    const l = layers[e.target.dataset.layer];
    if (!l) return;
    l.on = e.target.checked;
    if (l.on) l.group.addTo(map);
    else map.removeLayer(l.group);
  });
  map.on("popupopen", (e) => {
    const el = e.popup.getElement();
    el.querySelectorAll("[data-threat-edge]").forEach((b) => b.addEventListener("click", () => setThreat(Number(b.dataset.threatEdge))));
    el.querySelectorAll("[data-plan-sector]").forEach((b) =>
      b.addEventListener("click", () => {
        $("#sector-id").value = b.dataset.planSector;
        setMode("sector");
        map.closePopup();
        planificar();
      }),
    );
    el.querySelectorAll("[data-toggle-camera]").forEach((b) =>
      b.addEventListener("click", () => {
        toggleCamera(Number(b.dataset.toggleCamera));
        map.closePopup();
      }),
    );
  });
}

async function init() {
  bindEvents();
  buildLayerList();
  renderChips();
  const start = new Date(Date.now() + 864e5 * 12);
  $("#campaign-start").value = start.toISOString().slice(0, 10);
  try {
    const [nodes, edges, links, trails, fires, ebird, meteo] = await Promise.all(
      ["nodes", "edges", "links", "trails", "fires", "ebird", "meteo"].map((k) => getJSON(`/api/${k}`)),
    );
    state.data = { nodes, edges, links, trails, fires, ebird, meteo };
    for (const f of nodes.features) state.nodesById.set(f.properties.id, { ...f.properties, lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] });
    for (const f of edges.features) state.edgesById.set(f.properties.id, f);
    state.linksById = new Map(links.features.map((f) => [f.properties.id, f]));
    for (const f of links.features) state.edgesById.set(f.properties.id, f);
  } catch (err) {
    setStatus("");
    showError(`No se pudo leer la base de datos: ${err.message}. Revisa que Docker esté arriba y que los datos estén cargados.`);
    return;
  }
  try {
    const [sectores, especies, bases] = await Promise.all([getJSON(`${MOTOR}/api/sectores`), getJSON(`${MOTOR}/api/especies`), getJSON(`${MOTOR}/api/bases`)]);
    state.sectors = sectores.sectores;
    state.species = especies.especies;
    state.bases = bases.bases;
  } catch (err) {
    drawStatic();
    setStatus("");
    showError(`El motor de planificación no responde (${MOTOR}): ${err.message}.`);
    return;
  }
  drawStatic();
  fillSelects();
  const todas = L.featureGroup([...state.sectorShapes.values()]);
  if (todas.getLayers().length) map.fitBounds(todas.getBounds().pad(0.05));
  setStatus(`${state.sectors.length} sectores y ${state.data.nodes.features.filter((f) => f.properties.is_camera).length} cámaras. Elige qué monitorear y presiona «Planificar vuelos».`);
  fetch(`${MOTOR}/api/caso-ejemplo`).then((r) => ($("#example-button").hidden = !r.ok)).catch(() => {});
  loadCapacity();
}

init();
