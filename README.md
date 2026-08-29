# mex-orbit-art

La fuente de todo el arte del juego: **cero assets heredados — identidad visual propia desde el vector**.

> **MexOrbit** es nombre temporal del proyecto. Documentación en español.

## Qué es

- **Los archivos fuente** (vectorial: SVG/proyectos de edición) de naves, aliens, drones, items, efectos, mapas/fondos y UI — la base vectorial de naves ya aprobada en fase 0 es el punto de partida del estilo.
- **El pipeline de exportación**: de fuente vectorial a los formatos que `mex-orbit-client` consume (spritesheets/texturas/atlas), reproducible y documentado.
- **La guía de identidad visual**: paleta, estilo, y la iconografía de las 5 familias de nombres del diseño (materiales, legendarios, códigos de equipo, constelaciones, taxonomía alien).

## Qué NO es

- No es el repo de assets *importados* del cliente (eso es salida del pipeline, versionada en `mex-orbit-client`); aquí vive la **fuente**.
- Nada derivado de BigPoint entra a este repo — ni sprites, ni trazas, ni paletas calcadas.

## Organización (propuesta inicial, por definir con el pilar de arte)

```
ships/        # naves (constelaciones)
aliens/       # taxonomía (Vex → Imperator)
items/        # iconografía de equipo, materiales, consumibles
ui/           # design system: componentes, iconos, tipografía
maps/         # fondos y elementos de mapa
fx/           # efectos (láseres, explosiones, recubrimientos)
pipeline/     # scripts de exportación
brand/        # identidad (nota: el nombre del juego es temporal — nada de logos definitivos aún)
```

## Vídeos en bucle -> atlas animado

`tools/video-atlas.py` convierte un vídeo con croma verde en la rejilla de fotogramas que monta el
cliente. El master vive en `source/renders/<Nombre>.mp4`: sin él no se puede reexportar a otros fps
ni a otra resolución.

**La celda se elige por lo que el bicho mide en pantalla** (`screen_size` de su JSON), no copiando la
del anterior. Un Gravit de 124 px en una celda de 384 es triple muestreo que nadie ve y que se paga
entero en VRAM: con 256 cuesta 12,2 MB en vez de 27,6.

| bicho | en pantalla | celda | VRAM |
|---|---|---|---|
| Gravon | 214 px | 384 | 27,6 MB |
| Skarnox | 208 px | 384 | 27,6 MB |
| Ferox | 190 px | 320 | 19,1 MB |
| Mordax | 186 px | 320 | 19,1 MB |
| Vex | 141 px | 256 | 12,2 MB |
| Vexor | 178 px | 320 | 11,7 MB |
| Gravit | 124 px | 256 | 12,2 MB |
| Vorax | 232 px | 128×512 | 12,2 MB |
| caja | 96 px | 192 | 6,9 MB |
| portal | 380 u | 384 | 14,1 MB |
| base | 820 u | 632×1048 | 40,4 MB |

La del Vorax no es cuadrada a propósito: es un gusano de 125×638 y cuadrarlo tiraría el 80% de cada
celda.

**La celda y los fps son el mismo dial, y la base lo enseñó.** El área del atlas es celda × número de
fotogramas, así que subir uno obliga a bajar el otro. La base se dibuja a 820 px de ancho: con 48
fotogramas a 12 fps la celda no pasaba de 320, o sea el render **reducido a la mitad y luego ampliado
2,56×** — contornos deshechos y líneas de panel ilegibles. A 4 fps caben 16 celdas de 632×1048, que es
la resolución completa del render, con una ampliación de 1,30×.

Lo que decide si el cambio sale gratis es **cuánto se mueve el sujeto**, y eso se mide en la salida
del script: triplicar el intervalo entre fotogramas subió el paso normal de 2,25 a 3,00 sobre 255. Un
balanceo lento aguanta pocos fotogramas; un bicho que aletea, no. Mirar ese número antes de bajar los
fps, no después.

Y un límite que conviene tener presente: un sujeto **grande en pantalla y con muchos fotogramas** no
cabe nítido a ningún precio razonable. Dibujar la base a 820 px con 48 fotogramas afilados serían
219 MB. Si hiciera falta esa fluidez, la salida no es el atlas: es **cámara fija en el render y que se
muevan solo las luces**, y entonces el cuerpo va en un PNG nítido y barato y solo la capa emisiva se
anima. Se probó a separarlas de este vídeo restando el mínimo temporal y no salió, porque aquí se
mueve la base entera.

**No todo asset animado es un bucle.** Con `RANGO=ini:fin` se exporta un tramo como **secuencia de un
disparo** y se salta el análisis de bucle entero. Es lo que necesita el portal, que reposa en su
primer fotograma y reproduce el encendido una sola vez al activarlo: ahí no hay costura que cerrar, y
el recorte al mejor cierre le comería justo el final, que es donde el portal se queda.

```
RANGO=0:24 py -3 tools/video-atlas.py source/renders/Portal.mp4 exports/portal-anim.png 12 384
```

El recorte del rango va **antes** de calcular la caja de la unión: encuadrar contando fotogramas que
se van a tirar agranda la caja y encoge al bicho dentro de su celda.

`RANGO` y `SECUENCIA` son **independientes**, aunque nacieran juntas con el portal. El Vexor pliega y
despliega las alas dos veces en sus 4 s: quiere `RANGO=0:25` (media película, misma animación, la
mitad de VRAM) pero **sigue siendo un bucle** y su costura importa. Recortar y no-cerrar son dos
decisiones distintas.

**Antes de exportar entero, mirar si el vídeo se repite.** Medir el salto del fotograma `k` contra el
`0` para todo `k` y buscar el primer valle: si lo hay, ahí está el ciclo real y el resto es VRAM
tirada.

**Y el valle solo cuenta si cierra igual de bien que el vídeo entero.** El Vexor recortaba porque su
valle empataba con el total (0,95 contra 0,99). El Ferox tiene uno que ahorraría 7 MB y no se usa,
porque cierra a 1,49× cuando el entero cierra a 0,5×: un sub-bucle que cierra *peor* no es un ciclo
repetido, es un parecido, y recortar ahí quita movimiento real.

**Y si no hay ciclo, puede que no haga falta.** El vídeo del Vex es una **rampa** —se enciende y
despliega las alas y ahí se queda—, con una costura de 3,9× que ningún recorte arregla. Se reproduce
con vaivén (`"pingpong": true` en su JSON) y el cierre sale perfecto por construcción sin gastar un
fotograma más. Ojo: eso solo vale si el movimiento **no tiene dirección privilegiada**. Los aros del
Gravon tienen rotación neta y al revés se mecerían; un ala que se abre no, porque cerrarse es su
vuelta.

**Antes de exportar, medir el vídeo.** Cuatro vídeos se rechazaron por el mismo tipo de fallo, y los
tres números que los cazan son baratos:

| medida | bueno | rechazado |
|---|---|---|
| deriva del centroide | Gravit 6×2 px · Mordax 0×11 px | Vorax v1: 55×37 px |
| variación de la caja | Gravit 0 px · Mordax 6×32 px | Vorax v1: 70×196 px |
| fondo | croma verde | Gravon v1 negro: el metal oscuro no se separa |
| luz de borde | ninguna | Base v2: el 57% del anillo del objeto llega teal |

El cuarto fue la primera caja de carga, en perspectiva 3/4 con suelo y reflejo — eso no lo caza un
número, lo caza mirar. El contrato de render está en `prompts/README.md`.

La quinta medida es la última en llegar y la aprendió la base: **el croma no debe ILUMINAR al sujeto.**
Si el generador pone luz de rebote verde en el contorno, esa luz está pintada en el arte y ningún
recorte la quita — no es mezcla con el fondo, es iluminación. Se intentó despillar solo el anillo
restando en la dirección del croma y el borde salió **magenta**, porque ahí el verde-azulado del croma
y las tiras de luz cian de la propia base son el mismo píxel. Se mide igual que lo demás: qué
porcentaje del anillo exterior del objeto, **en el vídeo sin tocar**, tiene verde y azul por encima
del rojo.

## Cuánto detalle admite una nave

La Phoenix v1 era un render fotorrealista con suciedad, franjas de peligro y rótulos («POD 749»,
«ORION LOGISTICS»). Se ve magnífica a 512 px y no se ve en el juego, porque **la nave se dibuja a
141 px y el zoom baja hasta 0,1**. Un rótulo de cinco píxeles a esa escala no es detalle: es ruido que
además hierve al moverse.

El criterio no es «menos detalle» a ojo, se mide a tamaño de juego:

| | contraste a 141 px | a 35 px |
|---|---|---|
| Phoenix v1 (fotorreal) | 31,1 | 29,4 |
| Phoenix v2 (limpia) | **43,6** | **42,1** |

Lo que sobrevive al tamaño final es **silueta y contraste de valor**, no la densidad de detalle. La v2
gana un 40% de contraste y a 35 px se sigue leyendo como nave; la v1 a ese tamaño es una mancha parda.
Los cañones de la v2 sobresalen más, y eso también ayuda: ensanchan la silueta, que es lo primero que
lee el ojo de lejos.

La mitad técnica de este mismo problema está en el cliente y es el filtrado de textura — sin mipmaps
el contorno se puntea. Está documentado en el README de `mex-orbit-client`.

## Relieve: mapas de normales (ruta C)

`tools/gen-normal.py` deriva un mapa de normales **del propio render**. Existe porque el arte es
cenital y los sprites rotan, así que su iluminación gira con ellos: el brillo del casco apunta siempre
al mismo sitio *relativo a la nave*, nunca al mismo sitio del mundo, y el ojo lee eso como recorte de
papel. Con el mapa, el shader reilumina contra una luz fija en el mundo y al virar el reflejo **barre**
el casco.

Lo que **no** da: volumen. La silueta sigue plana y no hay escorzo. Es relieve, no perspectiva — la
alternativa que sí da perspectiva es el atlas de rotación, y ese obliga a rehacer el catálogo entero
con un solo ángulo de cámara.

La altura sale de dos fuentes que hacen cosas distintas:

| fuente | qué aporta | por qué así |
|---|---|---|
| silueta | el volumen del cuerpo | la distancia al borde aproxima un casco redondeado; el radio sale de la propia pieza, así que un casco ancho abomba más que una antena |
| luminancia **pasada por alto** | paneles, remaches, greebles | cruda trae cocida la luz del render (un degradado suave), y entonces el mapa cree que la nave es una rampa |

**La fuerza no se pasa a mano: se resuelve** para que la inclinación media de la normal caiga en un
objetivo (30° por defecto). Un factor fijo da un resultado distinto en cada asset —depende del
contraste del render y del tamaño del export— y entonces cada nave se ilumina con una intensidad
distinta sin que nadie sepa por qué. Se ve en las dos Phoenix: la misma inclinación pide fuerza 27,2
en una y 40,9 en la otra.

El defecto conocido de derivar altura de la luminancia es que **lo claro sube**, así que un rótulo
pintado se convierte en un bulto. Con un render de arcilla no pasa —ahí el sombreado *es* la forma—;
con uno sucio y rotulado, sí. Otra razón por la que un render limpio vale más que uno bonito.

La dirección de la luz **no** vive aquí: es una sola para todo el mundo y está en el cliente
(`AssetDefs.LUZ_MUNDO_GRADOS`). Dos objetos con su propia luz se leen como dos recortes pegados.

### Atlas y resolución

Con `ATLAS=colsxfilas` se procesa una rejilla. Cada celda va por su cuenta —la silueta y el paso alto
no pueden cruzar el borde, ahí empieza otro fotograma— pero **la fuerza se resuelve una sola vez para
toda la hoja**: por celda, cada fotograma tendría su propia intensidad y el bicho parpadearía al
animarse.

Con `ESCALA=0.5` el mapa sale a media resolución, y eso no es una concesión: las normales son de
frecuencia más baja que el color, y a tamaño completo **doblarían la VRAM del asset**. A la mitad
cuesta un 25%. Los nueve bichos suman +40 MB y la estación +10.

Media, no menos: bajar a 0,3 ahorraría otros 3 MB por bicho pero cambia el resultado iluminado a
tamaño de juego un **9,9%**, y eso se ve. Medido sobre el Ferox a 190 px, que es lo que mide en
pantalla.

**Los emisivos SÍ necesitan protección, y medirlo en el asset equivocado casi lo oculta.** Medido sobre el Ferox salía un 2%, así que no se escribió: como la altura sale de la
luminancia, las normales derivadas apuntan hacia la luz del propio render y el relieve refuerza el
sombreado que el arte ya traía. Pero el Ferox casi no tiene luz propia. En la caja de carga —tubos de
neón— y en el portal —plasma— la misma cuenta da el negocio entero, y el shader acabó protegiéndolos.

La lección no es sobre emisivos: **un asset no basta para decidir una regla del pipeline.** El que se
elija para medir decide la respuesta.

## El recorte del croma

No es un umbral con desenfoque encima, y dejó de serlo porque la base lo delató. Umbralizar cuantiza
el contorno a píxeles enteros y difuminar después no recupera la forma. El recorte estima un **alfa
continuo** a partir del verdor y luego **desmezcla**: un píxel de borde es `objeto·α + croma·(1−α)`,
así que se le resta lo que puso el croma y se divide por α. El borde sale del color que tiene el
objeto, con su forma real. El *despill* clásico no basta: baja el canal verde, pero lo que el croma
aportó en luminancia se queda dentro y el ribete se ve igual, oscuro en vez de verde.

Un hueco cerrado dentro de la silueta es fondo **si es verde**, y mota si no lo es. Antes se decidía
por tamaño (< 2500 px se rellenaba) y el tamaño nunca fue el criterio: los vanos del aro de la base
miden ~1.400 px y se quedaban dentro, rellenos de croma.

**Y el atlas se sangra.** Godot filtra en bilineal y al filtrar mezcla el RGB de los téxeles vecinos
**sin mirar su alfa**: un téxel transparente que guarde croma verde no es inofensivo por ser
invisible, su color entra en la media y tiñe el borde del de al lado. Por eso cada píxel transparente
recibe el color del píxel opaco más cercano. A 1× casi no se nota; la base se dibuja a más de 1× y
ahí cada téxel del contorno se reparte entre varios píxeles de pantalla.

Se comprueba mirando el verdor del borde opaco del atlas contra el del render sin tocar: si coinciden
(−11,6 contra −12,4 en la base), lo que queda es el arte y no el croma.

## Modelos 3D -> asset de juego: LA RECETA

Lo que pedirle a Meshy, y por qué cada cosa:

| ajuste | valor | por qué |
|---|---|---|
| **Remesh** | **sí, ~10-15 k tris** | Lo más importante. Sin él Meshy da una sopa de cáscaras solapadas y hay que decimar; el decimador no fusiona entre cáscaras y las deja hechas esquirlas. Con remesh, una superficie cerrada al presupuesto que pidas. |
| **Modo Ultra** | **apagado** | Triplica los trozos sueltos (431 → 1340) para un detalle que se decima igual. |
| Imagen | 3/4, **alas abiertas** | La pose de la imagen es la pose de reposo, y es la única que vas a tener. Se anima hacia adentro, nunca al revés. |
| Visión múltiple | apagado | Necesita vistas laterales que no existen todavía. |
| Texturas | 4096 | Se bajan aquí a 1024 (alta) o 512 (media). |
| Licencia | privada | |

Y la cadena, dos comandos:

```bash
# crudo -> master normalizado (sin decimar: el remesh ya vino al presupuesto)
blender --background --factory-startup --python tools/normalize-model.py -- \
    source/3d-models/crudo/vexor-texture-v3.glb source/3d-models/vexor-v3.glb 0 1024 r 1.0 0.0005

# master -> asset de juego con esqueleto
blender --background --factory-startup --python tools/riguear-modelo.py -- \
    source/3d-models/vexor-v3.glb <cliente>/pruebas/vexor.glb 0.30 0.22 0.32 3
```

### Los dos diales, y cuál de los dos importa

Medido con 30 bichos en pantalla, sobre gráficos integrados:

| cambio | qué compra | qué cuesta |
|---|---|---|
| **512 → 1024 de textura** | **mucha nitidez** | 170 → 176 fps (nada) · VRAM 3 → 12 MB |
| 10 k → 31 k triángulos | filos algo más suaves | 135 → 83 fps (−38%) |

**Los polígonos cuestan fps; la textura cuesta VRAM.** Y en un bicho cuyo detalle
vive en el mapa de normales, la textura es donde está el retorno. Por eso el
asset va a 10 k tris con textura de 1024 y no al revés.

A 12 MB por especie, los nueve bichos son 108 MB contra los 58 del bestiario en
atlas de hoy. A 512 serían 27 MB. Ahí está el escalón de `quality.gd`: **alta =
1024, media = 512, mismo GLB.**

## Modelos 3D -> asset de juego

`tools/normalize-model.py` convierte lo que devuelve Meshy en algo que el cliente
puede comer. **No es un paso de limpieza opcional: el crudo incumple el contrato
por los cuatro costados** y el primer Vexor lo enseñó de golpe.

```bash
# crudo -> master de trabajo
blender --background --factory-startup --python tools/normalize-model.py -- \
    source/3d-models/crudo/vexor-texture.glb source/3d-models/vexor.glb 200000 1024 r

# master -> asset de juego
blender --background --factory-startup --python tools/normalize-model.py -- \
    source/3d-models/vexor.glb <cliente>/pruebas/vexor.glb 15000 512 r
```

| paso | crudo de Meshy | master de trabajo | asset de juego |
|---|---|---|---|
| triángulos | 1 965 610 | 200 000 | **15 000** |
| textura | 2048 | 1024 | **512** |
| peso | 78,2 MB | 7,4 MB | **0,8 MB** |
| VRAM | 48 MB | 16 MB | **4 MB** |

**Los 15 000 valen para el JUEGO y no para mirar de cerca**, y la diferencia
costó una confusión entera. Medido a 700 px con encuadre cerrado:

| tris | cómo se ve de cerca |
|---|---|
| 3,06 M (crudo) | referencia |
| **200 000** | indistinguible del crudo |
| 50 000 | empiezan a asomar las facetas |
| **15 000** | claramente poligonal: filos rectos, vetas dentadas, púas convertidas en esquirlas |

A tamaño de juego —178 px— los 15 000 se leen perfectos y las esquirlas son
subpíxel. **Pero en cuanto el bicho ocupa el triple, se ven.** Por eso el master
de trabajo va a 200 000: no es margen por si acaso, es el presupuesto para
mirarlo.

La primera versión de esta tabla decía que 15 000 eran indistinguibles de dos
millones. Estaba medida sobre el Vexor v1 y **renderizada a 356 px**, donde
cualquier defecto es subpíxel. Dos errores a la vez, y explicaron un rato largo
buscando en Godot un fallo que estaba en la decimación.

Y para comparar: el atlas animado del mismo Vexor cuesta **11,7 MB** y solo sirve
para un rumbo. El modelo cuesta 4 y sirve para todos, más cualquier elevación de
cámara.

### Las cuatro cosas que arregla, y por qué cada una

- **Tumbarlo.** Meshy lee la imagen como un póster y devuelve el modelo de pie,
  con el largo en Z. Al tumbarlo −90° en X el largo pasa a +Y, que al exportar a
  glTF es −Z, que es el «adelante» de Godot: la proa acaba mirando donde debe sin
  tocar nada más. **El paso es idempotente** — mira la caja y solo rota si el alto
  es la dimensión mayor, porque el script también se corre sobre su propia salida
  y rotar a ciegas ponía el master de pie otra vez.
- **Pivote al centro.** El giro es sobre el origen; descentrado, el bicho orbita
  en vez de virar. No se ve en una captura fija, aparece en cuanto gira.
- **Decimar y bajar texturas.** Ver la tabla.
- **Emisión.** Meshy pinta las vetas y los núcleos en el albedo y deja
  `emissiveFactor` a cero: se ve rojo, pero no es luz. Se derivan por dominancia
  de canal —la misma heurística que `extract-emissive.py`— pero **una sola vez,
  horneada en su textura**, en vez de adivinarla en cada render. En el Vexor el
  22% de la textura emite, y son sus dos núcleos.

### Qué se versiona y qué no

`source/3d-models/crudo/` está **ignorado**: son 78 MB por modelo, diez veces el
archivo más grande de este repo, y git no olvida. Lo que se versiona es el master
de trabajo, del que se re-exporta a cualquier presupuesto. Los dos millones de
triángulos no hacen falta para nada; si alguna vez hicieran, se regeneran desde
Meshy igual que se regeneraría un vídeo.

**Un modelo se valida antes de normalizarlo**, con
`mex-orbit-testing/assets/validar-modelo.py`.

### Elegir la pose: `tools/frames-de-video.py`

Meshy congela **una** pose, la de la imagen que le des, y no hay forma de sacarle
un rango de movimiento. El primer Vexor se generó desde un fotograma con las alas
pegadas al cuerpo, y por eso salió una concha donde el ala y el flanco son la
misma superficie: no hay nada que abrir, y la animación se queda en doblar un
filo.

De ahí la regla, que es lo contrario de lo intuitivo:

> **Modela en la pose más EXTENDIDA y anima hacia adentro.** Un hueso o una clave
> de forma siempre pueden juntar geometría; ninguno puede inventar superficie que
> no se modeló.

```bash
py -3 tools/frames-de-video.py source/renders/Vexor.mp4 source/frames/Vexor 24
```

Saca los fotogramas ya sin croma, todos en el **mismo lienzo cuadrado** —si cada
uno se recortara a su caja, el bicho cambiaría de tamaño entre poses y Meshy
recibiría dos escalas distintas— y **mide el ancho de la silueta** para decir cuál
es el más abierto y cuál el más cerrado. Es el mismo criterio con el que se
encontró la bisagra en la malla, aplicado al vídeo.

En el Vexor: 96 fotogramas, silueta de 695 a 1147 px (un recorrido del 39%),
**f029 el más abierto y f052 el más cerrado**. Y en f029 se ve el fondo entre los
dedos del ala y el cuerpo, que es exactamente la separación que obliga a Meshy a
modelar volúmenes distintos.

Los fotogramas **no se versionan**: se regeneran del `.mp4`, que sí está en git.

### Partir y animar: `partir-en-piezas.py` + rotación de nodos

**Este es el camino bueno.** `animar-alas.py`, más abajo, quedó como referencia
histórica: funciona, pero cuesta tres veces más.

```bash
blender --background --factory-startup --python tools/partir-en-piezas.py -- \
    <entrada.glb> <salida.glb> 0.30 vexor
```

Meshy nunca entrega una cáscara limpia: son cientos de trozos solapados (431 en el
Vexor v1, 1340 en el v2). Eso, que parece un defecto, es la salida — cada trozo se
asigna **entero** a cuerpo, `ala_izq` o `ala_der` según dónde caiga su centro.
Nada se corta, así que no hay agujeros ni interiores huecos, y las UV sobreviven.
La opción «Dividir» de Meshy sobra, y menos mal: entrega las piezas sin textura y
solo deja texturizar el modelo entero.

Y **el movimiento no va en el GLB.** El cliente ya mueve el pulso, la ondulación y
los anillos desde `_process`; plegar un ala es lo mismo, dos rotaciones:

```gdscript
ala_izq.rotation.y = -ang
ala_der.rotation.y =  ang
```

Medido con 150 bichos plegando alas: **149,8 fps por nodos contra 48,4 por clave
de forma**, y solo un 4% por debajo del modelo quieto. Un nodo rotado es una
matriz; una clave de forma son deltas por vértice.

`tools/animar-nodos.py` existe para cuando haga falta una animación *authorada*
dentro del GLB, y documenta dos trampas del exportador que costaron dos pasadas:
hay que poner `rotation_mode = "XYZ"` (el importador deja los objetos en
cuaternión y el exportador tira la animación entera sin avisar), y cada pieza con
su propia Action sale como una animación **separada**.

### Animación por clave de forma: `tools/animar-alas.py`

Meshy da malla estática. Las alas se pliegan con una **clave de forma**, no con
esqueleto: un armature pide modo edición y pintar pesos, y los operadores de modo
fallan en silencio con `--background`. Una clave de forma es dato puro, glTF la
exporta como morph target y Godot la reproduce.

```bash
blender --background --factory-startup --python tools/animar-alas.py -- \
    <cliente>/pruebas/vexor.glb <cliente>/pruebas/vexor-anim.glb 0.26 0.30 42 1 26
```

**La bisagra se mide, no se estima.** En el Vexor el ancho salta de 0,512 a 1,102
en t=0,75: ahí acaban las placas del tórax y empiezan las alas, o sea |x| ≈ 0,26.
Y el mismo perfil confirma el `from: 0.68` de `undulate` medido en el sprite 2D —
el ancho cae de 0,968 a 0,619 en t≈0,28, que es el mismo sitio. **El modelo y el
sprite coinciden en dónde acaba el tórax.**

El pliegue no es rígido: el peso va de 0 en la bisagra a 1 una banda más afuera,
así que el ala se *dobla* en vez de girar en bloque, y de paso no deja arruga dura
en la unión. 26 fotogramas, un ciclo, y **el bucle cierra por construcción** — el
último fotograma repite el primero. Toda la maquinaria de medir la costura y
buscar el valle se cae con esto.

Y sale gratis algo que en 2D costó trabajo: las vetas emisivas se pliegan con las
placas. En el sprite eso obligó a que `undulate` y `undulate_add` compartieran un
include; aquí la emisión es un material de la misma malla y no puede
desincronizarse.

**El precio de la clave de forma está medido, y no es en peso sino en dibujo.**
Cuesta 0,3 MB sobre el asset de juego, pero con 150 instancias en pantalla el
mero hecho de que la malla tenga morph target baja de 190 a 113 fps *sin
reproducir nada*. A población real (20–30 bichos) el coste es del 17–22% y el
suelo se queda en 109 fps. Si algún día hicieran falta 150 bichos animados a la
vez, la salida es esqueleto: unas pocas matrices en vez de deltas por vértice.

### Lo que el pipeline de modelos NO resuelve

El **abdomen que ondula** no se hornea. `undulate` es continuo y reacciona al
estado (`idle: 0.5` es cuánto se menea parado), así que en 3D pasa a ser un vertex
shader o un hueso movido por código — nunca keyframes, que lo congelarían.

Y el **pulso emisivo** tampoco: es luz, no geometría. Pero gana algo al mudarse.
Hoy corre en su propio reloj (`speed: 3.2` → periodo 1,96 s) al lado de un ciclo
de alas de 2,17 s: se separan del todo cada ~21 s, así que el destello *no* está
sincronizado con el aleteo aunque lo parezca. Con la animación en el GLB, el
shader puede leer su fase y entonces el destello cae en el aleteo por
construcción.

## Relación con otros repos

| Repo | Relación |
|---|---|
| `mex-orbit-client` | Consumidor de las exportaciones |
| `mex-orbit-docs` | El pilar 05-arte define la dirección; aquí se ejecuta |
| `mex-orbit-testing` | Valida los assets antes y después: `validar-video.py`, `validar-modelo.py` |

## Estado

Repo recién creado.


### El halo horneado: por qué media lleva glow dentro del PNG

En calidad **alta** el brillo del rojo lo hace el `Environment` del `SubViewport`
con `glow_enabled`: lo que pasa de 1 se **derrama** a los píxeles vecinos. En
**media** no hay entorno, hay un PNG — y sin halo horneado el resultado no era
más oscuro, era **de otro carácter**: mismo brillo medio, pero media con
manchones planos reventados y alta con el rojo vivo y halo.

Medido sobre el mismo bicho (rojo medio del píxel y % de píxeles por encima de
0,8, recortando a 1 en los dos lados porque es lo que la pantalla da):

| | rojo medio | reventados |
|---|---|---|
| media, antes | 0,370 | 19,1 % |
| **media, con halo horneado** | **0,373** | **10,1 %** |
| alta con glow (la referencia) | 0,377 | 8,7 % |

El 1,4 % que queda es diferencia de **encuadre** entre las dos imágenes, no de
acabado: la silueta de media ocupa 98 687 px y la de alta 79 200. Afinar más sería
perseguir ruido de la propia medición.

**Los cuatro diales** (`GLOW_*` en `hornear-sprite.py`, todos con variable de
entorno del mismo nombre para poder barrerlos sin editar):

| dial | valor | qué hace |
|---|---|---|
| `GLOW_NUCLEO` | 0,09 | atenúa el núcleo. El horneado sale **más caliente** que la emisión de Godot al mismo pulso; sin bajarlo, media revienta el doble |
| `GLOW_UMBRAL` | 0,25 | desde dónde brilla, sobre el color **premultiplicado** |
| `GLOW_RADIO` | 0,06 | cuánto se extiende, en fracción del lado |
| `GLOW_FUERZA` | 1,8 | cuánto se devuelve como halo |

Tres cosas que costaron una pasada cada una y no son obvias:

- **El halo sale de la emisión original y el núcleo se atenúa después.** Al revés,
  bajar el núcleo dejaba la imagen por debajo del umbral y el halo desaparecía.
  Es además lo físico: un bloom reparte energía, no la quita.
- **El alfa tiene que crecer con el halo.** Cae fuera de la silueta, donde el
  render trae alfa 0, y el cliente monta esta capa en blend **aditivo**, que
  multiplica por alfa. Sin devolvérselo, el halo se multiplica por cero.
- **La ruta de salida se pasa a absoluta.** Blender resuelve un `render.filepath`
  relativo contra su propia ruta base, no contra el directorio de lanzamiento: con
  `exports/horno` el render se fue a un sitio fantasma, el script dijo que había
  horneado y los PNG se quedaron igual. Sin error ninguno.


### Los diales son POR BICHO, no del pipeline

Los valores por defecto de `hornear-sprite.py` y las bisagras de `riguear-modelo.py`
se calibraron con el Vexor. **No se heredan**: cada bicho se mide. El Vex lo dejó
claro — es más largo que ancho, al revés que el Vexor, y emite en un solo ojo en
vez de en toda la superficie.

| | Vexor | Vex | Ferox | Skarnox |
|---|---|---|---|---|
| caja (ancho × largo × alto) | 1,911 × 1,611 × 0,590 | 1,526 × 1,916 × 0,548 | 1,071 × 1,903 × 0,567 | 1,906 × 1,786 × 1,353 — **bola achatada** |
| triángulos | 10 254 (remesh ya al presupuesto) | 12 000 (crudo a 31 148, decimado) | 12 000 (crudo a 31 181, decimado) | 10 150 (remesh ya al presupuesto) |
| `BISAGRA` / `BANDA` del ala | 0,30 / 0,22 | **0,18 / 0,16** | **0,24 / 0,14** | sin alas (3,0) |
| `COLA_DESDE` | 0,32 | **0,24** | **0,28** | 0 — sin cola |
| `CUERNO_DESDE` | 0,13 | 0,12 | **0 — sin cuernos** | 0 — solo raíz |
| `GLOW_NUCLEO` | 0,09 | **0,22** | 0,09 | 0,09 |
| `GLOW_UMBRAL` | 0,25 | 0,25 | 0,25 | **0,05** |
| `GLOW_RADIO` / `GLOW_FUERZA` | 0,06 / 1,8 | **0,09 / 3,8** | 0,06 / 1,8 | **0,20 / 1,6** |
| `HORNO_SOL` / `HORNO_AMBIENTE` | 1,35 / 0,65 | 1,0 / 0,45 | 1,6 / 0,65 | **0,4 / 0,1625 — luz propia** |
| ganancia de emisión | 1,0 | 1,0 | 1,0 | **2,0** |
| emisión derivada | 38-47 % de la textura | 16,5 % | 5,4 % real (ver abajo) | grietas + núcleo, p99 0,54 |
| `cuernos_grados` (cliente) | 14 | **0 — no se lee** | — | — |

Cómo se sacó cada uno:

- **Las bisagras, del perfil de la malla.** El ancho por banda de Y da el salto:
  en el Vex, `|X|` p95 pasa de 0,101 a 0,749 entre Y −0,599 y −0,479, así que ahí
  empiezan las alas y ahí acaba la cola (`COLA_DESDE` = 0,24 del largo).
- **`GLOW_*`, barriendo contra la medición.** El Vex emite en un solo ojo, así que
  subir el núcleo casi no mueve la media (0,09 → 0,22 solo dio 0,201 → 0,205): la
  palanca es el halo. Con radio 0,09 y fuerza 3,8 media queda en **0,231** contra
  los **0,233** de alta.
- **`cuernos_grados` = 0 porque se midió.** A 35° el cuerno del Vex desplaza su
  centroide **0,51 px** contra los 2,28 del Vexor, y a su tamaño real de 141 px la
  pose y el reposo son indistinguibles. Sus cuernos son más verticales: el giro no
  cambia la silueta. Animar lo que no se ve es gastar por nada.
- **El Ferox y la cobertura que asusta sin razón.** `normalize-model.py` reporta
  que con canal `r` emite el **80,6 %** de su textura — huele a la trampa de la
  estación (encender el casco entero), pero medido no lo es: el marfil del cuerpo
  es apenas r-dominante (máscara ~0,04, emisiva resultante ~0,02) y los acentos
  reales —ojos y vetas rojas, albedo 0,72/0,19/0,21— son el **5,4 %** por encima
  de 0,35 con p99 de 0,62. La cifra de cobertura sola no dice nada: hay que mirar
  la **distribución** de la máscara antes de tocar el canal o la ganancia. Con los
  `GLOW_*` por defecto media homologa sin tocar nada: rojo medio 0,464 contra
  0,474 de alta con glow al pico del pulso.
- **Sus cuchillas son las alas, y la bisagra tiene el valle en |X| 0,22–0,26**: el
  cuerpo acaba en 0,20 y el lóbulo de la cuchilla va de 0,26 a 0,54. En el cliente
  van a **30° en el eje 1** (a +30 se pliegan al cuerpo, a −30 se abren en abanico,
  sin cruzarse; cada extremo cambia la silueta un 30 % a 190 px) y la cola a
  **12° en el eje 2** (el 0 no la mueve: 0,4 % de silueta).
- **El Skarnox es una bola y su palanca de horno es el UMBRAL.** Ni la geometría ni
  la concentración de la máscara delatan el cráter (radios 0,865–0,909, concentración
  0,07): se localizó **rendiendo las seis vistas** — miraba a −Y, y el tumbado
  estándar de −90 en X lo deja en el alto. Ojo: el eje «fino» de su caja (1,873 en Y,
  un 1,5 % menor) es ruido — el tumbado acertó de casualidad; en una bola la
  orientación se dice y se verifica con render. Y en el horno, `GLOW_NUCLEO`/`FUERZA`
  no movían la media (0,196 → 0,201 con núcleo ×2,4: puntos calientes, no derrame)
  porque `GLOW_UMBRAL=0,25` está por encima de lo que las grietas rinden **a pulso 1**
  — el halo se calcula antes de multiplicar por el pico del pulso, mientras el bloom
  de alta ve la emisión ya multiplicada. Y cuando la lava pidió más color, la
  palanca fue la **ganancia de emisión en el normalizador** (1,0 → 2,0): doblar la
  fuente obligó a bajar la fuerza del halo de 4,2 a **2,0** — el halo pertenece a
  la pareja modelo+emisiva, igual que `HORNO_AMBIENTE` pertenece a la pareja
  modelo+textura en la Phoenix. Cada retexturizado lo volvió a demostrar: el v2
  (p99 0,671 contra 0,537) bajó la fuerza de 2,0 a 1,2, y el v3 (p99 0,749, el
  vigente, ya bajo la luz nueva del mundo) la dejó en **0,9** — media 0,450
  contra 0,450 de alta con glow al pico (pulse 2,6), clavado. Desde el v2 ya no
  es bola perfecta (alto 1,353): entra «ya en el plano» con eje fino real y las
  seis vistas confirman el cráter al alto sin girar nada. El resto
  de su intensidad vive en el JSON: suelo del pulso en 1,2 (la lava no se apaga),
  el pase de `lava` que viaja (solo de alta), y desde ago-2026 el bloque **`luz`**
  — la excepción por bicho a la luz del mundo: el Skarnox va a **un cuarto** del
  mundo (sol 0,25, ambiente 0,1625) para leerse autoiluminado. El horno lo espeja
  (sol 0,4 = 0,25 × 1,6 axial, ambiente igual) y con la base oscura el halo tuvo
  que volver a subir a **1,6**: el derrame del glow pesa más cuanto menos luz
  exterior hay. Media 0,332 contra 0,333 de alta.

### Naves: los anclajes de motores y cañones

Una nave necesita dos cosas que un bicho no: por dónde escupen los motores y por
dónde sale el láser. En 2D son puntos en píxeles de la textura y funcionan porque
las llamas cuelgan del sprite y giran con él. **En 3D el sprite ya no gira** —gira
el modelo dentro del viewport— así que unas coordenadas de textura se quedarían
clavadas en pantalla mientras la nave da la vuelta.

`tools/marcar-anclajes.py` mete en el GLB nodos vacíos `tobera_1..N` y
`canon_izq`/`canon_der` con su posición **en unidades del modelo**, que es lo único
que sobrevive a un cambio de encuadre. Es la convención que `validar-modelo.py` ya
comprobaba desde antes de que existiera la herramienta.

```bash
blender --background --factory-startup --python tools/marcar-anclajes.py -- \
    source/3d-models/phoenix.glb <cliente>/assets/ships/phoenix.glb 0.09 0.75 60 4
```

Las posiciones se **miden**: de cada tobera se toma su punto más trasero (la llama
sale de la boca, no del centro de masa) y de cada cañón la punta delantera (un
cañón es un tubo). Medido en el Phoenix: toberas en X −0,262 / −0,125 / +0,125 /
+0,258, que en proporción son los mismos cuatro motores que el JSON 2D tenía en
−58 / −25 / 24 / 57.

**El número de toberas se pasa como argumento** y no se adivina. Contarlas por los
valles del histograma falló dos veces: el valle entre la tobera de fuera y la de
dentro de cada lado tiene 129 vértices contra una media de 164, así que el Phoenix
salía con 2. Con el número dado se usa la **simetría** de la nave —partir por el
centro y cada lado en dos— y solo se aceptan cortes que dejen los dos lados con
tamaño suficiente; sin esa condición el corte se va a los bins del borde, donde
por construcción hay pocos vértices, y el grupo no llega a partirse.


### El horno también tiene luz, y ahora ESPEJA la del cliente

**Desde el cambio de luz del mundo (ago-2026)** el horno replica el rig del
cliente (`AssetDefs.ambiente_mundo`): fondo del color del ambiente (azul grisáceo
0,35/0,40/0,55 — antes el nodo Background se quedaba en el gris 0,05 por defecto
de Blender y la fuerza multiplicaba casi-nada, por eso los valores viejos parecen
de otra escala), **la curva FILMIC exacta de Godot sobre el pase BASE**
(`HORNO_FILMIC`, encendida por defecto: el filmic con blanco 1 levanta los medios
0,5 → 0,69, y sin ella perseguir la diferencia con ambiente lavaba el contraste
sin llegar), y defaults `HORNO_SOL=1.6` / `HORNO_AMBIENTE=0.65` — 1,6 y no 1,0
porque el sol del sprite es axial y el del cliente rasante a −48°.

Calibrado por bicho contra `medir_emision.tscn` (media / alta, al pico del pulso):

| | `HORNO_SOL` | `HORNO_AMBIENTE` | media | alta |
|---|---|---|---|---|
| Vexor | 1,35 | 0,65 | 0,479 | 0,459 |
| Vex | 1,0 | 0,45 | 0,276 | 0,286 |
| Vorax | 1,0 | 0,55 | 0,243 | 0,236 |
| Ferox | 1,6 | 0,65 | 0,631 | 0,600 |
| Skarnox | 1,6 | 0,65 | 0,471 | 0,447 |
| Phoenix | 1,6 | **0,35** | 0,301 | 0,288 |

**Para un metal el ambiente va al revés que antes.** Un metal casi no tiene
difuso: devuelve lo que hay alrededor. En la era del fondo gris-0,05 la Phoenix
necesitaba `HORNO_AMBIENTE=1.7` para no salir negra; con el fondo ya del color
del ambiente real refleja de sobra y el dial baja a **0,35** — menos que un
bicho, porque en Godot el metal ni siquiera ve el ambiente de color (no hay
mapa de reflexión) y en Blender sí. El dial sigue siendo de la **pareja
modelo+textura** y se recalibra con cada cambio de cualquiera de los dos.
Y ojo: homologar es parecerse al modelo en alta, no al PNG que había antes.

**La ESTACIÓN es el caso extremo de todo lo anterior**, y estrenó dos diales:
`HORNO_ELEVACION=30` (la cámara oblicua del cliente, con el encuadre de
`extension_vista` — las ocho esquinas proyectadas, no la huella) y
`HORNO_LUZ=mundo` (no rota, así que la regla de la luz axial no aplica y lleva
el sol direccional real, azimut 315 y elevación −48). Su casco es metálico por
textura, así que el ambiente le baja hasta **0,15** — con 0,65 media salía un
75 % más clara que alta. El halo va apagado (`GLOW_FUERZA=0`, igual que su
`glow: false` de alta) y `GLOW_NUCLEO=3.0` hace de ganancia: cuece en la capa
emisiva el `emision: 3.0` del modelo, porque el pulso 2D no lo multiplica.
Homologado en el juego contra alta: 0,0749 contra 0,0809 en el mismo recorte.
Su atlas de video queda como respaldo con la luz vieja: solo se monta si el
GLB no carga.

## Dos casos que el Vorax destapó en la cadena 3D

**El eje fino no siempre entra en Y.** `normalize-model.py` tumbaba el modelo mirando cuál es la
dimensión menor, y solo sabía hacerlo desde Y. El Vorax llegó con el fino en **X**, así que imprimió
un aviso y **no tumbó nada** — y como ese aviso convive con un «ya venía en el plano» en la línea
siguiente, el modelo se dio por bueno **de pie**. Lo cazó el validador, no el script.

Ahora cubre las dos entradas. El contrato son dos cosas, no una: el eje fino acaba en **Z** (el alto
de un juego cenital) y el largo en **+Y** (que al exportar a glTF es −Z, el «adelante» de Godot).
Desde X hacen falta dos giros —+90 en Y y +90 en Z—; ninguno de 90° sobre un solo eje lleva dos ejes
a la vez a donde se quiere.

**Un bicho puede no tener alas.** `riguear-modelo.py` montaba `ala_izq`/`ala_der` y
`cuerno_izq`/`cuerno_der` siempre. En un gusano no hay dónde: el perfil del Vorax no da un solo salto
lateral (0,41 de ancho en la proa a 0,22 en la popa, sin escalón). Forzar la bisagra por encima del
ancho máximo los habría creado igual, **sin un solo vértice que pese en ellos** — y un hueso muerto no
avisa, se descubre el día que alguien intenta animarlo. Peor aún: la bisagra también acota los
cuernos, así que subirla les habría dado la cabeza entera.

Las alas se saltan si **ningún vértice pasa la bisagra** (la señal es la malla, no un parámetro), y
los cuernos con `CUERNO_DESDE = 0`. Y el peso pasa a **cero**, no a la rampa: dejar la rampa haría que
los vértices del borde pesaran en un hueso inexistente y al normalizar le robaran peso al cuerpo, que
es como se aplasta una malla sin que nadie sepa por qué.

| Vorax | valor | de dónde sale |
|---|---|---|
| tris | 14 998 | el crudo traía 28 126, el doble del presupuesto |
| `BISAGRA` | 0,50 | por encima del ancho máximo (0,430) = sin alas |
| `CUERNO_DESDE` | 0 | los dientes son un anillo, no un par simétrico |
| `COLA_DESDE` / `COLA_SEG` | 0,78 / **6** | casi todo el cuerpo ondula, y una onda que recorre necesita más segmentos que un coletazo |

## Emisión de color SECUNDARIO, y el rig radial

**Un color secundario no lo ve la extracción por canal.** La máscara era
`canal − max(los otros dos)`, y el cian es verde **y** azul altos a la vez: ninguno domina al otro, así
que sale ~0. Medido en el Vorax de cristales: por canal, el verde cazaba un 6,3% con p99 de 0,031
—ruido— y el azul un 0,0%. Como cian (`min(g,b) − r`): un 40% con p99 de 0,569.

No es que el bicho no brillara: **la herramienta no sabía mirar**, y habría pasado por la cadena sin
emisión y sin un solo aviso. Ahora el canal acepta `c/m/y` además de `r/g/b`.

**Y un bicho puede ser radial.** `riguear-modelo.py` sabía de alas, cola y cuernos. El Vorax es una
estrella de ocho tentáculos: con `RADIAL=8` monta un anillo de huesos hermanos colgados de la raíz.
Los ángulos **se miden** de la malla con un histograma angular circular —el envolvente importa: sin él
un brazo a 358° se parte en dos— y salen irregulares: 36, 84, 102, 122, 146, 188, 286 y 342. Repartir
360/8 habría puesto huesos entre dos brazos.

El peso de un brazo es el producto de dos rampas, **radial y angular**: con solo una, el hueso se
lleva un anillo entero o una cuña que llega al centro. Y los brazos vecinos se reparten el solape en
vez de sumar más de 1 — el mismo fallo que tuvieron los cuernos.

**Tercer interruptor: la cola.** Intentar apagarla con los diales no la apaga; deja `cola_1` cogiendo
peso entero encima del de `raiz`, y la suma por vértice salió **2,000 exacto** — la firma de dos huesos
reclamando lo mismo al 100%. Ahora `COLA_SEG = 0` la salta, como `BISAGRA` alta salta las alas y
`CUERNO_DESDE = 0` los cuernos.

## La estación: dos casos que un bicho no tiene

**Un asset puede tener DOS colores de acento.** La estación lleva el rótulo en magenta (p99 0,298) y
las ventanas en cian (p99 0,153): con un solo canal, uno de los dos se queda apagado. Y pedir el de
más cobertura era peor —el azul domina en el **92,2 %** de la textura porque el casco entero es
azul-gris, así que habría encendido la torre entera. El canal acepta ahora una suma: `c+m` toma el
**máximo** de las dos máscaras, no la suma, porque un píxel es del acento que más domine y no de los
dos a la vez.

**Y no todo se tumba.** El contrato del normalizador —el eje fino acaba en el alto— codifica «objeto
plano visto desde arriba», que es lo que son los bichos y las naves. Una estación es una **torre
vertical**: tumbarla la acuesta. No hay heurística que distinga los dos casos mirando la caja, porque
la diferencia no está en el modelo sino en cómo se mira, así que se dice con `TUMBAR=0`.

| estación | valor | por qué |
|---|---|---|
| `TUMBAR` | **0** | es una torre, no un objeto plano |
| tris | 30 228, **sin decimar** | es UNA instancia, no quince como un Vex |
| canal | `c+m` | rótulo magenta + ventanas cian |
