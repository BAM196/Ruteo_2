# Motor de rutas resilientes (fase 3: puntos 5, 6 y 8)

Servicio `motor` (Python, en Docker, puerto 8001). Lee el grafo y las amenazas de la base y entrega:

1. **Punto 5:** la probabilidad de falla de cada nodo y cada arista, por amenaza y total (`motor/probabilidades.py`).
2. **Punto 6:** las 4 rutas: `pgr_dijkstra` por distancia, el modelo de optimización en Gurobi, `pgr_dijkstra` ponderado y ACO (`motor/rutas/`).
3. **Punto 8:** la métrica de resiliencia $R$ de cada ruta, con su tiempo de cómputo y la técnica más resiliente (`motor/resiliencia.py`).

Solo lee de la base (o de los JSON del repositorio) y de `config/*.yaml`. No depende del sitio ni de la simulación.

## Cómo se corre

Todo junto, desde la raíz del repositorio:

```bash
python main.py          # extrae, levanta Docker (postgis, web, motor), carga y calcula el punto 5
```

Por partes:

```bash
docker compose up -d --build motor
docker compose run --rm motor python -m motor.probabilidades --cargar   # punto 5 -> prob_fallo.json y tablas
docker compose run --rm motor python -m motor.evaluacion                # tablas y gráficos para el video
docker compose run --rm motor python -m pytest                          # pruebas (incluye las de la base)
```

Sin Docker ni base (para desarrollar), con los JSON del repositorio:

```bash
cd Motor
pip install -r requirements.txt
python -m pytest
python -m motor.probabilidades --fuente json
python -m motor.evaluacion --fuente json
MOTOR_FUENTE=json uvicorn motor.api:app --port 8001
```

## Estructura

```
Motor/
├── config/amenazas.yaml        # parámetros del punto 5 y del dron, cada uno con valor, fuente y justificación
├── config/aco.yaml             # config_mai y config_zhang
├── config/consulta_ejemplo.json# caso de ejemplo del punto 9
├── motor/
│   ├── grafo.py                # carga del escenario desde la base o desde JSON
│   ├── probabilidades.py       # punto 5
│   ├── rutas/comun.py          # costos, exclusiones, evaluación y GeoJSON comunes
│   ├── rutas/dijkstra_distancia.py   # técnica 1
│   ├── rutas/milp.py                 # técnica 2 (Gurobi)
│   ├── rutas/dijkstra_ponderado.py   # técnica 3
│   ├── rutas/aco.py                  # técnica 4
│   ├── resiliencia.py          # punto 8 (R analítico y Monte Carlo)
│   ├── servicio.py             # une los tres puntos para una consulta
│   ├── evaluacion.py           # 30 corridas del ACO, brecha, sensibilidad, convergencia
│   └── api.py                  # FastAPI
├── tests/                      # grafo de juguete con óptimo conocido + pruebas
├── prob_fallo.json             # salida del punto 5   (estructura: prob_fallo_estructura.md)
├── resultados/                 # salida de la evaluación (estructura: resultados/README.md)
├── Dockerfile.motor
└── requirements.txt
```

## API (contrato con el sitio)

| Método | Ruta | Qué hace |
| --- | --- | --- |
| `POST` | `/api/rutas` | Recibe la consulta del usuario y devuelve las 4 rutas con $R$, tiempo y leyenda |
| `GET` | `/api/probabilidades` | Punto 5 para toda la red |
| `POST` | `/api/probabilidades` | Igual, con `overrides_prob` en el cuerpo |
| `POST` | `/api/fallas` | Punto 7: sortea r ~ U(0,100) para cada nodo y arista y marca falla si r ≤ 100·p. Recibe `overrides_prob` y una `semilla` opcional. El sitio lo usa en "Simular fallas" |
| `GET` | `/health` | Estado de la base y del solver |

La documentación interactiva queda en http://127.0.0.1:8001/docs. El sitio llama a la API desde el navegador (CORS abierto).

### Entrada de `POST /api/rutas`

```json
{
  "origen_id": 33,
  "destino_id": 36,
  "restricciones": {"solo_bosque": false, "evitar_senderos": false, "excluir_nodos": []},
  "autonomia_m": 7980,
  "theta": 0.5,
  "overrides_prob": {"aristas": {"50": 0.8}},
  "r_min": null,
  "semilla": 0
}
```

| Campo | Significado |
| --- | --- |
| `origen_id`, `destino_id` | Cámaras de partida y de llegada (`nodos.id`) |
| `restricciones.solo_bosque` | Si es `true`, se excluyen los nodos con `landcover_code ≠ 10` (salvo origen y destino) |
| `restricciones.evitar_senderos` | Si es `true`, se excluyen las aristas marcadas con `buffer_privacidad` (cerca de un sendero) |
| `restricciones.evitar_clima` | Si es `true`, se excluyen los nodos y aristas con probabilidad de falla por clima (`meteo`) mayor que 0 (salvo origen y destino) |
| `restricciones.evitar_aves` | Si es `true`, se excluyen los nodos y aristas con probabilidad de falla por aves (`ebird`) mayor que 0 (salvo origen y destino) |
| `restricciones.excluir_nodos` | Cámaras que la ruta no puede tocar |
| `autonomia_m` | $D_{max}$ en metros. Si es `null`, se usa la del dron (7.980 m, ver más abajo) |
| `theta` | Peso del riesgo, entre 0 y 1. 0 = solo distancia, 1 = solo riesgo |
| `overrides_prob` | Probabilidades forzadas `{"nodos": {id: p}, "aristas": {id: p}}`. Se agregan como amenaza "escenario" (caso del punto 9) |
| `r_min` | Opcional: resiliencia mínima exigida ($R \ge r_{min}$) |
| `tecnicas` | Opcional: subconjunto de `["dijkstra_distancia", "milp", "dijkstra_ponderado", "aco"]` |
| `aco_config` | Opcional: `config_mai` o `config_zhang` (por defecto `config_zhang`) |
| `semilla` | Semilla del ACO y del Monte Carlo |

### Salida de `POST /api/rutas` (resumida)

```json
{
  "rutas": [
    {
      "tecnica": "milp",
      "etiqueta": "Gurobi (MILP)",
      "nodos": [33, 255, 153, 259, 36],
      "aristas": [605, 608, 623, 622],
      "geojson": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-72.6, -42.5], "..."]},
                  "properties": {"tecnica": "milp", "leyenda": "Gurobi (MILP) | 5,6 km | R = 1,000 | 55 ms"}},
      "distancia_m": 5648.4,
      "riesgo_log": 0.0,
      "p_supervivencia": 1.0,
      "costo": 0.5232,
      "tiempo_ms": 54.8,
      "factible": true,
      "mensaje": "ok",
      "R": 1.0,
      "R_montecarlo": 1.0,
      "ic95": [1.0, 1.0],
      "delta_R": 0.8,
      "ranking": 2,
      "leyenda": "Gurobi (MILP) | 5,6 km | R = 1,000 | 55 ms",
      "extra": {"solver": "Gurobi", "estado": "OPTIMAL", "objetivo": 0.5232, "gap": 0.0, "n_variables": 1628}
    }
  ],
  "mas_resiliente": "dijkstra_ponderado",
  "resiliencia": {"ranking": ["dijkstra_ponderado", "aco", "milp", "dijkstra_distancia"],
                  "empate_en_R": ["dijkstra_ponderado", "milp", "aco"]},
  "nodos_excluidos": {"6": "no es bosque (solo_bosque)"},
  "probabilidades": {"aristas_con_riesgo": {"50": 0.8}}
}
```

Cada ruta trae su `leyenda` lista para el panel (`algoritmo | km | R | ms`) y su `geojson` para dibujarla y prenderla o apagarla con un checkbox. Una ruta imposible llega con `factible: false` y un `mensaje`, nunca como error.

## Punto 5: probabilidad de falla

Cada parámetro está en `config/amenazas.yaml` con `valor`, `fuente` y `justificacion`. Lo que es supuesto de diseño se dice como tal.

| Amenaza | Modelo | Parámetros y fuente |
| --- | --- | --- |
| FIRMS (incendio) | $p = p_0(\text{conf})\cdot\max(0,\,1-d/R)$ | $R = 1.000$ m (píxel VIIRS de 375 m, Schroeder et al., 2014). $p_0$ = 0,9 / 0,7 / 0,4 según confianza h / n / l (supuesto) |
| Open-Meteo (clima) | $p = 1-(1-p_{viento})(1-p_{temp})(1-p_{lluvia})$ | Ráfaga: rampa de 8 m/s (supuesto) a 12 m/s (ficha DJI). Temperatura fuera de −10 a 40 °C: $p = 1$ (ficha DJI). Lluvia: rampa de 0 a 2,5 mm/h (AMS, "lluvia moderada"; el dron no declara IP) |
| eBird (aves) | $p = p_0\cdot f_{rec}\cdot f_{cant}\cdot\max(0,\,1-d/R)$ | $R$ = 100 m de precaución (Vas et al., 2015, recomiendan lanzar el dron a más de 100 m de las aves; no es un radio de perturbación medido) + 400 m de incertidumbre de ubicación de eBird (supuesto) = 500 m. $p_0 = 0{,}5$ (supuesto) |
| Senderos | — | Decisión D3: son metadata, no amenaza |

- **Distancias:** se miden en UTM 18S (EPSG:32718). Para una arista, es la distancia del punto al segmento, como en la fase 2.
- **Clima en aristas:** $p_a = \max(p_u, p_v)$ entre sus dos extremos (conservador).
- **Combinación:** las amenazas se tratan como independientes, $q = 1-\prod_k(1-q_k)$.
- **Cotas:** toda probabilidad se acota a $[0,\,1-10^{-6}]$, y una probabilidad en la cota equivale a excluir el elemento.
- **Limitación:** tratar las amenazas como independientes, y un nodo y sus aristas como independientes entre sí, sobreestima el riesgo cuando un mismo foco afecta a ambos. Es una aproximación conservadora.

### Autonomía del dron (D2, B4)

DJI Mavic 3T, el mismo dron del paper base (Chang et al., 2025). Datos de la [ficha técnica](https://enterprise.dji.com/mavic-3-enterprise/specs): 38 min de vuelo estacionario, 15 m/s de velocidad máxima en modo normal, 12 m/s de viento máximo y operación entre −10 y 40 °C.

$$D_{max} = \frac{v \cdot t \cdot (1 - \text{margen})}{2} = \frac{10 \cdot 38 \cdot 60 \cdot 0{,}7}{2} = 7.980 \text{ m}$$

- $v = 10$ m/s y el margen de 30 % son supuestos de diseño.
- Se divide por 2 porque el dron vuelve donde está el investigador.
- **Tramos de más de 3 km (T2 #4):** el dron sí puede volarlos, porque la autonomía de ida es de casi 8 km.
- **Tramos más largos que $D_{max}$:** hay aristas de hasta 27,9 km. Se excluyen solas de las técnicas 2, 3 y 4, porque ninguna batería las cubre.

## Punto 6: las cuatro técnicas

### Notación

- $V$: nodos; $A$: arcos dirigidos (cada arista $\{u,v\}$ da $(u,v)$ y $(v,u)$).
- $s$, $t$: origen y destino; $X \subseteq V$: nodos excluidos.
- $d_a$: largo del arco en metros; $p_a$, $q_v$: probabilidades de falla.
- $w_a = -\ln(1-p_a)$ y $u_v = -\ln(1-q_v)$.
- $d_{ref}$: distancia de la técnica 1; $\theta \in [0,1]$: peso del riesgo; $\varepsilon = 10^{-6}$.

### Modelo formal (técnica 2)

Variables: $x_a \in \{0,1\}$ (el arco se usa) e $y_v \in \{0,1\}$ (el nodo se visita).

**Objetivo:**

$$\min\;(1-\theta+\varepsilon)\sum_{a\in A}\frac{d_a}{d_{ref}}\,x_a+\theta\Big(\sum_{a\in A}w_a\,x_a+\sum_{v\in V}u_v\,y_v\Big)$$

**Restricciones:**

- Flujo: $\displaystyle\sum_{\delta^+(v)}x-\sum_{\delta^-(v)}x=\begin{cases}1&v=s\\-1&v=t\\0&\text{otro}\end{cases}$
- Una visita por nodo: $\displaystyle\sum_{\delta^-(v)}x\le1$
- Nodos visitados: $y_v\ge\sum_{\delta^-(v)}x$ y $y_s=1$
- Autonomía: $\displaystyle\sum d_a x_a\le D_{max}$
- Exclusiones: $x_a=0$ si $a$ toca $X$
- Opcional: $\displaystyle\sum w_a x_a+\sum u_v y_v\le-\ln R_{min}$

**Por qué el término de riesgo es exacto y lineal:** con fallas independientes, $P_{sup}=\prod(1-p)$. Minimizar $-\ln P_{sup}=\sum w+\sum u$ equivale a maximizar la supervivencia. Como los costos son estrictamente positivos (gracias a $\varepsilon$), el óptimo no tiene ciclos sueltos.

**Tamaño:** en el grafo final (278 nodos y 700 aristas) el modelo tiene unas 1.630 variables, bajo el límite de 2.000 de la licencia de `pip install gurobipy`. Si la red crece más, hay que pedir la licencia académica gratuita de Gurobi.

### Qué hace cada técnica

| Técnica | Costo | Autonomía | Implementación |
| --- | --- | --- | --- |
| 1. `pgr_dijkstra` (distancia) | `distancia_m` | Se revisa después | `SELECT id, source, target, distancia_m AS cost FROM aristas` |
| 2. Gurobi (MILP) | Modelo formal | **Restricción del modelo** | `gurobipy`, `TimeLimit` = 30 s, `MIPGap` = 0 |
| 3. `pgr_dijkstra` (ponderado) | $c_{uv}=(1-\theta)\,d_{uv}/d_{ref}+\theta\,(w_{uv}+u_v)$ | Se revisa después | `cost` y `reverse_cost` por sentido; un costo de −1 excluye la arista |
| 4. ACO | El mismo $C(P)$, más una penalización | Penalización $\gamma$ + `factible` | `config/aco.yaml` |

La diferencia entre las técnicas 2 y 3 es que usan **la misma función de costo**, pero solo el modelo de optimización impone $D_{max}$. En `resultados/tabla_rutas_autonomia.csv`, con $D_{max}$ = 5.500 m:

- La técnica 3 elige el desvío de 5,65 km y queda no factible.
- Gurobi devuelve la única ruta que sí cabe en la autonomía (la corta, con $R$ = 0,2).
- El ACO tampoco la encuentra: la heurística castiga tanto el tramo amenazado que casi ninguna hormiga lo elige, y como la autonomía solo entra como penalización, devuelve el desvío no factible.

### ACO: qué se toma de cada paper y qué se adapta

| Elemento | Zhang et al. (2018), EVRP | Mai et al. (2023), dron | Aquí |
| --- | --- | --- | --- |
| Regla de transición | $[Sav]^\alpha[\tau]^\beta$, probabilística | Probabilística + arg max con $q_0$ variable por iteración (Ec. 15, $k_0 = 0{,}7K$) | $P_{ij}\propto\tau_{ij}^\alpha\eta_{ij}^\beta$; `config_mai` usa el calendario de Mai con $q_{0,inicial} = 0{,}9$; `config_zhang` usa $q_0 = 0$ |
| Heurística | Ahorro (VRP con depósito) | $S\cdot M\cdot D$ (accesibilidad, altura, distancia al destino) | $\eta_{ij}=1/(c_{ij}+h_j)$, con $h_j$ = distancia en línea recta de $j$ al destino (como el factor $D$ de Mai), normalizada |
| Feromona | $\phi\tau+\sum\Delta\tau$, con $\lambda$ élite | Solo la mejor; $[\tau_{min},\tau_{max}]$ | Evaporación $\rho$; depositan la mejor de la iteración, la global y las $\lambda$ élite; $\Delta\tau=1/f$; cotas de Mai |
| Objetivo | Energía + penalizaciones | Largo + altura + giros | $f=C(P)+\gamma\max(0,D-D_{max})/d_{ref}$ |
| Autonomía | Penalización de batería | $L\le L_{max}$ | Penalización $\gamma = 1000$ + toda ruta factible gana sobre una no factible |
| Búsqueda local | ILS (2-opt\*, reubicar…) para varias rutas | No tiene | Reemplazar un tramo de 2 o 3 saltos por su camino mínimo |
| Comparación | CPLEX (instancias pequeñas) | AS, MMAS, otro ACO | Óptimo de Gurobi (técnica 2) |

- **Limitación:** Zhang es de **varios vehículos** y Mai trabaja sobre una **grilla 3D con terreno**. Aquí se usa un grafo y un solo dron, así que es una adaptación, no una réplica.
- **Decisiones propias:**
  - $\tau_0=\tau_{max}$.
  - $q_{0,inicial} = 0{,}9$ en el calendario de Mai: el paper da la forma (Ec. 15), pero no el valor, que tampoco aparece en su Tabla 4. Se barren los valores $\{0;\ 0{,}5;\ 0{,}9\}$ en la tabla de sensibilidad.
  - Normalizar $\eta$.
  - Usar la heurística euclidiana. Con el costo exacto al destino (un Dijkstra inverso) el ACO se vuelve un Dijkstra voraz; esa variante queda disponible con `heuristica: dijkstra`.
  - Tramo de búsqueda local de 3 saltos como máximo, para que nunca reemplace el camino completo.
  - Interpretar $\varepsilon = 25$ de Zhang como iteraciones sin mejora.

## Punto 8: métrica de resiliencia

$$R(P)=\prod_{v\in P}(1-q_v)\prod_{a\in P}(1-p_a)$$

Es la probabilidad de que la ruta se complete bajo las amenazas detectadas, y es igual a `p_supervivencia` $=e^{-\text{riesgo\_log}}$.

- **Validación:** se valida con Monte Carlo ($N$ = 10.000) usando la regla D4 del punto 7: $r\sim U(0,100)$, y el elemento falla si $r\le100p$. Se informa el intervalo de confianza $R\pm1{,}96\sqrt{R(1-R)/N}$.
- **Rutas no factibles:** no reciben $R$, y se marcan.
- **Más resiliente:** `mas_resiliente` es la ruta factible con mayor $R$. A igual $R$ gana la más corta, y luego la más rápida de calcular; el empate se informa en `empate_en_R`.
- **$\Delta R$:** $\Delta R = R_{tec}-R_{dijkstra}$ mide cuánto mejora cada técnica a la ruta por distancia.
- **Umbral de ruta resiliente (B6):** se propone $R\ge0{,}9$, es decir, a lo más un 10 % de probabilidad de no completar la misión. Se puede exigir con `r_min`.

## Resultados (`python -m motor.evaluacion`)

**Caso de ejemplo** (`config/consulta_ejemplo.json`): de la cámara 33 (U65) a la 36 (R61), con la arista 50 (de la U65 a la T62) amenazada ($p$ = 0,8).

| Técnica | Ruta | Distancia | $R$ | Tiempo |
| --- | --- | --- | --- | --- |
| `pgr_dijkstra` (distancia) | 33-35-36 | 5,4 km | 0,200 | ~4 ms |
| Gurobi (MILP) | 33-255-153-259-36 | 5,6 km | 1,000 | ~55 ms |
| `pgr_dijkstra` (ponderado) | 33-255-153-259-36 | 5,6 km | 1,000 | ~13 ms |
| ACO (`config_zhang`) | 33-255-153-259-36 | 5,6 km | 1,000 | ~26 ms |

Las técnicas 2, 3 y 4 rodean la cámara T62 por tres waypoints del anillo y empatan en $R$ ($\Delta R$ = +0,8). Los tiempos son dentro de Docker, con PostGIS.

**ACO: 30 corridas por configuración** (semillas 0 a 29, en el caso de ejemplo): brecha de 0 % en las 60 corridas. El caso es pequeño, así que la brecha ahí no discrimina.

**Banco de estrés** (`aco_banco_resumen.csv`): 12 pares al azar, 15 aristas amenazadas y $D_{max}$ = 60 km, para que existan muchas alternativas.

| Configuración | Búsqueda local | Brecha promedio | Brecha máxima | Sin ruta factible |
| --- | --- | --- | --- | --- |
| `config_mai` | No | 1,2 % | 26,0 % | 4 de 50 |
| `config_mai` | Sí | 0,8 % | 19,4 % | 3 de 50 |
| `config_zhang` | No | 5,7 % | 33,3 % | 20 de 50 |
| `config_zhang` | Sí | 0,9 % | 11,8 % | 20 de 50 |

Gurobi siempre llega al óptimo; el ACO no siempre, que es el resultado esperado. Con búsqueda local, `config_mai` llega al óptimo en 43 de 50 corridas y `config_zhang` en 26 de 50. La brecha de 3,2 % que reporta Zhang es de otro problema (varios vehículos) y no se compara con esta.

## Referencias

- Chang, B. et al. (2025). Enhancing Wildlife Detection Using Thermal Imaging Drones: Designing the Flight Path. *Drones*, 9(1), 52. https://doi.org/10.3390/drones9010052
- DJI (s. f.). *Mavic 3 Enterprise Series – Specs*. https://enterprise.dji.com/mavic-3-enterprise/specs
- Mai, X., Dong, N. y Chen, H. (2023). UAV path planning based on a dual-strategy ant colony optimization algorithm. *Intelligence & Robotics*, 3(4), 666–684. https://www.oaepublish.com/articles/ir.2023.37
- Schroeder, W., Oliva, P., Giglio, L. y Csiszar, I. A. (2014). The New VIIRS 375 m active fire detection data product. *Remote Sensing of Environment*, 143, 85–96.
- Vas, E., Lescroël, A., Duriez, O., Boguszewski, G. y Grémillet, D. (2015). Approaching birds with drones: first experiments and ethical guidelines. *Biology Letters*, 11(2), 20140754. https://doi.org/10.1098/rsbl.2014.0754 (PMC4360097)
- Zhang, S., Gajpal, Y., Appadoo, S. S. y Abdulkader, M. M. S. (2018). Electric vehicle routing problem with recharging stations for minimizing energy consumption. *International Journal of Production Economics*, 203, 404–413.
- American Meteorological Society. *Glossary of Meteorology*, entrada "Rain".
- Documentación de pgRouting (`pgr_dijkstra`), Gurobi y Open-Meteo.
