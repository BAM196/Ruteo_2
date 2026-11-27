# WildWard

**Planificación resiliente de vuelos de dron para el monitoreo de fauna en el Parque Nacional Pumalín Douglas Tompkins.**

WildWard planifica misiones de un dron con cámara térmica que sale desde donde está el operador, recorre el entorno de las cámaras trampa de CONAF y vuelve, en uno o varios vuelos cortos. Para planificar tiene en cuenta:

- la batería del dron;
- el relieve;
- la normativa de la DGAC;
- las restricciones que elija el usuario;
- las amenazas del día: incendios, mal clima y aves.

Compara cuatro técnicas de ruteo y entrega la que tiene más probabilidad de completar el recorrido.

El sistema entrega información para la preservación de especies a quienes pueden actuar sobre ella, como los encargados del parque y CONAF. No vuela el dron, no detecta animales en las imágenes y no decide acciones de conservación.

---

## Índice

1. [El problema](#el-problema)
2. [Qué hace el sistema](#qué-hace-el-sistema)
3. [Datos que usa](#datos-que-usa)
4. [Cómo funciona](#cómo-funciona)
5. [Cómo usar: terminal](#cómo-usar-terminal)
6. [Cómo usar: sitio web](#cómo-usar-sitio-web)
7. [Estructura del repositorio](#estructura-del-repositorio)
8. [Decisiones y sus fuentes](#decisiones-y-sus-fuentes)
9. [Limitaciones](#limitaciones)
10. [Referencias](#referencias)

---

## El problema

El Parque Pumalín (Región de Los Lagos) tiene 48 cámaras trampa de CONAF que registran fauna de interés para su conservación. La categoría de cada especie sale de la nómina oficial del Reglamento de Clasificación de Especies (RCE) para Los Lagos:

- **Especies objetivo:** el pudú, Vulnerable (VU), y la güiña y el puma, Casi amenazados (NT).
- **Especies que presionan a la fauna nativa:** las cámaras también registran especies domésticas o exóticas, como perros, vacas, liebres europeas y visones americanos.

Una cámara trampa solo ve un punto fijo y cuenta muchas veces al mismo animal, así que no sirve para estimar cuántos individuos hay. Revisar a pie el entorno de cada cámara es lento en un terreno de fiordos y bosque.

Un dron térmico muestrea ese entorno en minutos (Chang et al., 2025). Pero una misión puede fallar por un incendio cercano, por viento, lluvia o temperatura fuera de los límites del dron, o por aves que lo atacan o que él perturba. Una misión que falla son datos de monitoreo que no se obtienen.

**Pregunta que responde el sistema:** ¿cómo planificar los vuelos para que vuelvan con los datos aunque haya amenazas en el camino?

---

## Qué hace el sistema

1. **Arma sectores de monitoreo.** Agrupa las cámaras que se pueden atender desde una sola base sin mover al operador, y les asigna una prioridad según qué especies hay que proteger y qué las presiona.
2. **Elige la base del operador.** Es un punto al que se llega a pie (junto a una cámara, sobre un sendero o en la caminata entre dos cámaras) desde el que se ven las cámaras del sector.
3. **Planifica los vuelos con cuatro técnicas:** `pgr_dijkstra` por distancia, Gurobi (MILP), `pgr_dijkstra` ponderado y una colonia de hormigas (ACO). Cada vuelo sale de la base, muestrea un bloque de 200 × 200 m alrededor de cada cámara y vuelve, sin pasarse de la batería.
4. **Mide la resiliencia.** Calcula R, la probabilidad de completar cada vuelo y el plan completo, la valida con Monte Carlo y marca la técnica más resiliente.
5. **Programa campañas.** Cada campaña son 3 mañanas seguidas por sector. El sistema arma el plan provisorio 7 días hábiles antes, para la solicitud a la DGAC. La noche anterior y al amanecer decide si se vuela o se posterga con el pronóstico del día, y exporta los waypoints a KML para cargarlos en el dron.

Todo se usa desde un sitio web con un mapa.

---

## Datos que usa

Ningún dato necesita una cuenta de Google ni credenciales pagadas. Las únicas claves son las gratuitas de FIRMS y eBird.

| Dato                         | Fuente y acceso                                                                                                                                                              | Script                                | Para qué                                              |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | ----------------------------------------------------- |
| Cámaras y registros de fauna | Programa de fotomonitoreo de objetos de conservación y amenazas en el SNAP (CONAF, GBIF Chile, v1.9, CC BY-NC 4.0; `data/occurrence.zip`), filtrado a las cámaras de Pumalín | `Infraestructura/generar_nodos_v2.py` | Red de cámaras y waypoints; especies por cámara       |
| Elevación (30 m)             | Copernicus DEM GLO-30, bucket público en AWS                                                                                                                                 | `Metadata/extraer_dem.py`             | Perfil de cada tramo, altura de vuelo, línea de vista |
| Cobertura de suelo (10 m)    | ESA WorldCover 2021, bucket público en AWS                                                                                                                                   | `Metadata/extraer_worldcover.py`      | Restricción "volar solo sobre bosque"                 |
| Senderos oficiales           | KML de senderos del parque (`Metadata/Senderos.kml`)                                                                                                                         | `Metadata/extraer_senderos.py`        | Bases del operador; evitar sobrevolar visitantes      |
| Categoría de conservación    | Nómina RCE del Ministerio del Medio Ambiente (20º proceso)                                                                                                                   | `Metadata/especies_rce.py`            | Especies objetivo, pesos de la prioridad              |
| Catálogo de fauna            | Inventario de especies del parque (`data/…Especies.csv`)                                                                                                                     | `Metadata/extraer_fauna.py`           | Referencia de especies                                |
| Incendios                    | NASA FIRMS, VIIRS 375 m (clave gratuita)                                                                                                                                     | `Amenazas/extraer_firms.py`           | Amenaza de incendio                                   |
| Clima                        | Open-Meteo: pronóstico y reanálisis histórico                                                                                                                                | `Amenazas/extraer_meteo.py`           | Viento, temperatura y lluvia en la mañana             |
| Aves                         | eBird API 2.0 (clave gratuita)                                                                                                                                               | `Amenazas/extraer_ebird.py`           | Amenaza de aves grandes o territoriales               |
| Traslados entre bases        | OSRM (caminos de OpenStreetMap)                                                                                                                                              | `Infraestructura/traslados_bases.py`  | Cuántos sectores caben en una mañana                  |

Cada archivo JSON del proyecto tiene al lado un `*_estructura.md` que explica cada campo.

### Especies registradas por las cámaras

| Especie         | Origen           | Registros | Cámaras | Categoría en Los Lagos | Peso w  |
| --------------- | ---------------- | --------- | ------- | ---------------------- | ------- |
| Pudú            | Nativa           | 2.528     | 32      | VU                     | 3       |
| Güiña           | Nativa           | 546       | 26      | NT                     | 2       |
| Puma            | Nativa           | 166       | 11      | NT                     | 2       |
| Zorro culpeo    | Nativa           | 236       | 5       | LC                     | 1       |
| Quique          | Nativa           | 50        | 5       | LC                     | 1       |
| Perro doméstico | Doméstica        | 71        | 5       | —                      | presión |
| Vaca            | Doméstica        | 5.050     | 5       | —                      | presión |
| Liebre europea  | Exótica          | 264       | 2       | —                      | presión |
| Visón americano | Exótica invasora | 12        | 1       | —                      | presión |

El peso es w = 1 + peso del Red List Index (Butchart et al., 2007). La UICN bajó a la güiña a Preocupación menor en 2025, pero en Chile rige la categoría del RCE.

---

## Cómo funciona

### Terreno y altura

- **Altura de vuelo:** 80 m sobre la superficie, la altura validada por Chang et al. (2025) con el mismo dron. Queda bajo el techo de 120 m de la DAN 151.
- **Densificación:** si la recta entre dos puntos pasa a menos de 24,5 m de las copas, el tramo se densifica para seguir el relieve. Los 24,5 m suman el error del DEM, el error del dron y un margen por árboles altos.
- **Bloqueo:** un tramo se bloquea si exige pasar los 120 m.
- **Línea de vista:** se calcula sobre el DEM. Un tramo tapado por un cerro desde la base no se vuela desde esa base.

### Radio de operación: 1.500 m

La DAN 91 exige autorización caso a caso y no fija distancias fuera de zonas pobladas. La única cifra publicada por la DGAC es la de la DAN 151: hasta 1.500 m en línea de vista, con un máximo de dos observadores. Volar más allá de la línea de vista está reservado a servicio público. El valor se puede configurar.

### Sectores y prioridad

- **Partición exacta:** el menor número de grupos de cámaras que una sola base deja dentro del radio y a la vista. Con los datos reales salen 33 sectores: 21 de una cámara, 9 de dos y 3 de tres.
- **Cámaras sin base:** dos cámaras no tienen ninguna base desde la que se vea su bloque completo. El sistema lo informa.
- **Prioridad:** 100 · (V̂ + P̂) / 2.
  - **V:** valor de conservación, la suma de los pesos de las especies nativas por la fracción de cámaras que las registraron.
  - **P:** fracción de cámaras con especies exóticas o domésticas.
  - El riesgo de vuelo no entra en la prioridad: se muestra aparte, como R.

### Batería y vuelos

- **Batería útil:** 38 min de vuelo estacionario (ficha DJI) menos la reserva para el peor regreso, 9,3 min. Quedan 28,7 min por vuelo.
- **Muestreo:** cada cámara se muestrea en unos 9 minutos, con 25 fotos térmicas cada 50 m a 3 m/s.
- **Varios vuelos:** si un sector no cabe en una batería, se hacen varios vuelos con cambio de batería en la base.

### Amenazas

Cada probabilidad es la probabilidad de que ocurra, durante el vuelo, la condición que hace fallar al dron:

| Amenaza     | Probabilidad                                                                     | De dónde sale cada valor                                                                                                                                                       |
| ----------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Incendio    | P(foco real ∣ confianza) · máx(0, 1 − d / 1.000 m)                               | Tasa de falsas alarmas de VIIRS; 265 m de incertidumbre del píxel más distancia al humo                                                                                        |
| Viento      | 1 − Φ((12 − g₈₀) / 3,1), con g₈₀ = g₁₀ · 8^0,25                                  | Límite de 12 m/s de la ficha DJI; ley de potencia con α de "Wooded countryside, many trees" (Masters, 2004); σ del modelo de climatología como peor caso (Harris y Kahl, 2017) |
| Temperatura | Probabilidad de salir de −10 a 40 °C                                             | Ficha DJI                                                                                                                                                                      |
| Lluvia      | Probabilidad de lluvia del pronóstico (1 o 0 en histórico)                       | El dron no es resistente al agua                                                                                                                                               |
| Aves        | 1 − (1 − p_i)ⁿ, con p_i = 0,5 · recencia · máx(0, 1 − d / R) y R = 100 m + r_mov | Vas et al. (2015); r_mov = desplazamiento típico de las aves del parque                                                                                                        |

Las amenazas se combinan como independientes: q = 1 − Π(1 − q_k). El clima cuenta una vez por vuelo, con el peor valor del recorrido, porque es el mismo viento para todo el vuelo.

### Las cuatro técnicas

Todas usan la misma matriz de tramos entre la base y las cámaras, calculada con `pgr_dijkstra`.

| Técnica                    | Cómo arma los vuelos                                                                                            |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `pgr_dijkstra` (distancia) | Tramos más cortos y vecino más cercano. Ignora el riesgo: es la referencia                                      |
| Gurobi (MILP)              | Orden y reparto en vuelos óptimos, con batería y R mínima opcional                                              |
| `pgr_dijkstra` (ponderado) | Tramos con el costo del modelo y vecino más cercano                                                             |
| ACO                        | Colonia de hormigas que vuelve a la base cuando no le alcanza la batería (Zhang et al., 2018; Mai et al., 2023) |

El costo del modelo combina tiempo y riesgo con un peso θ: c = (1 − θ) · t / t_ref + θ · (−ln(1 − p)). El detalle de cada técnica está en [Motor/README.md](Motor/README.md).

### Resiliencia

- **R de un vuelo:** el producto de (1 − p) de todo lo que recorre.
- **R del plan:** el producto de las R de sus vuelos.
- **Validación:** se valida con 10.000 sorteos de Monte Carlo.
- **Umbral:** R del plan ≥ 0,9. Si ningún plan lo alcanza, el sistema sugiere otra base o postergar.

### Frecuencia del monitoreo

- **Por qué 3 mañanas seguidas por sector:** un animal presente no siempre se detecta, y los modelos de ocupación necesitan visitas repetidas en un periodo corto (MacKenzie et al., 2002). Con 3 queda una visita de respaldo.
- **Por qué en la mañana:** la imagen térmica pierde contraste cuando el suelo se calienta.
- **Una ronda por temporada:** si los días de terreno no alcanzan para todo el parque, la mitad va a los sectores más prioritarios y el resto a los pendientes, para que ningún sector quede sin visitar.
- **Costo de una pasada:** con los traslados medidos, una pasada por el parque cuesta 42 días de terreno (14 mañanas × 3).

---

## Cómo usar: terminal

### Requisitos

- **Python 3.12**, con los paquetes de `requirements.txt`.
- **Docker Desktop**, o Docker con Compose.
- **Claves gratuitas:**
  - [NASA FIRMS (MAP_KEY)](https://firms.modaps.eosdis.nasa.gov/api/map_key/).
  - [eBird](https://ebird.org/api/keygen). Sin la clave de eBird el sistema usa los avistamientos que ya trae el repositorio.

### Instalación

```bash
git clone <url-del-repositorio>
cd Ruteo_2
pip install -r requirements.txt
cp .env.example .env
```

Completa `.env` con tu contraseña de la base y tus claves:

```ini
POSTGRES_PASSWORD=elige_una_contraseña
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB=gisdb
POSTGRES_USER=gisuser
FIRMS_MAP_KEY=tu_clave_de_firms
EBIRD_API_KEY=tu_clave_de_ebird
```

### Levantar todo con un comando

```bash
python main.py
```

`main.py` hace todo en orden:

1. Descomprime `data/occurrence.zip`.
2. Genera la red de cámaras y tramos.
3. Descarga el DEM y la cobertura de suelo.
4. Calcula los perfiles de los tramos y las bases.
5. Cruza las especies con el RCE.
6. Extrae incendios, clima y aves.
7. Levanta Docker.
8. Carga la base.
9. Arma los sectores y calcula las probabilidades de falla.

Al terminar muestra:

```text
Listo. El sitio está en http://127.0.0.1:8000 y la API del motor en http://127.0.0.1:8001/docs.
```

Opciones:

| Comando                           | Qué hace                                                                          |
| --------------------------------- | --------------------------------------------------------------------------------- |
| `python main.py --sin-extraccion` | No descarga nada: levanta Docker y carga los datos que ya están en el repositorio |
| `python main.py --sin-red`        | Mantiene la red de cámaras y tramos del repositorio                               |

Si falla una fuente externa de amenazas (por ejemplo, falta una clave), `main.py` avisa y sigue con el archivo que ya está en el repositorio.

### Servicios

| Servicio      | Dirección                  | Qué es                                  |
| ------------- | -------------------------- | --------------------------------------- |
| Sitio web     | http://127.0.0.1:8000      | Mapa y planificador (Flask + Leaflet)   |
| Motor         | http://127.0.0.1:8001/docs | API de planificación (FastAPI + Gurobi) |
| Base de datos | `localhost:5433`           | PostgreSQL 17 con PostGIS y pgRouting   |

```bash
docker compose up -d        # levantar
docker compose ps           # ver estado
docker compose logs motor   # ver registros del motor
docker compose down         # apagar (los datos quedan en el volumen)
```

### Escenarios de una fecha pasada

Las tres extracciones de amenazas aceptan una fecha. Con ella cargan los incendios, el clima y las aves de ese día:

```bash
python Amenazas/extraer_firms.py --fecha 2024-02-10
python Amenazas/extraer_meteo.py --fecha 2024-02-10
python Amenazas/extraer_ebird.py --fecha 2024-02-10
python Amenazas/cargar_firms.py && python Amenazas/cargar_meteo.py && python Amenazas/cargar_ebird.py
docker compose run --rm motor python -m motor.probabilidades --cargar
```

No hace falta hacerlo a mano para planificar ya que el sitio tiene un campo de fecha que hace lo mismo sin tocar la base.

### Otros comandos útiles

```bash
docker compose run --rm motor python -m pytest -q             # tests del motor
docker compose run --rm motor python -m motor.evaluacion      # calibración del ACO y sensibilidad
docker compose run --rm motor python -m motor.buscar_caso     # buscar caso histórico
docker compose run --rm motor python -m motor.capacidad       # mañanas, días por pasada y rondas
docker compose run --rm motor python -m motor.programador     # revisar hoy las campañas programadas
python Infraestructura/traslados_bases.py                     # medir traslados entre bases (OSRM)
```

Los resultados de la evaluación quedan en `Motor/resultados/`.

---

## Cómo usar: sitio web

Abre http://127.0.0.1:8000. A la izquierda está el panel y a la derecha el mapa del parque. El panel tiene tres pestañas.

### Pestaña Planificar

**1. ¿Qué quieres monitorear?** Elige uno de cuatro modos:

| Modo                        | Para qué sirve                                                                                                                                 |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Un sector** (por defecto) | Monitorear un sector. La lista viene ordenada por prioridad y muestra las especies predominantes, las objetivo con su categoría y las exóticas |
| **Una especie**             | Seguir una especie: se visitan solo las cámaras que la registraron. Se muestra su categoría, su comportamiento y sus amenazas                  |
| **Cámaras**                 | Mirar donde ya sabes que hay algo, como un registro reciente o una exótica nueva. Toca las cámaras en el mapa para agregarlas o quitarlas      |
| **Todo el parque**          | Un plan completo: todos los sectores, cada uno desde su base                                                                                   |

**2. ¿Con qué datos?**

- **Datos actuales:** usa los incendios, el pronóstico de la próxima mañana y las aves cargados en la base.
- **Otra fecha:** elige un día pasado para planificar con los incendios, el clima y las aves de ese día.

**3. Opciones (opcional).** Se despliegan al tocarlas:

- **Base del operador:** automática (la más cercana a las cámaras) o una de las que ven todas las cámaras elegidas.
- **Más corto ↔ más seguro:** el peso θ entre tiempo de vuelo y riesgo.
- **Restricciones:**
  - volar solo sobre bosque;
  - evitar senderos con visitantes;
  - evitar mal clima, es decir, nodos y tramos donde la condición de falla es más probable que no;
  - evitar zonas con aves.
- **No visitar estas cámaras:** selección múltiple.
- **Amenaza simulada:** toca un tramo en el mapa y elige _Simular amenaza en este tramo_. Luego ajusta la probabilidad.

**Planificar vuelos** calcula las cuatro técnicas. Aparecen:

- **Resumen:** base elegida, cantidad de cámaras y sectores, la técnica más resiliente ★ con su probabilidad de completar el plan, y avisos. Por ejemplo, si ningún plan alcanza R ≥ 0,9 o si alguna cámara no se puede visitar y por qué.
- **Planes por técnica:** cada tarjeta tiene su color y muestra vuelos, kilómetros, minutos, R del plan, tiempo de cálculo y ΔR contra la técnica 1.
  - El casillero muestra u oculta el plan en el mapa.
  - _Ver vuelos_ lista cada vuelo con sus cámaras, su duración y su R.
- **Simular fallas:** sortea un número entre 0 y 100 para cada punto, tramo y clima de cada vuelo visible. Un elemento falla si el número sale menor o igual que 100 · p. Muestra qué vuelos se completan y marca en rojo en el mapa lo que falló.
- **Descargar vuelos (KML):** baja un ZIP con:
  - un KML por vuelo de la técnica más resiliente, con waypoints, alturas, velocidades y fotos, en el formato de DJI Pilot;
  - los datos para la solicitud a la DGAC: zona, radio en millas náuticas, altura en pies y tipo de vuelo.

En el mapa aparecen los vuelos de cada técnica, la base con su radio de 1.500 m, los bloques de muestreo y los tramos bloqueados desde esa base.

### Pestaña Campañas

- **Capacidad del equipo:** cuántas mañanas y días de terreno cuesta una pasada por el parque, y cuántos sectores entran en cada temporada.
- **Nueva campaña:** usa lo que elegiste en _Planificar_.
  1. Elige la primera mañana, los días de terreno disponibles y el motivo: ronda, después de un incendio, especie exótica nueva o revisión puntual.
  2. Se programan 3 mañanas seguidas. Con menos días queda como campaña parcial, y el sector pasa primero en la ronda siguiente.
  3. El sistema avisa la fecha del plan provisorio para la DGAC, 7 días hábiles antes.
- **Cada campaña muestra** sus mañanas con su estado (programada, volada, postergada o por reprogramar) y la última decisión. Tiene estos botones:
  - **Revisar amenazas y decidir:** recalcula el plan con el pronóstico de esa mañana y dice si se vuela o se posterga. El sistema también lo hace solo la noche anterior y al amanecer.
  - **Marcar mañana como volada.**
  - **Reprogramar:** mueve las mañanas pendientes a otra fecha.
  - **KML** de la campaña.

### Pestaña Mapa

- **Capas:** prende o apaga sectores, cámaras, vuelos, bases, radio, bloques, tramos bloqueados, tramos de la red, senderos, incendios, aves, clima, amenaza simulada y fallas sorteadas.
- **Leyenda** de colores.
- **Fondo del mapa:** el botón de la esquina del mapa cambia entre relieve, satélite y calles.

**Ventanas emergentes del mapa:**

- **Cámara:** cobertura, elevación, especies registradas con su categoría, y un botón para planificar su sector o agregarla a la selección.
- **Tramo:** largo en vuelo, ascenso, despeje sobre el terreno, si sigue el relieve, si está bloqueado y su probabilidad de falla, con un botón para simular una amenaza.
- **Sector:** prioridad, especies y base, con un botón para planificarlo.
- **Incendio, ave y clima:** datos de cada lectura.

---

## Estructura del repositorio

```text
Infraestructura/   red de cámaras y tramos, perfiles sobre el terreno, bases y traslados
Metadata/          DEM, cobertura de suelo, senderos, especies RCE y catálogo de fauna
Amenazas/          incendios (FIRMS), clima (Open-Meteo), aves (eBird) y r_mov
Motor/             motor de planificación (FastAPI + Gurobi), configuración, tests y resultados
Sitio Web/         sitio Flask + Leaflet
Diagrama/          esquema de la base (schema.sql) y versión para dbdiagram.io
data/              datos de entrada (GBIF, inventario de especies) y descargas
main.py            arma todo de punta a punta
docker-compose.yaml
```

### Tablas principales de la base

| Tabla                                                        | Contenido                                               |
| ------------------------------------------------------------ | ------------------------------------------------------- |
| `nodos`, `aristas`, `nodo_especie`                           | Red de cámaras, waypoints y tramos; especies por cámara |
| `metadata_cobertura`                                         | Cobertura de suelo y elevación de cada nodo             |
| `arista_perfil`                                              | Largo 3D, ascenso, despeje y geometría 3D de cada tramo |
| `bases`, `base_camara`, `base_enlace`, `base_arista_visible` | Bases, qué cámaras y tramos ve cada una                 |
| `sectores`, `sector_camara`                                  | Sectores, su base y su prioridad                        |
| `especie_rce`                                                | Categoría RCE, peso, origen y fichas                    |
| `metadata_senderos*`, `metadata_fauna`                       | Senderos y catálogo de fauna                            |
| `amenazas_firms*`, `meteo_alertas*`, `amenazas_ebird*`       | Amenazas                                                |
| `prob_fallo_nodo`, `prob_fallo_arista` (+ vistas `_total`)   | Probabilidad de falla                                   |
| `campanas`, `campana_dia`                                    | Campañas y sus mañanas                                  |

---

## Decisiones y sus fuentes

| Decisión              | Valor                                      | Regla                                                                                                                                                                                                           | Fuente                                                   |
| --------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Dron                  | DJI Mavic 3T                               | Cámara térmica, validado para fauna                                                                                                                                                                             | Chang et al. (2025)                                      |
| Batería               | 38 min                                     | Tiempo en vuelo estacionario, porque el muestreo es estacionario                                                                                                                                                | Ficha DJI                                                |
| Velocidad de traslado | 9 m/s                                      | Velocidad a la que DJI mide su autonomía                                                                                                                                                                        | Ficha DJI                                                |
| Reserva               | 9,3 min                                    | Peor regreso desde el borde del radio con viento al límite                                                                                                                                                      | Ficha DJI, DAN 151                                       |
| Radio de operación    | 1.500 m                                    | Única cifra publicada por la DGAC para línea de vista con observadores                                                                                                                                          | DAN 91 y DAN 151                                         |
| Altura de vuelo       | 80 m sobre la superficie                   | Validada en terreno, bajo el techo de 120 m                                                                                                                                                                     | Chang et al. (2025), DAN 151                             |
| Despeje mínimo        | 24,5 m                                     | Error del DEM + error del dron + margen por árboles                                                                                                                                                             | Copernicus DEM, ficha DJI                                |
| Muestreo              | 25 puntos cada 50 m, 534 s                 | Promedio de los 9 vuelos del paper base (8 min 30 s a 10 min 2 s)                                                                                                                                               | Chang et al. (2025), Tabla 1                             |
| Tamaño del sector     | D = 2 (1.500 − 141) m                      | Todo el sector cabe en el radio desde una base                                                                                                                                                                  | Lógica del modelo                                        |
| Bases                 | Cámaras, senderos y caminata entre cámaras | Lugares a los que se llega a pie                                                                                                                                                                                | Datos del proyecto                                       |
| Peso de especie       | 1 + RLI                                    | Escala estándar de riesgo de extinción                                                                                                                                                                          | Butchart et al. (2007), RCE                              |
| Radio de incendio     | 1.000 m                                    | 265 m de incertidumbre del píxel más distancia al humo                                                                                                                                                          | Schroeder et al. (2014)                                  |
| Foco real             | 0,988 (nominal y alta), 0,6 (baja)         | 1 − tasa de falsas alarmas                                                                                                                                                                                      | Schroeder et al. (2014), ATBD VIIRS                      |
| Viento                | α = 0,25, σ = 3,1 m/s                      | α: fila "Wooded countryside, many trees" de la ley de potencia. σ: desviación estándar del sesgo del modelo de climatología, usada como peor caso (los modelos de factor de ráfaga tienen σ de 0,87 a 0,98 m/s) | Masters (2004), Tabla 6.3; Harris y Kahl (2017), Tabla 2 |
| Radio de aves         | 100 m + r_mov                              | Distancia de precaución más desplazamiento del ave                                                                                                                                                              | Vas et al. (2015), Reusch et al. (2020)                  |
| p₀ de aves            | 0,5                                        | Principio de razón insuficiente                                                                                                                                                                                 | Lógica del modelo                                        |
| Visitas por campaña   | 3                                          | 2 es el mínimo para separar presencia de detección; 3 deja respaldo                                                                                                                                             | MacKenzie et al. (2002), Chang et al. (2025)             |
| Anticipación          | 7 días hábiles                             | Plazo de la solicitud de autorización                                                                                                                                                                           | DAN 91, Anexo D                                          |
| Umbral de resiliencia | R del plan ≥ 0,9                           | Objetivo del plan completo                                                                                                                                                                                      | Decisión del modelo                                      |
| Monte Carlo           | 10.000 sorteos                             | Intervalo de 95 % de ± 0,01                                                                                                                                                                                     | Estadística                                              |

**Valores sin fuente directa.** Tienen análisis de sensibilidad en `Motor/resultados/` (`python -m motor.evaluacion`):

- p₀ de aves, r_mov y el radio de incendio;
- α del viento;
- los pesos de la prioridad;
- la regla mixta del 50 %;
- el tiempo de cambio de batería;
- el peso θ.

---

## Limitaciones

- **El DEM es de superficie y de 30 m.** El ojo del operador se pone 1,7 m sobre esa superficie, como si estuviera en un claro. Bajo el dosel la vista real es menor.
- **Gurobi es exacto sobre el grafo reducido** (base y cámaras con tramos precalculados), no sobre toda la red.
- **Las amenazas se combinan como independientes.** Si se correlacionan, el riesgo calculado es una cota superior.
- **Las probabilidades no están calibradas con fallas reales de vuelo:** son reglas explícitas con su fuente o con sensibilidad.
- **OSRM no ve accesos por mar ni el estado de los senderos.** Esos traslados hay que confirmarlos en terreno.
- **El vuelo lo hace siempre un piloto,** con autorización de la DGAC y de CONAF. El sistema planifica y recomienda; no despega el dron.

---

## Referencias

**Paper base y métodos**

- Chang, B. et al. (2025). Enhancing Wildlife Detection Using Thermal Imaging Drones: Designing the Flight Path. _Drones_, 9(1), 52. https://doi.org/10.3390/drones9010052
- Mai, X., Dong, N. y Chen, H. (2023). UAV path planning based on a dual-strategy ant colony optimization algorithm. _Intelligence & Robotics_, 3(4), 666-684.
- Zhang, S., Gajpal, Y., Appadoo, S. S. y Abdulkader, M. M. S. (2018). Electric vehicle routing problem with recharging stations for minimizing energy consumption. _International Journal of Production Economics_, 203, 404-413.
- Dorigo, M. y Gambardella, L. M. (1997). Ant Colony System: a cooperative learning approach to the traveling salesman problem. _IEEE Transactions on Evolutionary Computation_, 1(1), 53-66.
- Miller, C. E., Tucker, A. W. y Zemlin, R. A. (1960). Integer programming formulation of traveling salesman problems. _Journal of the ACM_, 7(4), 326-329.
- Butchart, S. H. M. et al. (2007). Improvements to the Red List Index. _PLoS ONE_, 2(1), e140.
- MacKenzie, D. I. et al. (2002). Estimating site occupancy rates when detection probabilities are less than one. _Ecology_, 83(8), 2248-2255.

**Amenazas**

- Schroeder, W. et al. (2014). The New VIIRS 375 m active fire detection data product. _Remote Sensing of Environment_, 143, 85-96.
- Vas, E. et al. (2015). Approaching birds with drones: first experiments and ethical guidelines. _Biology Letters_, 11(2), 20140754.
- Reusch, K. et al. (2020). Foraging movements of breeding Kelp Gulls in South Africa. _Movement Ecology_, 8(1).
- Masters, G. M. (2004). _Renewable and Efficient Electric Power Systems_ (1.ª ed.). Wiley. Sec. 6.4, ec. (6.15) y Tabla 6.3, pp. 319-320.
- Harris, A. R. y Kahl, J. D. W. (2017). Gust factors: Meteorologically stratified climatology, data artifacts, and utility in forecasting peak gusts. _Journal of Applied Meteorology and Climatology_, 56(12), 3151-3166. https://doi.org/10.1175/JAMC-D-17-0133.1

**Normativa y especies**

- DGAC. DAN 91, Reglas del Aire (art. 91.102 y Anexo D).
- DGAC. DAN 151, Operaciones de aeronaves pilotadas a distancia sobre áreas pobladas (art. 151.103 y 151.105).
- Ministerio del Medio Ambiente. Nómina de especies según estado de conservación, hasta el 20º proceso del RCE. https://clasificacionespecies.mma.gob.cl/
- Fichas RCE del pudú, la güiña y el puma; Freer (2004); Elbroch et al. (2009); Animal Diversity Web.

**Datos**

- Copernicus DEM GLO-30 y ESA WorldCover en AWS Open Data.
- Corporación Nacional Forestal (2024). Programa de fotomonitoreo de objetos de conservación y amenazas en el Sistema Nacional de Áreas Protegidas (SNAP). Version 1.9. Occurrence dataset. http://gbif-chile.mma.gob.cl/ipt/resource?r=fotomonitoreo_conaf_2021&v=1.9 (clave GBIF 9f7ed5a4-f73a-4d74-b0be-cef5bd700a37, licencia CC BY-NC 4.0).
- NASA FIRMS, Open-Meteo, eBird API 2.0 y OSRM.
