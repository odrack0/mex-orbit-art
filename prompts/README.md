# Prompts de render — assets del slice E2

Prompts listos para el generador de imágenes (Gemini / Recraft). El **contrato de render** aplica a todos —
violarlo invalida el render para el pipeline:

1. **Ortográfica cenital estricta** (top-down puro; la IA deriva a 3/4 — rechazar esos intentos).
2. **Proa hacia arriba**, centrada.
3. **Luz axial desde la cámara** (sin dirección lateral: con rotación libre en Godot un reflejo lateral "gira" y canta).
4. **Fondo verde croma plano** (`#00B140`), sin sombra proyectada al suelo, sin viñeta.
5. **1024×1024**, la nave ocupando ~70% del lienzo.
6. Escala relativa coherente entre naves (la Phoenix es pequeña; anotada en cada prompt).

Al recibir el render: validar la silueta a tamaño de juego (~150 px) antes de exportar.

**Los efectos no siguen este contrato**, y no es un descuido: un láser no tiene proa ni cenital que
respetar. Lo suyo son otras dos reglas —blanco y negro puro, porque el juego los tiñe con `modulate`
según la munición, y fondo negro en vez de transparente, porque se dibujan en blend aditivo— y viven
en el prompt de cada uno.

## Contrato del CONCEPTO 3D (2-sep-2026) — el que manda desde el cliente 3D

> El contrato de arriba era para el pipeline de sprites (cenital, croma, luz axial) y quedó como
> historia. Desde el 1-sep el cuerpo de cada entidad es una malla, y la imagen de Gemini ya no es el
> asset: es la **instrucción de Meshy** (image-to-3D + textura). Todo lo que Gemini pinta en la imagen
> —sombras, brillos, halos, fondo— Meshy lo interpreta como textura, y en el juego pelea con la luz
> del mundo. Estas reglas salen de cómo ilumina el cliente (`data/config/lighting.json`) y de cómo se
> extrae el emisivo (`normalize-model.py`, por color dominante).

1. **Vista 3/4 desde arriba, ~45°** (la cámara del juego tilt 45°): el 3/4 ya no se rechaza, es el
   que Meshy necesita para leer el volumen y el que tú vas a ver en el juego. La cara superior lleva
   la identidad (ojos, luces, placas): un bicho se ve desde arriba, nunca por la panza.
2. **Luz de estudio suave y pareja, sin dirección marcada, sin sombras duras ni rim light.** El
   mundo tiene UN sol blanco desde arriba-izquierda (tilt 100 / pan 35, especular 0,7), ambiente
   rosado tenue (`ffa5ae` a 0,2) y el cliente añade brillo cerrado (roughness 0,35) y fresnel de
   borde a TODO material. Una sombra pintada en la textura no gira con el bicho: canta.
3. **Cuerpo de valor medio-oscuro, no negro ni blanco.** Gris plomo / obsidiana / quitina oscura
   (albedo ~25–45 %). El negro puro se vuelve una mancha plana con el ambiente a 0,2 (el Drony); el
   blanco se quema con el especular. Contraste contra el fondo del 1-1 (nebulosa naranja sobre
   negro): un cuerpo naranja o rojo se funde con la nebulosa salvo que sea lava emisiva.
4. **Las luces, como PARCHES PLANOS de un solo color saturado, sin halo ni núcleo blanco.** El
   emisivo se extrae por color dominante: cian `#00FFFF`, magenta `#FF00FF`, rojo `#FF2000`,
   verde `#00FF40`, amarillo `#FFE000`. Un glow pintado (halo degradado, centro blanco) es cian
   pálido en la textura y en el juego no emite nada — la lección del Drony. El brillo lo pone el
   cliente (pulso, glow, lava). Un color de luz por especie.
5. **Pocas formas grandes, nada de detalle fino.** Un bicho mide 124–248 px en pantalla: 3–6
   volúmenes que se lean en silueta, luces de al menos un 8 % del ancho del cuerpo, sin rótulos,
   decals, tornillería ni cableado (se convierte en ruido que hierve al moverse; el detalle medio lo
   conserva el horneado de normales, el fino no existe a ese tamaño).
6. **Materiales opacos que Meshy sepa hacer**: metal pintado, roca, hueso, quitina, cristal OPACO.
   Nada de transparencias, vidrio, pelo, partículas, humo, alas de gasa: no hay transparencia en la
   cadena y Meshy las sustituye por manchas.
7. **Fondo liso gris neutro** (`#808080`), sin suelo, sin sombra proyectada, sin viñeta. El croma
   verde ya no hace falta y su rebote tiñe los bordes.
8. **Lo que se vaya a articular, separado del cuerpo**: alas, cola, cuernos, brazos radiales como
   lóbulos claros con una «bisagra» visible; el rig corta por esa posición (ver skill
   `mexorbit-asset-3d`). Lo fusionado no se puede animar sin inventar geometría.
9. **Pose de reposo, centrado, ocupando ~70 % del lienzo, 1024×1024 o más.** Una sola pieza en la
   imagen: nada de vistas múltiples ni turnarounds (Meshy los mezcla).

Antes de mandarlo a Meshy: reducir la imagen a **150 px** y mirarla. Si no se distingue de un
círculo gris, no va a mejorar en 3D. En Meshy: generar SIN textura (el alto de 1,5–3 M), remesh a
4–7 k quads, texturizar el remesh usando **esta misma imagen** como referencia (no texto), y medir
el emisivo al exportar (≥ 3 % de la textura con p99 > 0,5 en el canal elegido; si no, retexturizar
en Meshy, no subir ganancias aquí).

Plantilla (Gemini):

```text
Concept render of a [sci-fi combat drone / mineral alien / ...] for a top-down space game.
Single object, resting pose, centered, filling ~70% of the frame, seen from a 3/4 view slightly
from above (about 45°). Clean studio lighting: soft, even, no strong shadows, no rim light, no
lens flare, no bloom. Body: [dark gunmetal grey painted metal / obsidian chitin] with 3-5 large
readable shapes, no text, no decals, no small greebles. Lights: [one large lens eye + 3 wide
strips], painted as FLAT SOLID saturated [cyan #00FFFF] patches with hard edges — no glow, no
halo, no white center. Opaque materials only. Plain flat mid-grey background (#808080), no
ground, no cast shadow, no vignette. 1024x1024.
Negative: black body, white lights, glowing halos, bloom, dramatic lighting, cast shadows,
transparency, glass, fur, smoke, particles, multiple views, text, watermark.
```

## Post-proceso (pipeline PNG — dictamen 2026-08-25)

**El master canónico es el render recortado** (`source/renders/*-cut.png`); los exports del juego son
downscale Lanczos directo — cero pérdida. La vectorización quedó retirada del pipeline (posterizaba el
brillo y mordía los contornos); `tools/vectorize-ship.py` se conserva solo como herramienta de estilo.

```bash
py -3 tools/chroma-key.py source/renders/<Asset>.jpeg source/renders/<asset>-cut.png
py -3 tools/export-png.py            # regenera todos los exports (naves/NPCs 512, estación 1024, props 256)
```

Extras del pipeline:
- `tools/extract-emissive.py` — capa emisiva (núcleo/venas/reactor) para glow animado en el juego.
- `tools/obsidiana.py` — pasada de coherencia del catálogo (casco obsidiana, especulares oro, decorado turquesa), con dial de fuerza.

| Asset | Archivo de prompt | Export |
|---|---|---|
| Nave inicial Phoenix | [`phoenix.md`](phoenix.md) | `exports/phoenix.png` (512) |
| Alien Vex | [`vex.md`](vex.md) | `exports/vex.png` + `vex-emissive.png` (512) |
| Alien Vexor (forma mayor del Vex) | [`vexor.md`](vexor.md) | `exports/vexor.png` + `vexor-emissive.png` (512) |
| Alien Skarn (especie mineral) | [`skarn.md`](skarn.md) | `exports/skarn.png` + `skarn-emissive.png` (512) |
| Alien Skarnox (forma mayor del Skarn) | [`skarnox.md`](skarnox.md) | `exports/skarnox.png` + `skarnox-emissive.png` (512) |
| Alien Gravit (forma **menor**, hierro macizo) | [`gravit.md`](gravit.md) | `exports/gravit.png` + `gravit-emissive.png` (512) |
| Alien Mordax (fauces, agresivo de cerca) | [`mordax.md`](mordax.md) | `exports/mordax.png` + `mordax-emissive.png` (512) |
| Alien Gravon (forma **mayor** del Gravit) | [`gravon.md`](gravon.md) | `exports/gravon.png` + `gravon-emissive.png` (512) |
| Alien Vorax (el devorador, huye malherido) | [`vorax.md`](vorax.md) | `exports/vorax.png` + `vorax-emissive.png` (512) |
| Alien Ferox (cazador óseo) | [`ferox.md`](ferox.md) | `exports/ferox.png` + `ferox-emissive.png` (512) |
| Estación base | [`station.md`](station.md) | `exports/station.png` + `station-emissive.png` (1024) |
| Caja de carga | [`caja.md`](caja.md) | `exports/cargo-box.png` + `cargo-box-emissive.png` (256) |
| Portal | [`portal.md`](portal.md) | `exports/portal.png` + `portal-emissive.png` (256) |
| Láseres (haz normal y potenciado) | [`laseres.md`](laseres.md) | `exports/beam.png` (156×24) + `beam-skilled.png` (156×40) |
