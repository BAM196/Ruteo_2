# Motor de planificación de misiones

Servicio en Python que arma las misiones del dron: sectores, base del operador, vuelos de ida y vuelta, las cuatro técnicas de ruteo, la probabilidad de falla y la resiliencia de cada plan. Corre en Docker, en el puerto 8001, con FastAPI y Gurobi. El sitio web lo consulta por HTTP.

La guía general del proyecto, con la instalación, el uso del sitio y las fuentes, está en el [README principal](../README.md). Este archivo explica el motor por dentro.

## Cómo se corre

```bash
docker compose up -d                                              # base, sitio y motor
docker compose run --rm motor python -m motor.mision.sectores --cargar
docker compose run --rm motor python -m motor.probabilidades --cargar
docker compose run --rm motor python -m pytest -q                 # tests
docker compose run --rm motor python -m motor.evaluacion          # calibración y sensibilidad
docker compose run --rm motor python -m motor.buscar_caso         # caso de ejemplo histórico
docker compose run --rm motor python -m motor.capacidad           # mañanas y rondas
docker compose run --rm motor python -m motor.programador         # tareas de las campañas de hoy
```

Sin Docker, desde `Motor/`, se puede trabajar con los JSON del repositorio en vez de la base:

```bash
pip install -r requirements.txt
MOTOR_FUENTE=json python -m pytest -q
MOTOR_FUENTE=json python -m motor.mision.sectores
```

La documentación interactiva de la API queda en http://127.0.0.1:8001/docs.

## Estructura

| Archivo | Qué hace |
| --- | --- |
| `config/amenazas.yaml` | Parámetros de cada amenaza, cada uno con `valor`, `fuente` y `justificacion` |
| `config/mision.yaml` | Dron, radio de operación, altura, muestreo, prioridad, campañas y resiliencia |
| `config/aco.yaml` | `config_mai`, `config_zhang` y la grilla de calibración |
| `config/caso_ejemplo.json` | Caso de ejemplo elegido por `buscar_caso.py` |
| `motor/grafo.py` | Carga la red (cámaras, waypoints, tramos con perfil, bases, especies y amenazas) desde la base o desde los JSON |
| `motor/probabilidades.py` | Probabilidad de falla por nodo y tramo |
| `motor/escenarios.py` | Amenazas de una fecha: histórico para fechas pasadas, pronóstico para próximas |
| `motor/mision/sectores.py` | Partición exacta en sectores y su prioridad |
| `motor/mision/bases.py` | Elección de la base del operador |
| `motor/mision/bloques.py` | Bloques de muestreo de 5 × 5 puntos alrededor de cada cámara |
| `motor/mision/bateria.py` | Tiempo de vuelo, reserva y batería útil |
| `motor/mision/prioridad.py` | Valor de conservación, presión de exóticas y Kendall |
| `motor/rutas/comun.py` | Consulta, contexto de amenazas, problema por sector, tramos y evaluación de un plan |
| `motor/rutas/matriz.py` | Matriz de tramos con `pgr_dijkstra` (muchos a muchos) o Dijkstra en Python |
| `motor/rutas/dijkstra_distancia.py` | Técnica 1 |
| `motor/rutas/milp.py` | Técnica 2 (Gurobi) |
| `motor/rutas/dijkstra_ponderado.py` | Técnica 3 |
| `motor/rutas/aco.py` | Técnica 4 |
| `motor/resiliencia.py` | R por vuelo y por plan, Monte Carlo, sorteo de fallas y leyenda |
| `motor/servicio.py` | Une todo: modo → sectores → base → técnicas → resiliencia |
| `motor/capacidad.py` | Tiempo por sector, mañanas, días por pasada y rondas por temporada |
| `motor/programador.py` | Campañas: plan provisorio, decisión de volar o postergar, reprogramación |
| `motor/exportar.py` | KML de waypoints por vuelo y datos para la solicitud a la DGAC |
| `motor/buscar_caso.py` | Búsqueda del caso de ejemplo |
| `motor/evaluacion.py` | Calibración del ACO y análisis de sensibilidad |
| `motor/api.py` | API |
| `tests/` | Tests con un sector de juguete (`grafo_juguete.json`) y con la base real |

## Flujo de una consulta

1. **El modo define las cámaras.**
   - Sector: las de un sector.
   - Especie: las que registraron la especie.
   - Cámaras: una o varias, elegidas por el usuario.
   - Todo el parque: las 48.
2. **Las cámaras se agrupan en sectores.** En modo sector y parque se usan los sectores precalculados. En los otros modos se aplica la misma partición a las cámaras elegidas.
3. **Cada sector se atiende desde una base.** Es la candidata que deja todas las cámaras a ≤ 1.359 m y a la vista, con la menor suma de distancias. El usuario puede elegir otra.
4. **Se arma el problema del sector.** Solo cuentan los tramos volables desde esa base: dentro del radio, sin cerros que corten la línea de vista y sin bloqueo por altura. También se quitan los tramos y nodos excluidos por las restricciones del usuario.
5. **Las cuatro técnicas arman sus vuelos.**
6. **Se miden la R de cada vuelo y del plan,** se valida con Monte Carlo y se marca la técnica más resiliente.

## Batería

$$\sum_{(i,j) \in \text{vuelo}} \left(\frac{d_{ij}}{v_c} + \frac{\Delta h^+_{ij}}{v_{sub}}\right) + \sum_{i \in \text{vuelo}} s_i \le T_{bat} - t_{res}$$

| Símbolo | Valor | Regla |
| --- | --- | --- |
| T_bat | 2.280 s (38 min) | Tiempo en vuelo estacionario de la ficha DJI; el muestreo es estacionario |
| v_c | 9 m/s | Velocidad a la que DJI midió su autonomía (32,4 km/h) |
| v_sub | 6 m/s | Ascenso máximo en modo normal, ficha DJI |
| s_i | 534 s | Muestreo de un bloque de 5 × 5 puntos: promedio de los 9 vuelos de la Tabla 1 de Chang et al. (2025), que duran de 8 min 30 s a 10 min 2 s |
| t_res | 560 s | Peor regreso: 1.500 m / (15 − 12) m/s + 60 s de aterrizaje |

Quedan 1.720 s útiles (28,7 min) por vuelo. Si las cámaras no caben en una batería, se hacen varios vuelos con un cambio de batería de 5 minutos entre ellos.

## Las cuatro técnicas

Cada técnica decide tres cosas: por dónde ir entre dos puntos (los tramos), en qué orden visitar las cámaras y cómo repartirlas en vuelos.

**Tramos.** Para la base b y las cámaras C se calcula el mejor camino entre cada par de puntos con `pgr_dijkstra` (muchos a muchos, con costos propios en una tabla temporal):

- **Técnica 1:** el costo es la distancia volada en metros.
- **Técnicas 2, 3 y 4:** el costo de cada tramo es

$$c_e = (1-\theta+\varepsilon)\,\frac{t_e}{t_{ref}} + \theta\,(w_e + u_v), \qquad w = -\ln(1-p), \quad u = -\ln(1-q)$$

con t_ref, el tiempo de traslado del plan de la técnica 1, y ε = 10⁻⁶. Se usa el tiempo y no la distancia porque la batería se mide en tiempo.

**El clima es un evento del vuelo.** El viento es el mismo en todo el recorrido, así que el clima no se suma tramo a tramo: cada vuelo toma el máximo de su recorrido, μ_k = máx(−ln(1 − p_clima)). El incendio y las aves sí se suman por elemento.

| Técnica | Tramos | Orden y reparto | Qué garantiza |
| --- | --- | --- | --- |
| 1. `pgr_dijkstra` (distancia) | Solo distancia | Vecino más cercano; vuelve a la base cuando la siguiente cámara no cabe en la batería | Nada sobre el riesgo: es el peor caso de referencia |
| 2. Gurobi (MILP) | Costo del modelo | Óptimo exacto de orden y reparto, con batería y R mínima | El óptimo sobre el grafo reducido |
| 3. `pgr_dijkstra` (ponderado) | Costo del modelo | Vecino más cercano por costo; mismo cierre por batería | Tramos óptimos, orden y reparto gananciosos |
| 4. ACO | Costo del modelo | Construcción con feromona y búsqueda local | Buena solución sin garantía de óptimo |

### Modelo de Gurobi

x_ijk = 1 si el vuelo k va de i a j; y_ik = 1 si la cámara i va en el vuelo k; z_k = 1 si se usa el vuelo k; u_ik es el orden de i en el vuelo (restricciones MTZ, Miller, Tucker y Zemlin, 1960); μ_k es el clima del vuelo.

$$\min \sum_k \sum_{i,j} c_{ij}\,x_{ijk} + \theta \sum_k \mu_k$$

$$\sum_k y_{ik} = 1 \qquad \sum_j x_{ijk} = \sum_j x_{jik} = y_{ik} \qquad \sum_j x_{0jk} = \sum_j x_{j0k} = z_k \qquad z_k \ge z_{k+1}$$

$$\sum_{i,j} t_{ij}\,x_{ijk} + \sum_i s_i\,y_{ik} \le T_{bat} - t_{res} \qquad u_{ik} - u_{jk} + |C|\,x_{ijk} \le |C| - 1 \qquad \mu_k \ge \mu_{ij}\,x_{ijk}$$

$$\sum_k \Big(\sum_{i,j} \rho_{ij}\,x_{ijk} + \mu_k\Big) \le -\ln R_{min} \quad \text{(opcional)}$$

- **Límite de la licencia:** la licencia gratuita de Gurobi admite 2.000 variables y restricciones. El número de vuelos K se acota para no pasarlo. Con 8 cámaras el modelo tiene unas 720 variables.
- **Grafo reducido:** el modelo es exacto sobre el grafo reducido (base y cámaras con tramos precalculados), no sobre la red completa.
- **Parámetros:** MIPGap 0 y límite de 30 s, que es solo un seguro.

### ACO

- **Construcción:** cada hormiga sale de la base y elige la siguiente cámara con τ^α η^β, con η = 1/c_ij. Si ninguna cabe en la batería que queda, vuelve a la base y empieza otro vuelo, como el vehículo de Zhang et al. (2018) que vuelve a recargar.
- **Búsqueda local:** 2-opt dentro de un vuelo, mover una cámara a otro vuelo e intercambiar cámaras entre vuelos.
- **Configuraciones:** `config_mai` (α 1, β 8, ρ 0,2, 500 iteraciones, calendario de q₀ de Mai et al., 2023) y `config_zhang` (α 5, β 5, ρ 0,1, 150 iteraciones, 10 soluciones de élite). La segunda es la que se usa por defecto.

## Resiliencia

$$R_{vuelo} = (1 - p_{clima}) \prod_{v} (1 - q_v) \prod_{a} (1 - p_a) \qquad R_{plan} = \prod_k R_{vuelo,k}$$

- **R del plan:** un plan se completa solo si se completan todos sus vuelos.
- **Monte Carlo:** 10.000 sorteos por vuelo con la regla r ~ U(0, 100), donde un elemento falla si r ≤ 100 · p. Da un intervalo de 95 % de media anchura ≤ 0,01.
- **Más resiliente:** la técnica factible con mayor R del plan. Si hay empate, gana la de menor tiempo de vuelo y luego la más rápida de calcular. ΔR se mide contra la técnica 1.
- **Umbral:** R del plan ≥ 0,9. Si ningún plan lo alcanza, el sistema avisa y sugiere otra base o postergar.

## Campañas

- **Campaña:** 3 mañanas seguidas por sector, porque los modelos de ocupación necesitan visitas repetidas. Si se declaran menos días, queda como campaña parcial.
- **Ronda por temporada:** cubre el parque si alcanzan los días. Si no, la mitad de los días va a los sectores más prioritarios y el resto a la rotación de pendientes (`capacidad.py`).
- **7 días hábiles antes:** se arma un plan provisorio para la solicitud a la DGAC (DAN 91, Anexo D).
- **La noche anterior y al amanecer:** se revisa el pronóstico, se recalcula el plan y se decide si se vuela o se posterga. Una mañana postergada pasa a la siguiente; si se acaba la temporada, la campaña queda incompleta y el sector pasa primero en la ronda siguiente.

El programador corre dentro del motor cada 30 minutos (`MOTOR_PROGRAMADOR=0` lo apaga). El piloto siempre decide si despega.

## API

| Método | Ruta | Qué hace |
| --- | --- | --- |
| `GET` | `/health` | Estado de la base, de Gurobi y resumen de los datos |
| `GET` | `/api/parametros` | Batería, radio, altura y umbral |
| `GET` | `/api/sectores` | Sectores con prioridad, subtítulo, base y polígono |
| `GET` | `/api/bases` | Bases candidatas y las cámaras que cada una deja a la vista |
| `GET` | `/api/especies` | Especies con su categoría RCE, amenazas y comportamiento |
| `POST` | `/api/plan` | Plan de cada técnica |
| `POST` | `/api/fallas` | Sorteo de fallas por vuelo |
| `GET` / `POST` | `/api/probabilidades` | Probabilidad de falla de todos los elementos |
| `POST` | `/api/escenario` | Carga las amenazas de una fecha |
| `POST` | `/api/kml` | ZIP con un KML por vuelo y la solicitud a la DGAC |
| `GET` | `/api/capacidad` | Mañanas, días por pasada y rondas por temporada |
| `GET` / `POST` | `/api/campanas` | Lista y crea campañas |
| `POST` | `/api/campanas/{id}/decidir` | Revisa las amenazas y decide si se vuela la próxima mañana |
| `POST` | `/api/campanas/{id}/reprogramar` | Mueve las mañanas pendientes a otra fecha |
| `POST` | `/api/campanas/{id}/volada/{dia}` | Marca una mañana como volada |
| `GET` | `/api/campanas/{id}/kml` | KML del plan de la campaña |

### Entrada de `POST /api/plan`

```json
{
  "modo": "sector",
  "sector_id": 31,
  "especie": null,
  "camaras": [],
  "base_id": null,
  "fecha": "2024-02-10",
  "theta": 0.5,
  "restricciones": {"solo_bosque": true, "evitar_senderos": false, "evitar_clima": false,
                    "evitar_aves": false, "excluir_nodos": []},
  "overrides_prob": {"aristas": {"4": 0.6}},
  "focos_simulados": [],
  "r_min": null,
  "aco_config": null,
  "semilla": 0
}
```

- **`modo`:** `sector`, `especie`, `camaras` o `parque`. Sin `sector_id`, el modo sector toma el de mayor prioridad.
- **`fecha`:** vacía para usar los datos cargados. Una fecha pasada usa el histórico de ese día.
- **`overrides_prob`:** fuerza la probabilidad de un nodo o tramo (amenaza simulada).
- **`focos_simulados`:** agrega focos de incendio simulados `{lon, lat, confidence}`.

### Salida (resumida)

| Campo | Contenido |
| --- | --- |
| `titulo`, `modo`, `escenario`, `parametros` | Qué se planificó y con qué datos |
| `sectores[]` | Cada sector con sus cámaras, base, subtítulo y regla de la base |
| `no_visitadas` | Cámaras que no se pueden visitar y por qué |
| `planes[]` | Por técnica: `etiqueta`, `vuelos[]`, `distancia_m`, `tiempo_s`, `R`, `R_montecarlo`, `ic95`, `delta_R`, `costo`, `tiempo_ms`, `factible`, `mensaje`, `leyenda` |
| `planes[].vuelos[]` | `camaras`, `nodos`, `aristas`, `tiempo_s`, `R`, `p_clima`, `elementos` (con su p, para el sorteo) y `geojson` |
| `resiliencia` | Métrica, ranking, más resiliente, empates y aviso |
| `capas` | Bases, bloques de muestreo, tramos bloqueados desde la base y radio |

Ejemplo de leyenda: `Gurobi (MILP) | 2 vuelos | 5,0 km | 41 min | R plan = 0,892 | 8 ms`.

## Referencias

- Chang, B. et al. (2025). Enhancing Wildlife Detection Using Thermal Imaging Drones: Designing the Flight Path. *Drones*, 9(1), 52.
- Mai, X., Dong, N. y Chen, H. (2023). UAV path planning based on a dual-strategy ant colony optimization algorithm. *Intelligence & Robotics*, 3(4), 666-684.
- Zhang, S., Gajpal, Y., Appadoo, S. S. y Abdulkader, M. M. S. (2018). Electric vehicle routing problem with recharging stations for minimizing energy consumption. *International Journal of Production Economics*, 203, 404-413.
- Miller, C. E., Tucker, A. W. y Zemlin, R. A. (1960). Integer programming formulation of traveling salesman problems. *Journal of the ACM*, 7(4), 326-329.
