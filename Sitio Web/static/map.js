const LAND_COVER_COLORS = {
  10: "#2f6b45",
  30: "#c6a317",
  80: "#2a6f97",
};

const startSelect = document.querySelector("#start-id");
const goalSelect = document.querySelector("#goal-id");
const summary = document.querySelector("#route-summary");
const errorBox = document.querySelector("#route-error");
const routeButton = document.querySelector("#route-button");
const form = document.querySelector("#route-form");

const map = L.map("map", { zoomControl: true });
L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Imágenes Esri, Maxar, Earthstar Geographics" }
).addTo(map);
L.tileLayer(
  "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png",
  { attribution: "&copy; OpenStreetMap, &copy; CARTO", pane: "shadowPane" }
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
  pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
    radius: 7,
    color: "#f7f3ea",
    weight: 2,
    fillColor: LAND_COVER_COLORS[feature.properties.land_cover_code] || "#8d8478",
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
      `${props.records} registros${note}`
    );
  },
}).addTo(map);

const firesLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
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
      `FRP ${props.frp ?? "s/d"} MW`
    );
  },
}).addTo(map);

const routeLayer = L.geoJSON(null, {
  style: { color: "#d4652f", weight: 5, opacity: 0.95 },
}).addTo(map);

function showError(message) {
  errorBox.hidden = !message;
  errorBox.textContent = message || "";
}

function fillCameras(features) {
  const options = features.map((feature) => {
    const option = document.createElement("option");
    option.value = feature.properties.id;
    option.textContent = feature.properties.name;
    return option;
  });
  startSelect.replaceChildren(...options.map((option) => option.cloneNode(true)));
  goalSelect.replaceChildren(...options);
}

function cameraName(features, id) {
  const match = features.find((feature) => feature.properties.id === id);
  return match ? match.properties.name : `Cámara ${id}`;
}

async function readJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "No se pudo completar la consulta.");
  }
  return payload;
}

async function drawRoute(startId, goalId) {
  const query = startId && goalId ? `?start_id=${startId}&goal_id=${goalId}` : "";
  const payload = await readJson(`/api/route${query}`);
  routeLayer.clearLayers();
  if (payload.geometry) {
    routeLayer.addData({
      type: "Feature",
      geometry: payload.geometry,
      properties: {},
    });
  }
  startSelect.value = String(payload.start_id);
  goalSelect.value = String(payload.goal_id);
  return payload;
}

function bindToggles() {
  const pairs = [
    ["#toggle-edges", edgesLayer],
    ["#toggle-nodes", nodesLayer],
    ["#toggle-fires", firesLayer],
    ["#toggle-route", routeLayer],
  ];
  pairs.forEach(([selector, layer]) => {
    document.querySelector(selector).addEventListener("change", (event) => {
      if (event.target.checked) {
        layer.addTo(map);
      } else {
        map.removeLayer(layer);
      }
    });
  });
}

async function loadPark() {
  showError("");
  routeButton.disabled = true;
  try {
    const [nodes, edges, fires] = await Promise.all([
      readJson("/api/nodes"),
      readJson("/api/edges"),
      readJson("/api/fires"),
    ]);
    nodesLayer.addData(nodes);
    edgesLayer.addData(edges);
    firesLayer.addData(fires);
    fillCameras(nodes.features);
    const route = await drawRoute();
    const bounds = nodesLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.08));
    }
    const fireText = fires.features.length
      ? `${fires.features.length} focos`
      : "sin focos activos";
    summary.textContent =
      `${nodes.features.length} cámaras · ` +
      `${cameraName(nodes.features, route.start_id)} a ${cameraName(nodes.features, route.goal_id)} · ` +
      `${route.distance_km} km · ${fireText}`;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      showError("");
      routeButton.disabled = true;
      try {
        const nextRoute = await drawRoute(startSelect.value, goalSelect.value);
        summary.textContent =
          `${cameraName(nodes.features, nextRoute.start_id)} a ` +
          `${cameraName(nodes.features, nextRoute.goal_id)} · ${nextRoute.distance_km} km. ` +
          "Solo distancia, sin cobertura ni incendios.";
      } catch (error) {
        showError(error.message);
      } finally {
        routeButton.disabled = false;
      }
    });
  } catch (error) {
    summary.textContent = "No se pudo cargar el parque.";
    showError(error.message);
  } finally {
    routeButton.disabled = false;
  }
}

bindToggles();
loadPark();
