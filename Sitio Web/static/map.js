const LAND_COVER_COLORS = {
  10: "#2f6b45",
  30: "#c6a317",
  80: "#2a6f97",
};

const MOTOR_URL = `${window.location.protocol}//${window.location.hostname}:8001`;
const DEFAULT_START = 16;
const DEFAULT_GOAL = 22;
const DEFAULT_THREAT_EDGE = 27;

const TECHNIQUES = {
  dijkstra_distancia: {color: "#d4652f", weight: 13},
  milp: {color: "#2563eb", weight: 10},
  dijkstra_ponderado: {color: "#16a34a", weight: 6},
  aco: {color: "#f0abfc", weight: 2.5},
};

const startSelect = document.querySelector("#start-id");
const goalSelect = document.querySelector("#goal-id");
const excludeSelect = document.querySelector("#exclude-ids");
const thetaInput = document.querySelector("#theta");
const thetaValue = document.querySelector("#theta-value");
const autonomyInput = document.querySelector("#autonomy");
const forestOnly = document.querySelector("#forest-only");
const threatBox = document.querySelector("#threat-box");
const threatEdge = document.querySelector("#threat-edge");
const threatP = document.querySelector("#threat-p");
const summary = document.querySelector("#route-summary");
const errorBox = document.querySelector("#route-error");
const routeButton = document.querySelector("#route-button");
const form = document.querySelector("#route-form");
const routesBox = document.querySelector("#routes-box");
const routesList = document.querySelector("#routes-list");
const routesWinner = document.querySelector("#routes-winner");

const map = L.map("map", {zoomControl: true});
L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  {attribution: "Imágenes Esri, Maxar, Earthstar Geographics"},
).addTo(map);
L.tileLayer(
  "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png",
  {attribution: "&copy; OpenStreetMap, &copy; CARTO", pane: "shadowPane"},
).addTo(map);

const edgesLayer = L.geoJSON(null, {
  style: (feature) => ({
    color: feature.properties.exceeds_max ? "#f0d78c" : "#f7f3ea",
    weight: feature.properties.exceeds_max ? 2 : 1.4,
    opacity: 0.85,
  }),
  onEachFeature: (feature, layer) => {
    const kind = feature.properties.kind === "conexion" ? "puente" : "vecino";
    const limit = feature.properties.exceeds_max ? " Supera 3 km." : "";
    layer.bindPopup(`${feature.properties.cost_km} km · ${kind}.${limit}`);
  },
}).addTo(map);

const nodesLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 7,
      color: "#f7f3ea",
      weight: 2,
      fillColor:
        LAND_COVER_COLORS[feature.properties.land_cover_code] || "#8d8478",
      fillOpacity: 1,
    }),
  onEachFeature: (feature, layer) => {
    const props = feature.properties;
    const species = (props.species || [])
      .slice(0, 4)
      .map((item) => item.common || item.scientific)
      .join(", ");
    const note = props.pixel_note ? `<br>${props.pixel_note}` : "";
    layer.bindPopup(
      `<strong>${props.name}</strong><br>` +
        `${props.land_cover_label || "Sin cobertura"}<br>` +
        `${species || "Sin especies"}<br>` +
        `${props.records} registros${note}`,
    );
  },
}).addTo(map);

const trailsLayer = L.geoJSON(null, {
  style: () => ({
    color: "#d97706",
    weight: 3.5,
    dashArray: "6, 6",
    opacity: 0.9,
  }),
  pointToLayer: (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 5,
      color: "#ffffff",
      weight: 1.5,
      fillColor: "#b45309",
      fillOpacity: 0.95,
    }),
  onEachFeature: (feature, layer) => {
    const props = feature.properties;
    const len =
      props.length_km > 0 ? `<br>Longitud: ${props.length_km} km` : "";
    const desc = props.description
      ? `<br><small>${props.description}</small>`
      : "";
    layer.bindPopup(
      `<strong>${props.name}</strong> (${props.type})${len}${desc}`,
    );
  },
}).addTo(map);

const ebirdLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 7,
      color: "#ffffff",
      weight: 2,
      fillColor: "#7c3aed",
      fillOpacity: 0.9,
    }),
  onEachFeature: (feature, layer) => {
    const props = feature.properties;
    layer.bindPopup(
      `<strong>⚠️ Amenaza aérea: ${props.common_name || "Rapaz / Gaviota"}</strong><br>` +
        `<em>${props.scientific_name}</em><br>` +
        `Fecha: ${props.observed_at || "Reciente"} · Cantidad: ${props.count || 1}<br>` +
        `Localidad: ${props.location || "Sector parque"}`,
    );
  },
}).addTo(map);

const firesLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 9,
      color: "#d4652f",
      weight: 2,
      fillColor: "#ffb020",
      fillOpacity: 0.9,
    }),
  onEachFeature: (feature, layer) => {
    const props = feature.properties;
    layer.bindPopup(
      `<strong>Foco ${props.id}</strong><br>` +
        `${props.acquired_on || "sin fecha"} · confianza ${props.confidence || "s/d"}<br>` +
        `FRP ${props.frp ?? "s/d"} MW`,
    );
  },
}).addTo(map);

const meteoLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 8,
      color: "#1d4ed8",
      weight: 2,
      fillColor: "#3b82f6",
      fillOpacity: 0.85,
    }),
  onEachFeature: (feature, layer) => {
    const props = feature.properties;
    layer.bindPopup(
      `<strong>Clima en la cámara</strong><br>` +
        `Temp: ${props.temperature ?? "s/d"} °C<br>` +
        `Humedad: ${props.humidity ?? "s/d"}%<br>` +
        `Viento: ${props.wind_speed ?? "s/d"} m/s`,
    );
  },
}).addTo(map);

const routeLayers = {};
const threatLayer = L.geoJSON(null, {
  style: {color: "#dc2626", weight: 7, opacity: 1, dashArray: "4, 9"},
}).addTo(map);

let cameras = [];
let edgeFeatures = [];

function showError(message) {
  errorBox.hidden = !message;
  errorBox.textContent = message || "";
}

function cameraName(id) {
  const match = cameras.find((feature) => feature.properties.id === id);
  return match ? match.properties.name : `Cámara ${id}`;
}

function option(value, text) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = text;
  return el;
}

function fillCameras(features) {
  const make = () => features.map((f) => option(f.properties.id, `${f.properties.id} · ${f.properties.name}`));
  startSelect.replaceChildren(...make());
  goalSelect.replaceChildren(...make());
  excludeSelect.replaceChildren(...make());
  if (features.some((f) => f.properties.id === DEFAULT_START)) startSelect.value = String(DEFAULT_START);
  if (features.some((f) => f.properties.id === DEFAULT_GOAL)) goalSelect.value = String(DEFAULT_GOAL);
}

function fillEdges(features) {
  const options = [option("", "Ninguno")].concat(
    features.map((f) =>
      option(
        f.properties.id,
        `${f.properties.id} · ${cameraName(f.properties.source)} – ${cameraName(f.properties.target)}`,
      ),
    ),
  );
  threatEdge.replaceChildren(...options);
  if (features.some((f) => f.properties.id === DEFAULT_THREAT_EDGE)) {
    threatEdge.value = String(DEFAULT_THREAT_EDGE);
  }
}

async function readJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    const text = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : payload.error;
    throw new Error(text || "No se pudo completar la consulta.");
  }
  return payload;
}

function buildQuery() {
  const query = {
    origen_id: Number(startSelect.value),
    destino_id: Number(goalSelect.value),
    theta: Number(thetaInput.value),
    autonomia_m: autonomyInput.value ? Number(autonomyInput.value) : null,
    restricciones: {
      solo_bosque: forestOnly.checked,
      excluir_nodos: Array.from(excludeSelect.selectedOptions).map((o) => Number(o.value)),
    },
    overrides_prob: {},
  };
  if (threatBox.open && threatEdge.value) {
    query.overrides_prob = {aristas: {[threatEdge.value]: Number(threatP.value)}};
  }
  return query;
}

function drawThreat(query) {
  threatLayer.clearLayers();
  const ids = Object.keys((query.overrides_prob || {}).aristas || {}).map(Number);
  edgeFeatures
    .filter((f) => ids.includes(f.properties.id))
    .forEach((f) => threatLayer.addData(f));
}

function clearRoutes() {
  Object.values(routeLayers).forEach((layer) => map.removeLayer(layer));
  Object.keys(routeLayers).forEach((key) => delete routeLayers[key]);
  routesList.replaceChildren();
}

function formatR(value) {
  return value.toFixed(3).replace(".", ",");
}

function drawRoutes(payload) {
  clearRoutes();
  const order = ["dijkstra_distancia", "milp", "dijkstra_ponderado", "aco"];
  const routes = [...payload.rutas].sort((a, b) => order.indexOf(a.tecnica) - order.indexOf(b.tecnica));
  const tie = (payload.resiliencia && payload.resiliencia.empate_en_R) || [];

  routes.forEach((route) => {
    const style = TECHNIQUES[route.tecnica] || {color: "#444", weight: 4};
    if (route.geojson) {
      routeLayers[route.tecnica] = L.geoJSON(route.geojson, {
        style: {
          color: style.color,
          weight: style.weight,
          opacity: 0.95,
          dashArray: route.factible ? null : "10, 8",
        },
        onEachFeature: (_feature, layer) =>
          layer.bindPopup(
            `<strong>${route.etiqueta}</strong><br>` +
              `${route.leyenda}<br>` +
              `Cámaras: ${route.nodos.join(" → ")}<br>` +
              (route.factible ? "Factible" : `No factible: ${route.mensaje}`),
          ),
      }).addTo(map);
    }

    const item = document.createElement("li");
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = Boolean(route.geojson);
    box.disabled = !route.geojson;
    box.addEventListener("change", () => {
      const layer = routeLayers[route.tecnica];
      if (!layer) return;
      if (box.checked) layer.addTo(map);
      else map.removeLayer(layer);
    });
    const swatch = document.createElement("i");
    swatch.className = "swatch line";
    swatch.style.background = style.color;
    const text = document.createElement("span");
    const winner = route.tecnica === payload.mas_resiliente;
    const tied = tie.includes(route.tecnica);
    text.textContent = `${winner || tied ? "★ " : ""}${route.leyenda}`;
    label.append(box, swatch, text);
    item.append(label);
    if (!route.factible) {
      const note = document.createElement("small");
      note.className = "route-note";
      note.textContent = route.mensaje;
      item.append(note);
    }
    if (winner || tied) item.classList.add("best");
    routesList.append(item);
  });

  const winnerRoute = routes.find((r) => r.tecnica === payload.mas_resiliente);
  if (!winnerRoute) {
    routesWinner.textContent = "Ninguna ruta es factible con estas condiciones.";
  } else if (tie.length > 1) {
    const names = routes.filter((r) => tie.includes(r.tecnica)).map((r) => r.etiqueta);
    routesWinner.textContent = `Más resilientes (empate en R = ${formatR(winnerRoute.R)}): ${names.join(", ")}.`;
  } else {
    routesWinner.textContent = `Más resiliente: ${winnerRoute.etiqueta} (R = ${formatR(winnerRoute.R)}).`;
  }
  routesBox.hidden = false;

  const group = L.featureGroup(Object.values(routeLayers));
  if (group.getLayers().length) map.fitBounds(group.getBounds().pad(0.3));
}

async function computeRoutes() {
  showError("");
  if (startSelect.value === goalSelect.value) {
    showError("El origen y el destino son la misma cámara.");
    return;
  }
  routeButton.disabled = true;
  summary.textContent = "Calculando las cuatro rutas…";
  const query = buildQuery();
  try {
    const payload = await readJson(`${MOTOR_URL}/api/rutas`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(query),
    });
    drawRoutes(payload);
    drawThreat(query);
    threatLayer.bringToFront();
    const p = payload.parametros;
    summary.textContent =
      `${cameraName(p.origen)} a ${cameraName(p.destino)} · θ = ${String(p.theta).replace(".", ",")} · ` +
      `autonomía ${Math.round(p.d_max_m).toLocaleString("es-CL")} m`;
  } catch (error) {
    summary.textContent = "No se pudieron calcular las rutas.";
    showError(
      error instanceof TypeError
        ? `No hay conexión con el motor en ${MOTOR_URL}. ¿Está corriendo el contenedor "motor"?`
        : error.message,
    );
  } finally {
    routeButton.disabled = false;
  }
}

function bindToggles() {
  const pairs = [
    ["#toggle-edges", edgesLayer],
    ["#toggle-nodes", nodesLayer],
    ["#toggle-trails", trailsLayer],
    ["#toggle-ebird", ebirdLayer],
    ["#toggle-fires", firesLayer],
    ["#toggle-meteo", meteoLayer],
  ];
  pairs.forEach(([selector, layer]) => {
    const el = document.querySelector(selector);
    if (el) {
      el.addEventListener("change", (event) => {
        if (event.target.checked) {
          layer.addTo(map);
        } else {
          map.removeLayer(layer);
        }
      });
    }
  });
}

async function loadPark() {
  showError("");
  routeButton.disabled = true;
  try {
    const [nodes, edges, fires, meteo, trails, ebird] = await Promise.all([
      readJson("/api/nodes"),
      readJson("/api/edges"),
      readJson("/api/fires"),
      readJson("/api/meteo"),
      readJson("/api/trails"),
      readJson("/api/ebird"),
    ]);

    nodesLayer.addData(nodes);
    edgesLayer.addData(edges);
    firesLayer.addData(fires);
    meteoLayer.addData(meteo);
    trailsLayer.addData(trails);
    ebirdLayer.addData(ebird);

    cameras = nodes.features;
    edgeFeatures = edges.features;
    fillCameras(cameras);
    fillEdges(edgeFeatures);

    const bounds = nodesLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.08));
    }

    const fireText = fires.features.length
      ? `${fires.features.length} focos FIRMS`
      : "sin focos activos";
    const ebirdText = ebird.features.length
      ? `${ebird.features.length} avistamientos de aves`
      : "sin amenazas de aves";

    summary.textContent =
      `${nodes.features.length} cámaras · ${trails.features.length} senderos/hitos · ` +
      `${fireText} · ${meteo.features.length} lecturas de clima · ${ebirdText}. ` +
      "Elige origen y destino y calcula las rutas.";
  } catch (error) {
    summary.textContent = "No se pudo cargar el parque.";
    showError(error.message);
  } finally {
    routeButton.disabled = false;
  }
}

thetaInput.addEventListener("input", () => {
  thetaValue.textContent = Number(thetaInput.value).toFixed(2).replace(".", ",");
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  computeRoutes();
});

bindToggles();
loadPark();
