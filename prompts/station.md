# Estación base — el ancla de la facción

**Identidad**: el hogar. Donde se descarga, se refina, se vende y se repara. Debe sentirse segura y masiva —
la estructura más grande del mapa 1-1 con diferencia. Identidad de facción visible (acentos cian en v1).

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a large hexagonal space station platform, perfectly centered.
> Massive industrial docking platform with a bright glowing cyan core reactor at the center, six armored
> segments with panel lines and greebles, four docking arms extending outward to a thin outer docking ring,
> small landing pads with dashed guide lines, tiny position lights at the corners. Dark gunmetal and obsidian
> structure with turquoise-cyan emissive accents — industrial sci-fi, high detail, video game asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.
> The green background is a matte backdrop only: it must NOT light the subject — no green rim light,
> no green reflection or bounce on the edges, no green glow around the silhouette.

**Escala**: ~2× el diámetro de la nave más grande; en juego rinde a ~300 px.

## Vídeo en bucle (calidad alta)

En calidad alta la estación se anima; en media y baja se queda en su **primer fotograma**, igual que la
caja de carga. Eso obliga a algo que no aplica a los bichos: **el fotograma 0 tiene que valer como
imagen fija**, porque es lo que verá la mayoría. Nada de arrancar a media rotación ni con el reactor
apagado.

**Lo que el primer intento hizo mal, para no repetirlo.** El vídeo llegó en vista **oblicua de 3/4**:
una torre alta y estilizada, vista desde arriba y de lado. El contrato de render ya avisa de esto en su
punto 1 —"la IA deriva a 3/4, rechazar esos intentos"— pero aquí hay una razón de diseño más profunda
que conviene entender antes de volver a pedirlo:

> **Una estructura vertical no sobrevive a una cámara cenital.** Desde arriba, una torre es un punto.
> La estación actual es un disco radial *porque* eso es lo que se lee desde arriba, y es simétrica de
> revolución *porque* así no tiene proa que contradiga su posición en el mapa. El diseño puede cambiar
> —es tu decisión—, pero tiene que seguir siendo **ancho y radial**, no alto.

También traía texto cocido en el casco ("ASTRION"). Un rótulo dentro del asset no se puede traducir y
el nombre del juego todavía es provisional: los nombres van en la UI, no en la textura.

### Prompt

> Strict top-down orthographic view of a large space station, camera directly overhead, perfectly
> centered. The station is WIDE and RADIAL, not tall — a flat industrial platform seen from directly
> above, radially symmetric with no front or back. Bright glowing cyan core reactor at the center,
> armored segments with panel lines and greebles, docking arms extending outward to a thin outer
> docking ring, small landing pads, tiny position lights. Dark gunmetal and obsidian structure with
> turquoise-cyan emissive accents only — no magenta, no pink, no purple. No text, no logos, no
> lettering anywhere on the structure.
>
> ANIMATION, 4 seconds, seamless loop — the last frame must match the first exactly.
> The camera is ABSOLUTELY FIXED: no zoom, no pan, no orbit, no dolly. The station does not move,
> drift or change size; it stays centered and the same scale in every frame.
> Only these parts move: the outer docking ring rotates slowly and continuously, the core reactor
> pulses and breathes, the position lights blink softly in sequence, small vents release faint wisps.
> Lighting strictly from directly above (camera axis), constant — no moving highlights.
> Flat solid chroma green background (#00B140), no vignette, no ground shadow, no other objects.

**Por qué el aro exterior es lo que gira**: es la única pieza que puede rotar sin romper el bucle ni
delatar una proa, porque ya es un círculo. Girar el cuerpo entero pondría a la estación a dar vueltas
sobre el mapa, que no es lo que hace una base.

### Exportar

```bash
RANGO=0:47 py -3 tools/video-atlas.py source/renders/Base.mp4 exports/station-anim.png 12 384
```

La celda sale del `world_size` (820 u) igual que en todos los demás; se ajusta al medir el render.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Base.jpeg source/renders/station-cut.png
py -3 tools/vectorize-ship.py source/renders/station-cut.png world/props/station.svg 10 2 2.2 20 5 0.32
```

Parámetros muy aligerados (la pieza más grande del slice): calibrados 2026-08-25. Dos lecciones de esta pieza,
ya integradas en `chroma-key.py`: (1) los huecos grandes NO se rellenan — el vano entre el anillo de atraque y
la plataforma es fondo legítimo (5º argumento `HOLE_MAX`, default 2500 px); (2) el verdor se mide contra
`max(r,b)`, no la media — si no, el núcleo cian brillante se recorta como croma.

## El ribete verde-azulado del contorno (v2)

El segundo vídeo llegó con **luz de rebote del croma en el borde**: el 57% del anillo exterior del
objeto, medido en el vídeo sin tocar, tiene verde y azul por encima del rojo, media (55, 83, 88). En
pantalla se ve como un ribete sucio que parece un recorte mal hecho, y no lo es.

Esa luz **está pintada en el arte**. El recorte del croma separa mezcla, no iluminación: puede quitar
lo que el fondo aportó al píxel, no lo que el fondo aportó a la escena. Se probó a despillar solo el
anillo restando en la dirección del croma y el borde salió magenta, porque en la base el teal del
rebote y las tiras de luz cian del propio diseño son el mismo píxel.

Por eso el prompt lo pide explícitamente. Al recibir el vídeo se comprueba **antes** de exportar nada,
que es cuando todavía se puede pedir otro.

## Celda y fps de la base

No es un bicho: se dibuja a 820 px de ancho, así que la celda manda sobre el número de fotogramas. La
primera exportación fue 48 fotogramas a 12 fps con celda 320×532, o sea el render reducido a la mitad
y ampliado 2,56× — contornos deshechos. La buena es **16 fotogramas a 4 fps con celda 632×1048**, la
resolución completa del render:

```bash
RANGO=0:15 py -3 tools/video-atlas.py source/renders/Base.mp4 exports/station-anim.png 4 632x1048
```

Sale barato porque el movimiento es lento: triplicar el intervalo entre fotogramas solo subió el paso
normal de 2,25 a 3,00 sobre 255. Si el render nuevo se mueve más, ese número lo dirá antes de verlo.

**Y hay una salida mejor si alguna vez hace falta fluidez de verdad**: pedir el vídeo con **cámara
fija y que se muevan solo las luces**. Entonces el cuerpo va en un PNG nítido y barato y solo la capa
emisiva se anima, que es el patrón que ya usan la caja y el portal en calidad media. Se intentó
separar así este vídeo restando el mínimo temporal y no salió, porque aquí se mueve la base entera.
