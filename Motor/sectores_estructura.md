# sectores.json

Sectores de monitoreo: grupos de cámaras que se atienden desde una sola base, con su prioridad. Lo genera `python -m motor.mision.sectores` y se carga en las tablas `sectores` y `sector_camara`.

## Cómo se arman

**Partición exacta.** Se busca el menor número de grupos tal que cada grupo tiene una base que deja todas sus cámaras a ≤ R_op − r_b y con su bloque de muestreo a la vista. A igual número de grupos, gana la menor suma de diámetros.

- **Diámetro máximo:** D = 2 (R_op − r_b) ≈ 2,7 km. El diámetro sale del radio de operación, no de un número de grupos fijado a mano.
- **Cada cámara queda en un solo sector:** lo que se muestrea es el bloque de 200 × 200 m alrededor de cada cámara. Como la cámara más cercana a otra está a 1 km, ningún espacio se muestrea dos veces.
- **Numeración:** los sectores se numeran de norte a sur.

## Prioridad

$$V_s = \sum_{e \in \text{nativas}} w_e \, f_{e,s} \qquad P_s = \frac{\text{cámaras con alguna exótica o doméstica}}{\text{cámaras del sector}} \qquad \text{Prioridad}_s = 100 \cdot \frac{\hat V_s + \hat P_s}{2}$$

- **f_e,s:** fracción de cámaras del sector que registraron la especie e. Una especie registrada en más cámaras tiene más probabilidad de estar presente y de detectarse en un vuelo.
- **w_e:** 1 + peso del Red List Index (`Metadata/especies_rce.json`).
- **V̂ y P̂:** cada componente dividido por su máximo entre sectores.
- **Pesos iguales:** no hay base para preferir un componente. La estabilidad del orden se mide con Kendall al variar el peso entre 0,3 y 0,7.
- **El riesgo de vuelo no entra:** un sector peligroso no es menos importante para la fauna. El riesgo se muestra aparte, como la R del plan.

## meta

`metodo`, `diametro_max_m`, `alcance_m`, `n_sectores`, `tamanos` (cuántos sectores hay de cada tamaño), `sin_base`, `prioridad` y `numeracion`.

## sectores[]

| Campo | Contenido |
| --- | --- |
| `id`, `camaras`, `n_camaras`, `diametro_m` | Sector |
| `base`, `regla_base` | Base elegida (la de menor suma de distancias a las cámaras) y la regla |
| `valor_conservacion`, `presion_exoticas`, `V_norm`, `P_norm`, `prioridad` | Componentes y prioridad de 0 a 100 |
| `descripcion` | Especies predominantes, objetivo (con su categoría) y exóticas |
| `registros` | Registros por especie en el sector |
| `subtitulo` | Lo que ve el usuario. Por ejemplo: *Sector 8 · Prioridad 90 % · Predominan: pudú, güiña · Objetivo: pudú (VU), güiña (NT) · Exóticas: visón americano* |
| `poligono` | Envolvente de los bloques de muestreo, para el mapa |
