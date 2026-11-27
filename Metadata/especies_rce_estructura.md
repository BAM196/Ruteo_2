# especies_rce.json

Especies que registran las cámaras, cruzadas con su categoría oficial de conservación en Chile. Lo genera `Metadata/especies_rce.py`, que lee dos fuentes:

- **Nómina de especies según estado de conservación del Ministerio del Medio Ambiente:** actualizada al 20º proceso del Reglamento de Clasificación de Especies (RCE). El script la descarga a `data/rce_nomina.xlsx`.
- **`Metadata/fichas_especies.yaml`:** amenazas y comportamiento de cada especie, con su fuente.

## Reglas

- **Categoría:** se usa la vigente en la Región de Los Lagos.
  - Si la nómina da categorías por zona, se toma la del rango que incluye la región X. Por ejemplo, la güiña es VU de la XIV Región al norte y NT de la X al sur, así que aquí es NT.
  - Si la nómina da categorías por subespecie, se toma la del resto. El culpeo es LC; solo la subespecie de Tierra del Fuego es VU.
- **Peso:** w = 1 + peso del Red List Index (LC 0, NT 1, VU 2, EN 3, CR 4; Butchart et al., 2007).
- **Especie objetivo:** nativa con categoría VU, NT, EN o CR. En el parque son el pudú (VU), la güiña (NT) y el puma (NT).
- **Presión:** las especies domésticas o exóticas, que presionan a las nativas. En el parque son el perro, la vaca, la liebre europea y el visón americano.

La UICN bajó a la güiña a Preocupación menor en octubre de 2025. En Chile rige la categoría del RCE.

## meta

`fuente`, `version`, `url`, `archivo_local`, `region`, las cuatro reglas, `nota_uicn`, `generado` y `n_especies`.

## especies[]

| Campo | Contenido |
| --- | --- |
| `cientifico`, `comun` | Nombre de la especie como lo registran las cámaras |
| `registros`, `camaras` | Registros totales y en cuántas cámaras aparece |
| `origen` | Nativa, doméstica, exótica o exótica invasora |
| `nombre_rce`, `comun_rce` | Nombre en la nómina (el pudú figura como *Pudu pudu*) |
| `categoria_vigente`, `categoria_los_lagos` | Texto de la nómina y categoría que rige en la región |
| `presente_en_los_lagos`, `decreto`, `proceso_rce` | Distribución, decreto y proceso de clasificación |
| `peso_rli`, `peso_w`, `objetivo`, `presion` | Peso y rol en la prioridad |
| `amenazas` | Texto, fuente y URL de la ficha RCE (pudú, güiña y puma) |
| `comportamiento` | Organización social, actividad, ámbito de hogar, qué implica para el monitoreo y la fuente |
| `como_presiona` | Para las exóticas y domésticas |

La tabla `especie_rce` guarda estos campos; las fichas van en la columna `ficha` (JSONB).
