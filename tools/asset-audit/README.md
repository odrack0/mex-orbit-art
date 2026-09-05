# asset-audit — banco de medición de mallas

Herramientas para **medir** mallas: las de referencia del cliente clásico de
DarkOrbit (formato AWD2) y, sobre todo, las nuestras (GLB/OBJ). Nacieron del
estudio que produjo el
[ASTRION LOW-POLY MODELING STANDARD](../../../mex-orbit-docs/03-guidelines/astrion-lowpoly/ASTRION_LOW_POLY_MODELING_STANDARD.md)
y su razón de seguir aquí es aplicar ese estándar a nuestros assets de forma
automática.

Todo es Python 3.12 + numpy + scipy + Pillow, salvo los dos scripts de render,
que corren dentro de Blender (`blender -b -P …`).

> Los AWD de DarkOrbit son **fuente de referencia técnica**, nunca de arte.
> Estas herramientas los leen para medirlos; nada de su geometría entra en
> ningún asset de Astrion.

---

## El que se usa a diario

### `validate_asset.py` — el validador del estándar

```bash
py tools/asset-audit/validate_asset.py ../mex-orbit-client/assets/npcs/aci-01.glb --type=boss --screen-size=150
```

`--screen-size` es el del JSON de la especie (`data/npcs/*.json`,
`data/ships/*.json`): reproduce el escalado que hace `entity_node.gd`
(`_body_scale = screen_size / extent_3d`), así que los píxeles y la densidad
que salen son los que ve el jugador.

Aplica los umbrales de la sección 10 del estándar y devuelve código de salida 1
si hay algún ERROR. Tipos: `prop`, `prop_grande`, `dron`, `pet`, `npc_normal`,
`npc_complejo`, `elite`, `boss`, `uber`, `player_ship`, `estructura`, `portal`,
`fx`.

| Opción | Para qué |
|---|---|
| `--type=` | elige el rango de triángulos, de piezas y de aplanamiento |
| `--screen-size=` | el `screen_size` del JSON de la especie: escala el modelo igual que `entity_node.gd`, para que la densidad medida sea la que ve el jugador |
| `--world-scale=` | multiplicador crudo, alternativa a `--screen-size` |
| `--organic` | baja la exigencia de simetría de 0,95 a 0,60 |
| `--json` | salida estructurada para CI |

La comprobación que más suele saltar es **densidad en pantalla** (tris por cada
1.000 px² a 1440p, zoom 1, rasterizando la máscara real del asset): es la que
caza el asset que pesa como un boss y ocupa como un prop. Solo se aplica por
encima de 1.000 triángulos — por debajo manda el suelo de forma.

---

## El motor

### `mesh_metrics.py`

El módulo que hace el trabajo. Se puede llamar directo:

```bash
py tools/asset-audit/mesh_metrics.py modelo.glb      # o .obj
```

Qué mide, y por qué importa cada cosa:

| Grupo | Métricas | Para qué sirve |
|---|---|---|
| Conteo | `verts_stored`, `verts_welded`, `vertex_split_ratio`, `tris`, `edges` | el coste real de vértices es el almacenado, no el soldado |
| Higiene | `degenerate_tris`, `duplicate_faces`, `nonmanifold_edges`, `boundary_edges`, `open_shell` | errores de malla que rompen import y horneado |
| Topología | `quad_tri_ratio`, `ngon_clusters_ge3`, `hard_edge_ratio`, `mean_dihedral_deg` | cuánto de la malla es quad y cuánto es facetado deliberado |
| Estructura | `islands`, `largest_island_tri_share`, `island_bbox_overlaps`, `planar_islands` | cuántas piezas hay, si se intersecan y si alguna es una carta plana |
| UV | `uv_coverage`, `uv_overlap_factor`, `uv_tiled`, `texel_density_iqr_ratio` | empaquetado, islas espejadas y si la densidad de texel es uniforme |
| Simetría | `mirror_x0`…`mirror_zc`, `best_mirror_frac` | fracción de vértices con contraparte espejada, por plano |
| Redondez | `rot_sym_order`, `radial_slots`, `slot_regularity`, `sphere_fit_rms_rel` | **cuántos segmentos tiene de verdad cada pieza torneada** |
| Reparto | `tri_share_y_upper_half`, `tri_share_outer_third_radial` | dónde está la geometría dentro del volumen |
| Cámara | `hidden_gamecam_ratio`, `silhouette_band_tri_share`, `tri_share_for_90pct_pixels`, `interior_tri_ratio`, `subpixel_tri_ratio`, `median_tri_px` | qué triángulos llegan a la pantalla y cuáles no |

Funciones reutilizables: `analyse()` (asset completo), `analyse_islands()`
(pieza a pieza), `rotational_order()`, `radial_slots()`, `fit_sphere()`,
`visible_triangle_area()`, `projected_px_area()`, `camera_dir()`.

La cámara del juego está en las constantes `GAME_CAM_ELEVATION_DEG = 45`,
`GAME_CAM_AZIMUTH_DEG = 25`, contrastadas en
`mex-orbit-docs/03-guidelines/darkorbit-3d/camara-proyeccion.md`.

**Autotest.** Las primitivas conocidas se miden correctamente: un cilindro de
12 lados da `rot_sym_order = 12`; uno de 8, `8`; una esfera de 16 segmentos,
`16`; un cubo, `4`. Si tocas la detección de simetría, vuelve a comprobarlo
contra primitivas generadas, no contra assets.

---

## Lectura de AWD (referencia)

### `awd_reader.py`
Lee el contenedor AWD2: geometrías (bloque 1), instancias (23), materiales
(81), texturas (82), esqueletos (101-103) y animación de vértices (112/113/122).
No convierte ejes: los números que salen son los del fichero.

### `awd_export_obj.py`
AWD → OBJ conservando los nombres de objeto originales y separando los
anclajes invisibles (`laserpoint_*`, `engine_*`, `light_position`) del casco.
Escribe un `.parts.json` con el mapa objeto → rango de triángulos.

```bash
py awd_export_obj.py entrada.awd salida.obj [--anchors]
```

### `audit_awd.py`
Audita una carpeta entera de AWD y escribe CSV + JSON.

```bash
py audit_awd.py <carpeta> salida.csv salida.json [--light] [--scales=escalas.json]
```

`--light` salta la parte cara (rasterizado de visibilidad): 43 s contra ~25 min
para 322 mallas. `--scales` cruza con las escalas del cliente para calcular
píxeles reales en pantalla.

### `audit_islands.py`
Lo mismo pero **pieza a pieza**: una fila por componente conexa de cada asset.
Es el fichero del que salen los histogramas de segmentos.

### `audit_textures.py`
Inventario de una carpeta ATF leyendo solo la cabecera: formato, tamaño, mips.
Agrupa por asset y canal.

### `merge_report.py`
Une geometría + escala en juego + texturas en una fila por asset.

---

## Renders de diagnóstico

### `render_diagnostics.py` (Blender)

```bash
blender -b -P render_diagnostics.py -- <dir_obj> <dir_salida> [nombre1 nombre2 …]
```

Por asset y por vista (cenital y 3/4 con la cámara real): `solid`,
`solidwire`, `wire` y `density` — este último colorea cada triángulo por su
tamaño relativo, así que enseña de un vistazo dónde se gastó el presupuesto.

### `render_silhouette_map.py` (numpy, sin Blender)

```bash
py render_silhouette_map.py <salida> [--scales=escalas.json] modelo.obj …
```

Pinta cada triángulo por su papel desde la cámara de juego: **rojo** si toca la
banda de silueta, **azul** si es interior visible, gris si no se ve. El segundo
panel muestra el mismo mesh al tamaño de píxel que tiene de verdad en juego.

### `decimation_test.py` (Blender)

```bash
blender -b -P decimation_test.py -- <dir_obj> <salida> <escalas.json> <nombre> …
```

Decima al 75/50/25 %, renderiza cada nivel en grande y al tamaño real, y mide
el porcentaje de píxeles de silueta que cambian. Ojo con la interpretación: esa
métrica **subestima el daño** cuando lo que se pierde son elementos finos
completos (un cañón que colapsa cambia pocos píxeles y arruina la lectura).

### `contact_sheet.py`
Compone los renders en hojas comparativas legibles.

---

## Limitaciones conocidas

- La banda de silueta de 4 px **infla en piezas finas**: en una placa delgada
  casi toda la superficie cae dentro de la banda.
- `interior_tri_ratio` se calcula rasterizando 18 direcciones a 256²: un
  triángulo más pequeño que un píxel de la sonda puede contarse como oculto sin
  estarlo. Léelo junto a `subpixel_tri_ratio`.
- Los píxeles en pantalla asumen la cámara documentada, zoom 1 y que la malla
  esté en unidades de mundo. Un GLB fuente viene normalizado: sin
  `--screen-size` (o `--world-scale`) la densidad que sale **no significa
  nada**.
- `load_glb` es un lector mínimo: concatena todas las primitivas de todas las
  mallas, ignora la jerarquía de nodos y sus transformaciones. Para un asset
  con nodos transformados, exporta aplicando transformaciones antes de medir.
- La detección de cuádriculas usa coplanaridad (< 1°), así que un quad con
  arista doblada cuenta como dos triángulos. Es lo que queremos: mide la
  intención de superficie plana, no la topología del fichero fuente.

---

## Dónde están los datos del estudio

`mex-orbit-docs/03-guidelines/astrion-lowpoly/datos/`:
`darkorbit_assets.csv` (309 assets × 68 columnas), `islands.csv` (10.872
piezas), `textures.csv` (4.401 ATF), `do_scales.json`, `fx.csv`,
`_decimation.json`, `_silhouette_stats.json`.
