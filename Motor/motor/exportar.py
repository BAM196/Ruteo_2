import io
import zipfile
from datetime import date
from xml.sax.saxutils import escape

from .config import parametros_mision
from .mision import bloques

PIE_POR_M = 3.28084
M_POR_MN = 1852.0


def _elev(esc, nodo) -> float:
    return float(esc.nodos[nodo].get("elevacion_m") or 0.0)


def waypoints(esc, vuelo: dict, m: dict | None = None) -> list:
    m = m or parametros_mision()
    base = vuelo["nodos"][0]
    e_op = _elev(esc, base)
    camaras = set(vuelo["camaras"])
    puntos, hechos = [], set()

    def agregar(lon, lat, altura, velocidad, acciones=None, nombre=None):
        puntos.append({"lon": round(lon, 7), "lat": round(lat, 7), "altura_m": round(max(altura, 5.0), 1),
                       "velocidad": velocidad, "acciones": acciones or [], "nombre": nombre})

    n0 = esc.nodos[base]
    agregar(n0["lon"], n0["lat"], m["altura"], m["v_c"], nombre="Base")
    for k, aid in enumerate(vuelo["aristas"]):
        a = esc.aristas[aid]
        u, v = vuelo["nodos"][k], vuelo["nodos"][k + 1]
        pts = a.get("puntos") or [[*c, _elev(esc, u) + m["altura"]] for c in a["coords"]]
        if u != a["source"]:
            pts = list(reversed(pts))
        for p in pts[1:]:
            agregar(p[0], p[1], p[2] - e_op, m["v_c"])
        if v in camaras and v not in hechos:
            hechos.add(v)
            n = esc.nodos[v]
            e_cam = _elev(esc, v)
            for i, (lo, la, _h) in enumerate(bloques.puntos(n["lon"], n["lat"], m)):
                acciones = (["GimbalPitch:-90"] if i == 0 else []) + ["Hovering:1000", "ShootPhoto"]
                agregar(lo, la, e_cam + m["altura"] - e_op, 3.0, acciones, f"{n.get('nombre')} {i + 1}")
    if not vuelo["aristas"] and vuelo["camaras"]:
        n = esc.nodos[vuelo["camaras"][0]]
        for i, (lo, la, _h) in enumerate(bloques.puntos(n["lon"], n["lat"], m)):
            acciones = (["GimbalPitch:-90"] if i == 0 else []) + ["Hovering:1000", "ShootPhoto"]
            agregar(lo, la, m["altura"], 3.0, acciones, f"{n.get('nombre')} {i + 1}")
    return puntos


def _accion(texto: str) -> str:
    nombre, _, param = texto.partition(":")
    if nombre == "Hovering":
        return f'<mis:actions param="{param}" accuracy="0" cameraIndex="0" payloadType="0" payloadIndex="0">Hovering</mis:actions>'
    if nombre == "GimbalPitch":
        return f'<mis:actions param="{param}" accuracy="1" cameraIndex="0" payloadType="0" payloadIndex="0">GimbalPitch</mis:actions>'
    return '<mis:actions param="0" accuracy="0" cameraIndex="0" payloadType="0" payloadIndex="0">ShootPhoto</mis:actions>'


def kml_vuelo(esc, vuelo: dict, nombre: str, m: dict | None = None) -> str:
    pts = waypoints(esc, vuelo, m)
    marcas = []
    for i, p in enumerate(pts, start=1):
        acciones = "".join(_accion(a) for a in p["acciones"])
        marcas.append(f"""
      <Placemark>
        <name>Waypoint{i}</name>
        <visibility>1</visibility>
        <description>{escape(p['nombre'] or '')}</description>
        <styleUrl>#waypointStyle</styleUrl>
        <ExtendedData xmlns:mis="www.dji.com">
          <mis:useWaylineAltitude>false</mis:useWaylineAltitude>
          <mis:heading>0</mis:heading>
          <mis:turnMode>Auto</mis:turnMode>
          <mis:gimbalPitch>-90.0</mis:gimbalPitch>
          <mis:useWaylineSpeed>false</mis:useWaylineSpeed>
          <mis:speed>{float(p['velocidad']):.1f}</mis:speed>
          <mis:useWaylineHeadingMode>true</mis:useWaylineHeadingMode>
          <mis:useWaylinePointType>true</mis:useWaylinePointType>
          <mis:pointType>LineStop</mis:pointType>
          <mis:cornerRadius>0.2</mis:cornerRadius>{acciones}
        </ExtendedData>
        <Point>
          <altitudeMode>relativeToGround</altitudeMode>
          <coordinates>{p['lon']},{p['lat']},{p['altura_m']}</coordinates>
        </Point>
      </Placemark>""")
    linea = " ".join(f"{p['lon']},{p['lat']},{p['altura_m']}" for p in pts)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document xmlns="">
    <name>{escape(nombre)}</name>
    <open>1</open>
    <ExtendedData xmlns:mis="www.dji.com">
      <mis:type>Waypoint</mis:type>
      <mis:stationType>0</mis:stationType>
    </ExtendedData>
    <Style id="waylineGreenPoly"><LineStyle><color>FF0AEE8B</color><width>6</width></LineStyle></Style>
    <Style id="waypointStyle"><IconStyle><Icon><href>https://cdnimg.dji.com/g/kml/flighthub/point.png</href></Icon></IconStyle></Style>
    <Folder>
      <name>Waypoints</name>
      <description>Waypoints del vuelo. Alturas relativas al despegue (Chang et al., 2025, Ec. 4).</description>{''.join(marcas)}
    </Folder>
    <Placemark>
      <name>Wayline</name>
      <visibility>1</visibility>
      <styleUrl>#waylineGreenPoly</styleUrl>
      <ExtendedData xmlns:mis="www.dji.com">
        <mis:altitude>{parametros_mision()['altura']:.1f}</mis:altitude>
        <mis:autoFlightSpeed>{parametros_mision()['v_c']:.1f}</mis:autoFlightSpeed>
        <mis:actionOnFinish>GoHome</mis:actionOnFinish>
        <mis:headingMode>UsePointSetting</mis:headingMode>
        <mis:gimbalPitchMode>UsePointSetting</mis:gimbalPitchMode>
        <mis:powerSaveMode>false</mis:powerSaveMode>
        <mis:waypointType>LineStop</mis:waypointType>
        <mis:droneInfo><mis:droneType>COMMON</mis:droneType><mis:advanceSettings>false</mis:advanceSettings><mis:droneCameras/><mis:droneHeight><mis:useAbsolute>false</mis:useAbsolute><mis:hasTakeoffHeight>false</mis:hasTakeoffHeight><mis:takeoffHeight>0.0</mis:takeoffHeight></mis:droneHeight></mis:droneInfo>
      </ExtendedData>
      <LineString>
        <tessellate>1</tessellate>
        <altitudeMode>relativeToGround</altitudeMode>
        <coordinates>{linea}</coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""


def anexo_d(esc, bases: list, fecha: str | None, m: dict | None = None) -> list:
    m = m or parametros_mision()
    salida = []
    for b in bases:
        salida.append({
            "zona": {"centro": {"lat": b["lat"], "lon": b["lon"]}, "radio_mn": round(m["r_op"] / M_POR_MN, 2),
                     "base": b.get("nombre")},
            "altura_pies_sobre_terreno": round(m["altura"] * PIE_POR_M),
            "altura_maxima_pies": round(120 * PIE_POR_M),
            "tipo_vuelo": "VLOS (línea de vista visual, hasta dos observadores)",
            "aeronave": "DJI Mavic 3T",
            "fecha": fecha or date.today().isoformat(),
            "horario": f"desde el amanecer + {m['inicio_ventana_min']} min, {m['ventana_h']:.1f} h",
            "proposito": "Monitoreo de fauna con cámara térmica",
            "anticipacion": f"{m['anticipacion_dias_habiles']} días hábiles (DAN 91, Anexo D, punto 10)",
        })
    return salida


def zip_plan(esc, plan: dict, fecha: str | None = None) -> bytes:
    buf = io.BytesIO()
    bases = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for v in plan["vuelos"]:
            nombre = f"{plan.get('tecnica', 'plan')}_vuelo_{v['vuelo']:02d}"
            z.writestr(f"{nombre}.kml", kml_vuelo(esc, v, nombre))
            b = esc.nodos[v["nodos"][0]]
            bases[v["nodos"][0]] = {"lat": b["lat"], "lon": b["lon"], "nombre": b.get("nombre")}
        import json

        z.writestr("solicitud_dgac.json", json.dumps(anexo_d(esc, list(bases.values()), fecha),
                                                     ensure_ascii=False, indent=2))
    return buf.getvalue()
