# metadata_senderos.json

Trazados lineales y puntos de interés de los senderos del Parque Nacional Pumalín Douglas Tompkins, procesados desde el archivo vectorial oficial KML.

## Propósito en el Algoritmo

1. **Privacidad y Seguridad Aérea:** Los vuelos a baja cota no deben sobrevolar turistas. Los tramos con distancia $\le 50\text{ m}$ a un sendero habilitado activan `buffer_privacidad = true`.
2. **Evasión Antrópica:** Las cámaras cercanas a senderos experimentan menor presencia de mamíferos mayores durante el día por perturbación humana.
3. **Puntos de Lanzamiento (LZ):** Los puntos de inicio de sendero actúan como potenciales estaciones terrenas de despegue seguro.

## meta
- `fuente`: KML oficial exportado de Google My Maps (Pumalín).
- `crs_metrico`: EPSG:32718 (UTM 18S) para cómputos de distancia lineal en metros.
- `umbral_privacidad_m`: 50 m.

## senderos[]
- `id`: Identificador numérico.
- `nombre`: Nombre del sendero (ej: *Sendero Cascadas*, *Sendero Tronador*).
- `tipo`: `trazado` (LineString) o `punto_interes` (Point).
- `longitud_km`: Distancia calculada en proyección métrica.
- `nodos_cercanos`: Cámaras trampa a menos de 500 m.
- `aristas_cercanas`: Tramos del grafo de vuelo adyacentes al trazado.