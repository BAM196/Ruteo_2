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
      `<strong>Alerta Meteorológica</strong><br>` +
        `Temp: ${props.temperature ?? "s/d"} °C<br>` +
        `Humedad: ${props.humidity ?? "s/d"}%<br>` +
        `Viento: ${props.wind_speed ?? "s/d"} km/h`,
    );
  },
}).addTo(map);

const routeLayer = L.geoJSON(null, {
  style: {color: "#d4652f", weight: 5, opacity: 0.95},
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
  startSelect.replaceChildren(
    ...options.map((option) => option.cloneNode(true)),
  );
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
  const query =
    startId && goalId ? `?start_id=${startId}&goal_id=${goalId}` : "";
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
    ["#toggle-trails", trailsLayer],
    ["#toggle-ebird", ebirdLayer],
    ["#toggle-fires", firesLayer],
    ["#toggle-meteo", meteoLayer],
    ["#toggle-route", routeLayer],
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

    fillCameras(nodes.features);
    const route = await drawRoute();

    const bounds = nodesLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.08));
    }

    const fireText = fires.features.length
      ? `${fires.features.length} focos FIRMS`
      : "sin focos activos";
    const meteoText = meteo.features.length
      ? `${meteo.features.length} alertas`
      : "sin alertas";
    const ebirdText = ebird.features.length
      ? `${ebird.features.length} aves detectadas`
      : "sin amenazas de aves";

    summary.textContent =
      `${nodes.features.length} cámaras · ` +
      `${trails.features.length} senderos/hitos · ` +
      `${cameraName(nodes.features, route.start_id)} a ${cameraName(nodes.features, route.goal_id)} · ` +
      `${route.distance_km} km · ${fireText} · ${meteoText}· ${ebirdText}`;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      showError("");
      routeButton.disabled = true;
      try {
        const nextRoute = await drawRoute(startSelect.value, goalSelect.value);
        summary.textContent =
          `${cameraName(nodes.features, nextRoute.start_id)} a ` +
          `${cameraName(nodes.features, nextRoute.goal_id)} · ${nextRoute.distance_km} km. ` +
          "Solo distancia, sin cobertura, senderos ni amenazas aplicadas.";
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
