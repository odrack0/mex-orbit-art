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

**Los 15 000 no son un recorte prudente: están medidos.** A tamaño de juego no se
distinguen de los dos millones, porque el detalle vive en el mapa de normales y
no en los polígonos. A 5 000 se empiezan a redondear las púas.

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
