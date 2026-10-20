# amenaza_ebird.json

Avistamientos recientes de aves rapaces territoriales (*Accipitridae, Falconidae, Strigidae*) consultados desde la API 2.0 de eBird (The Cornell Lab of Ornithology).

## Justificación Técnica

Las aves rapaces (*Geranoaetus polyosoma*, *Falco peregrinus*, *Parabuteo unicinctus*, etc.) perciben a los drones como intrusos en su territorio reproductivo y de caza, protagonizando ataques directos que causan la pérdida total de la aeronave o daños a especies protegidas.

## Regla de Peso y Penalización

- **Umbral de territorialidad:** $500\text{ m}$ alrededor del avistamiento.
- Si un tramo o cámara cae a $\le 500\text{ m}$:
  - `evitar = true`
  - `costo_resiliente_km = costo_km + 1000`
- Al igual que en NASA FIRMS, el Dijkstra de fase 2 utiliza solo `costo_km`, dejando `costo_resiliente_km` para la heurística resiliente de fase 3.

## meta
- `fuente`: eBird API 2.0.
- `dias_atras`: 14 días.
- `umbral_amenaza_m`: 500 m.
- `penalizacion_km`: 1000 km.