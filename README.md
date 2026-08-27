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

## Relación con otros repos

| Repo | Relación |
|---|---|
| `mex-orbit-client` | Consumidor de las exportaciones |
| `mex-orbit-docs` | El pilar 05-arte define la dirección; aquí se ejecuta |

## Estado

Repo recién creado.
