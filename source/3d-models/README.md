# Modelos 3D

```
crudo/          lo que devuelve Meshy — IGNORADO por git
<nombre>.glb    el master de trabajo — versionado
```

## Por qué el crudo no entra a git

Un modelo crudo de Meshy pesa **78 MB**: dos millones de triángulos y tres
texturas de 2048 para un bicho que se dibuja a 178 px en pantalla. Es diez veces
el archivo más grande que este repo tiene hoy (8,5 MB), no hay LFS, y git no
olvida: si entra una vez, cada clon lo paga para siempre.

La carpeta `crudo/` existe igualmente porque tenerlo a mano ahorra volver a
generarlo. Pero **una carpeta en el mismo disco no es un respaldo, es una copia**
— si de verdad quieres respaldo de los crudos, tienen que salir de esta máquina.

## Por qué el master sí

La regla de los vídeos (`source/renders/*.mp4`: «sin él no se puede reexportar a
otros fps ni a otra resolución») aplica igual aquí, porque un modelo de Meshy
tampoco se regenera igual dos veces.

Lo que se versiona es la versión **de la que se puede re-exportar a cualquier
presupuesto de juego**: 200 000 triángulos y texturas de 1024, unos 7,4 MB. Los
dos millones no hacen falta para nada — está medido que a 15 000 no se distinguen
a tamaño de juego.

## Cómo se produce cada cosa

```bash
# crudo -> master (esto se versiona)
blender --background --factory-startup --python ../../tools/normalize-model.py -- \
    crudo/vexor-texture.glb vexor.glb 200000 1024 r

# master -> asset de juego (esto va al cliente)
blender --background --factory-startup --python ../../tools/normalize-model.py -- \
    vexor.glb <cliente>/pruebas/vexor.glb 15000 512 r
```

Antes de normalizar, validar:

```bash
py -3 ../../../mex-orbit-testing/assets/validar-modelo.py crudo/vexor-texture.glb
```

## Modelos procedurales (`procedural/`)

Piezas construidas por script en Blender, sin Meshy ni Tripo. Cada carpeta trae
el `.glb` (versionado), el `.blend` (ignorado: se regenera con el script), los
renders de inspección y `reporte.txt` con la verificación de geometría.

```bash
# esfera mecánica (concepto: esfera segmentada con núcleo frontal)
blender --background --factory-startup --python tools/esfera-mecanica.py -- \
    source/3d-models/procedural/esfera-mecanica
```

Diales de `tools/esfera-mecanica.py` (cabecera del script), todos en grados salvo
distancias en radios de esfera:

| Dial | Valor | Por qué |
|------|-------|---------|
| esfera UV | 32 × 16 (960 tris) | solo asoma en las ranuras, pero es la pieza que no se toca: perfecta y cerrada |
| ranura entre placas | 1,5° a cada lado (0,05 de ancho) | ~2,5 % del diámetro, como en el concepto |
| altura de placa / chaflán | 0,05 / 0,012 | el chaflán de 45° es lo que lee la cámara cenital como hard-surface |
| base hundida | 0,02 bajo la superficie | cada pieza es un sólido cerrado; hundirla evita z-fighting con la esfera |
| costuras de latitud | ±20 / ±52 / ±80 | ecuador 40°, banda 32°, casquete 28°, hub polar 10° |
| costuras de longitud | 30/90 ecuador, 0/60 banda, 45/135 casquete | tresbolillo entre bandas, simétrico en X y Z |
| cono del núcleo | semiángulo 36° | recorta las placas alrededor del núcleo (Boolean EXACT); bisel exterior llega a 30° |
| núcleo | bisel 21–30° h 0,08, aro 14,5–19° h 0,05, lente 13° h 0,035 | tres formas concéntricas; la lente será el cyan emisivo |
| Smooth by Angle | 30° | chaflanes y muros duros, tapas y esfera suaves |

Resultado (4-sep-2026): 4 170 triángulos evaluados, 8 mallas cerradas y manifold,
131 KB de GLB. Las líneas cyan no se modelan: van por textura/emission.

### v2: UVs y material IDs (`tools/esfera-mecanica-uv.py`)

Lee el `.blend` aprobado y escribe `esfera-mecanica-v2-uv.blend/.glb`, `uv-layout.png`,
`emission-mask.png`, `renders/three-quarter-clean.png` y `reporte-uv.txt`. Lo único que
cambia en geometría es que **aplica Boolean y Mirror** (cada placa necesita su propia isla
para que el desgaste pueda ser asimétrico); Smooth by Angle sigue vivo.

| Dial | Valor | Por qué |
|------|-------|---------|
| costura | diedro ≥ 60° | base de placas, esquinas y cortes del cono; los pliegues de 45° (tapa→chaflán→muro) se despliegan en la misma isla, así ninguna costura queda sobre una cara vista desde arriba |
| anillos del núcleo | un corte radial en −Z | fuera de la vista cenital; la lente y los hubs son discos y no lo necesitan |
| escala de islas | bases ×0,10, esfera ×0,40 | lo enterrado no se ve nunca; la esfera solo asoma en las ranuras |
| empaquetado | un solo 0..1, margen 0,004 (~8 px a 2048), rotación libre | un atlas de 2048 para todo el asset |
| muro | \|n·r\| < 0,35 | cara radial = interior de junta → MAT_RECESSES |
| máscara | rasterizado de las caras MAT_EMISSION + 4 px de sangrado | binaria por construcción, sin ruido |

Materiales: `MAT_HULL` (tapas y chaflanes), `MAT_RECESSES` (esfera, muros, bases),
`MAT_EMISSION` (solo `Core_Lens`, emisión a 0 hasta la fase de textura).

### v3: apariencia de Meshy reproyectada (`tools/reproyectar-texturas.py`)

Meshy texturiza bien pero **descarta las UVs y fusiona los materiales** (su despliegue son
cientos de islas de un triángulo). Como conserva la geometría vértice a vértice (solo la
reescala a caja unidad), sus texturas se reproyectan a NUESTRA malla: cada texel nuestro →
punto 3D → triángulo gemelo de Meshy → su UV → muestreo bilineal. Meshy queda como generador
de apariencia; la fuente de verdad sigue siendo `esfera-mecanica-v2-uv.blend`.

```bash
blender --background --factory-startup --python tools/reproyectar-texturas.py -- \
    source/3d-models/procedural/esfera-mecanica source/3d-models/crudo/esfera-mecanica-v2-meshy.glb
```

| Dial | Valor | Por qué |
|------|-------|---------|
| supermuestreo | 2×2 por texel + bilineal en origen | antialiasing; el promedio se hace en lineal para el base color |
| gemelos | centroides a < 1e-5 | 4 135 de 4 170 triángulos; los 35 n-gonos que Meshy retrianguló se resuelven por BVH |
| padding | relleno completo por jump-flooding | ningún mip muestrea negro; entre islas el relleno corta a mitad de camino |
| normal | re-base SOLO de la rotación en el plano tangente (x, y); z se conserva | Meshy suaviza sus normales de vértice a través de las aristas duras (21° de media respecto a la cara): pasar por la normal en mundo copiaría ese suavizado al mapa y anularía Smooth by Angle. MikkTSpace sobre copias trianguladas |
| espacios de color | basecolor sRGB; orm/metallic/roughness/normal Non-Color | orm: G = roughness, B = metallic |
| exportación | sin tangentes, backface culling | Godot genera MikkTSpace igual en las 8 piezas; materiales singleSided |
| MAT_EMISSION | `emission-mask.png` en Emission Color, fuerza 0 | el cyan es cambiar color y fuerza en un solo material |

Validación: render 3/4, cenital y frontal contra el GLB de Meshy alineado, diferencia media
0,6–1,1 % (sRGB) concentrada en chaflanes y aristas (nuestras normales duras contra las
suavizadas de Meshy: es la diferencia buscada); a 256 px (tamaño de juego) 0,6–1,1 %;
geometría 4 170 tris idéntica; normal final con inclinación p90 de 3,8°.
