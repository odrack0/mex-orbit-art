# Assets del vertical slice E2 — inventario y estado

**Actualizado: 2026-08-25.** El slice (*login → volar → matar un Vex → recoger carga → base → refinar →
almacén → vender*) necesita exactamente esto para ser jugable. Regla de origen por tipo:

- **Todo lo renderizado** (naves, NPCs, estación, caja, portal) → pipeline **PNG directo** (dictamen 2026-08-25): render cenital 1024 → `chroma-key.py` → downscale Lanczos (`export-png.py`) + capas emisivas (`extract-emissive.py`) + pasada de coherencia opcional (`obsidiana.py`). **Jamás dibujados a mano; la vectorización quedó retirada del pipeline** (posterizaba el brillo y mordía contornos — comparación del 25-ago).
- Tamaños de export (dial): naves/NPCs **512** (aguantan el zoom 3× de cámara), estación **1024**, props **256**.
- **Fondos y efectos** → procedurales, generados por `tools/gen-slice-procedural.py` (deterministas, regenerables).
- **UI** → cubierta por el sistema de diseño N (`mex-orbit-docs/05-arte/03-sistema-diseno-ui.md`), no vive en este repo.

## Estado

| Asset | Estado | Archivo | Origen |
|---|---|---|---|
| Fondo del mapa 1-1 | ✅ generado | `world/backgrounds/map-1-1.png` (2048×1260) | procedural |
| Tile de estrellas (parallax) | ✅ generado | `world/backgrounds/starfield-tile.png` (1024, repetible) | procedural |
| Láser cian (jugador) | ✅ generado | `fx/laser-cyan.png` (256×24, blend ADD) | procedural |
| Láser rojo (hostil) | ✅ generado | `fx/laser-red.png` | procedural |
| Explosión (8 frames) | ✅ generado | `fx/explosion-sheet.png` (8×128) | procedural |
| Caja de carga | ✅ **atlas animado** | `exports/cargo-box-anim.png` (48 fotogramas) · fuente `source/renders/Caja.mp4` | vídeo IA |
| Portal | ✅ propuesta | `world/props/portal.svg` | SVG geométrico |
| **Nave Phoenix** | ✅ **vectorizada** (render 2026-08-25) | `ships/phoenix.svg` · fuente `source/renders/Phoenix.jpeg` | pipeline IA |
| **NPC Vex** | ✅ render final | `exports/vex.png` + `vex-emissive.png` · fuente `source/renders/Vex.jpeg` | pipeline IA |
| **NPC Vexor** (forma mayor del Vex) | ✅ render final | `exports/vexor.png` + `vexor-emissive.png` · fuente `source/renders/Vexor.jpeg` | pipeline IA |
| **NPC Skarn** (especie mineral) | ✅ render final | `exports/skarn.png` + `skarn-emissive.png` · fuente `source/renders/Skarn.jpeg` | pipeline IA |
| **NPC Ferox** (cazador óseo, especie clara) | ✅ render final | `exports/ferox.png` + `ferox-emissive.png` · fuente `source/renders/Ferox.jpeg` | pipeline IA |
| **NPC Skarnox** (forma mayor del Skarn) | ✅ **atlas animado** | `exports/skarnox-anim.png` (48 fotogramas) · fuente `source/renders/Skarnox.mp4` · el PNG fijo y su emisiva se conservan de respaldo | vídeo IA |
| **NPC Gravit** (forma menor, hierro macizo) | ✅ render final | `exports/gravit.png` + `gravit-emissive.png` · fuente `source/renders/Gravit.jpeg` | pipeline IA |
| **NPC Mordax** (fauces radiales) | ✅ render final | `exports/mordax.png` + `mordax-emissive.png` · fuente `source/renders/Mordax.jpeg` | pipeline IA |
| **NPC Gravon** (forma mayor del Gravit) | ✅ **atlas animado** | `exports/gravon-anim.png` (49 fotogramas) · fuente `source/renders/Gravon.mp4` · el PNG fijo y su emisiva se conservan de respaldo | vídeo IA |
| **NPC Vorax** (el devorador) | ✅ **atlas animado** | `exports/vorax-anim.png` (45 fotogramas, celda **rectangular** 128×512) · fuente `source/renders/Vorax.mp4` | vídeo IA |
| **Estación base** | ✅ **vectorizada** | `world/props/station.svg` · fuente `source/renders/Base.jpeg` | pipeline IA |
| Placeholders (Phoenix/Vex/estación) | 🗄️ obsoletos | `placeholders/` | sustituidos por los finales; se conservan como referencia |

## Contrato de render (resumen — completo en `prompts/README.md`)

Cenital ortográfica estricta · proa arriba · luz axial desde la cámara · croma verde `#00B140` sin sombra ·
1024×1024 con la pieza al ~70% · escala relativa coherente. Validar la silueta a ~150 px antes de vectorizar.

## Cómo regenerar lo procedural

```bash
py -3 tools/gen-slice-procedural.py
```

Semilla fija (`20260825`): regenerar produce exactamente los mismos bytes. Cambiar la estética = cambiar el
script, no retocar el PNG.

## Pendientes conocidos

- Los tres renders IA (Phoenix, Vex, estación) — requieren pasar los prompts por Gemini/Recraft y correr el post-proceso.
- La pasada de coherencia "Obsidiana" (`tools/design-mexorbit.py`) se aplicará cuando haya ≥2 naves para unificar material.
- Dirección de estilo del mundo (paleta de nebulosas por facción/zona, densidad de decorado): sesión de arte propia; el fondo actual es la base neutral.

## Umbral de la capa emisiva: no todo lo rojo es luz

`extract-emissive.py` se queda con los píxeles donde un canal **domina**, y el umbral es por asset:

| Asset | Canal | Umbral | Por qué |
|---|---|---|---|
| Vex / Vexor | `r` | 18 | Núcleo y venas: rojo puro y saturado sobre quitina oscura |
| Ferox | `r` | **45** | Primer asset **claro**: el hueso marfil tiene algo de rojo. Debe encenderse la mirada y las costuras, no el cuerpo entero |
| Skarnox | `r` | 40 | Mismo problema de cristal que el Skarn, y con más cristal: revisar la capa antes de darla por buena |
| Gravit | `r` | 20 | Metal oscuro sin decorado claro: el rojo del núcleo domina limpio |
| Mordax | `r` | **50** | El peor caso: cuerpo rojo-pardo **y** dientes pálidos. Debe encenderse la mirada, no la dentadura |
| Gravon | `r` | 20 | Hereda el del Gravit; subir si la maquinaria interna expuesta tira a rojiza |
| Vorax | `r` | 25 | Sus vísceras recorren **todo** el cuerpo: es la capa emisiva más grande del catálogo, no un punto |
| Skarn | `r` | **40** | Sus **cristales rosados** también tiran a rojo. Con 12–26 entraban a la capa emisiva y brillaban como si fueran magma; a 40 solo sobrevive el magma de las grietas |
| Estación / caja | `c` | 16 | Decorado cian |
| Portal | `m` | 14 | Vórtice violeta |

Regla: al agregar un asset, **mirar la capa emisiva antes de darla por buena** — un umbral bajo convierte en
lámpara cualquier cosa que tenga un tinte del canal.

## Dónde se ve girar un anillo

```bash
py -3 tools/ring-bands.py exports/gravon.png
```

Da el perfil de **asimetría angular por radio**. Rotar un anillo perfectamente liso mapea píxeles
idénticos sobre sí mismos: el shader funciona y aun así no se ve nada. Solo las bandas con variación
alta (>22) producen lectura.

Se aprendió a la mala con el Gravon: su banda móvil estaba cortada en `r 0.24`, justo antes de donde
empieza su detalle asimétrico (0.24–0.33). El efecto era invisible sin que nada estuviera roto.

**Y la asimetría es necesaria, no suficiente.** El Gravon acabó SIN anillos: su detalle son piezas
soldadas **de un aro a otro**, así que rotar una banda no las hace girar, las cizalla. Esta
herramienta dice dónde hay detalle; si ese detalle *puede* girar —una pieza sobre un anillo, no una
estructura entre anillos— lo dice el ojo.

## Aliens animados: vídeo en bucle -> atlas

```bash
py -3 tools/video-atlas.py source/renders/<Nombre>.mp4 exports/<code>-anim.png 12 384
```

Recorta el croma de cada fotograma, encuadra por la **caja de la unión** (no por el primer
fotograma: el bicho bascula y encuadrar por uno solo le corta un borde en otros) y empaqueta la
rejilla.

**El vídeo debe cumplir el contrato de render más dos cosas:**

1. **Croma verde, no negro.** El primer intento vino sobre negro y fue inservible: un casco de metal
   oscuro sobre fondo negro no tiene frontera que separar.
2. **Bucle**: el último fotograma tiene que casar con el primero. El script mide el salto de la
   costura contra el paso normal, **busca el mejor cierre** y decide.

   *Recortar* al mejor cierre es lo único que funciona, y solo cuando el vídeo se pasa un poco de
   ciclo. Los dos casos reales, medidos:
   - **Skarnox**: 48 fotogramas saltaban 13× el paso normal; recortando a 43, bajó a 2,00. El
     vídeo sobraba material → recortar **arregla**, y el script lo hace solo.
   - **Gravon**: 49 fotogramas saltaban 4× y el mejor recorte no mejoraba nada. Ese vídeo **es**
     un ciclo entero que no cierra (rotación neta de los aros) → recortar solo quitaría
     movimiento real, y el script lo deja entero.

   Por eso el recorte solo se aplica si la mejora es grande (por debajo del 60% del salto original).

   Dos técnicas descartadas, y por qué:
   - *Ping-pong*: cerraría gratis, pero las bandas interiores del Gravon tienen rotación **neta**
     (+60° y −32° por ciclo), así que al revés se mecerían en vez de girar.
   - *Fundido de la cola sobre la cabeza*: solo sirve si sobra material, igual que el recorte, pero
     además **fantasmea** al mezclar dos instantes distintos. Si sobra material, recortar es mejor.

   **Ojo con leer el ratio a secas**: en una animación lenta el paso normal es diminuto (0,34 en el
   Skarnox nuevo), así que una costura pequeña en absoluto sale con un múltiplo alto. Lo que
   importa es el valor sobre 255, no las veces.

| Bucle | fps | Fotogramas | Atlas a 384 px | VRAM |
|---|---|---|---|---|
| 4 s | 12 | 49 | 2688×2688 | 27,6 MB |
| 4 s | 8 | 32 | 2304×2304 | 20,2 MB |

Los diales son la longitud del bucle, los fps y el lado — en ese orden de impacto.

## Pedir un vídeo que loopee de verdad

La caja de carga cerró el bucle mejor que ningún otro asset — costura de **0,9 veces** un paso
normal, o sea que salta menos que avanzar un fotograma — y no fue suerte: **su luz da la vuelta
completa al contorno**. Cuando la animación es un recorrido que vuelve al punto de partida, el ciclo
cierra **por construcción** y no depende de que el modelo acierte con la costura.

Es la diferencia con el Gravon, cuyos aros giran un ángulo que no completa una vuelta: ahí no hay
composición en 2D que lo arregle.

**Al pedir el vídeo, describe un ciclo cerrado** (una luz que recorre un borde entero, un latido que
vuelve a su punto de partida) en vez de "que se anime".

## Celdas rectangulares para bichos alargados

`video-atlas.py` acepta la celda como `384` (cuadrada) o `128x512`. Las celdas **no tienen por qué
ser cuadradas**: `Sprite2D` parte la textura en `hframes` × `vframes` iguales y nada más.

En el Vorax la diferencia es de tres a uno. Mide 125×638 px; cuadrarlo dejaría el **80% de cada
celda vacía** — 27,6 MB de VRAM. Con celda 128×512 son **12,2 MB**.
