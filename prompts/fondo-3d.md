# El fondo del cliente 3D (F3) — nebulosas por capas, telón y planetas

**Contexto**: desde la Fase 3 del cliente 3D (`plan-cliente-3d.md`), el fondo ya no es un paralaje
2D por fórmula: son **capas de quads a profundidad real** (−3500 + 550 por capa, con jitter
vertical por tile) bajo un **cielo procedural con estrellas y twinkle** que pone el shader. El
código está listo y probado; lo que enseña costuras es el ARTE, que era de la era del paralaje 2D.
Este pedido lo cierra.

**El diagnóstico, para que el porqué no se pierda**:

1. Las nebulosas actuales (`nebula-mid/near`, `dust-far`) son imágenes **a sangre completa**: en
   mosaico, sus bordes rectos cantan. En el original cada tile era una NUBE AISLADA con el borde
   desvanecido a transparente — con eso los huecos, giros y jitter del mosaico se leen como cielo
   natural, no como azulejos.
2. El telón (`map-1-1.png`) trae **estrellas cocidas**: a su cota (−4200) se estiran y se ven como
   manchones borrosos, y además DUPLICAN las estrellas nítidas del cielo procedural. El telón nuevo
   va SIN estrellas: solo el lavado de nebulosa que da identidad al sector.

## 1. Atlas de nubes por capa — el pedido principal

**Tres atlas** (uno por capa), cada uno **2048×2048 = rejilla 2×2 con 4 variantes** de nube.
Requisitos duros de cada celda (1024×1024):

- La nube **aislada y centrada**, con el borde desvanecido a **alfa 0 total** en los últimos
  ~120 px de cada lado de la celda. Ni un píxel opaco tocando el borde: es lo que hace invisible
  el mosaico.
- Fondo de la celda 100% transparente (PNG con alfa), sin viñeta, sin marca.
- Las 4 variantes claramente distintas en silueta (el código las sortea por tile y las gira en
  pasos de 90°).

| Archivo | Capa (cota) | Identidad |
|---|---|---|
| `nebula-far-atlas.png` | profunda (−3500) | Polvo tenue y frío, azul-gris muy oscuro, apenas presencia — es lo que se ve DETRÁS de todo |
| `nebula-mid-atlas.png` | media (−2950) | Nebulosa cian/turquesa (la familia del 1-1, luz `0xA3FFFF`), cuerpo suave con algo de veta |
| `nebula-near-atlas.png` | cercana (−2400) | Nube más densa y con detalle interno, cian con vetas violetas (`#A78BFA` de la paleta), la que más se desplaza al volar |

### Prompt base (pegar en Gemini / Recraft, uno por capa ajustando la identidad)

> A 2x2 sprite sheet of 4 different wispy space nebula clouds, each cloud isolated and centered in
> its own 1024x1024 quadrant on a fully TRANSPARENT background, edges fading smoothly to complete
> transparency well before the cell borders (at least 120px of fully transparent margin per cell).
> Soft volumetric cyan-turquoise gas clouds with faint violet undertones, dark space game art
> style, subtle and calm (gameplay must read on top), no stars, no planets, no watermark, PNG with
> alpha, 2048x2048.

(Para `far`: "very faint dark blue-grey dust wisps, extremely subtle". Para `near`: "denser cloud
with more internal detail and violet streaks".)

### Post-proceso y enchufe

1. Guardar crudos en `source/renders/nebula-<capa>-atlas.png`; verificar el alfa del borde
   (`py tools/find-anchors.py` no aplica — basta un vistazo al canal alfa, o
   `python -c "..."` sumando alfa en el marco de 120 px: debe dar 0).
2. Exportar a `mex-orbit-client/assets/world/layers/` con el mismo nombre.
3. En `data/maps/1-1.json`, cada entrada de `tiles_far`/`tiles_near` pasa a:
   ```json
   { "tex": "res://assets/world/layers/nebula-mid-atlas.png",
     "p_factor": 6.0, "scale": 1.6, "alpha": 0.85, "celdas": 4, "grid": 2 }
   ```
   El cliente ya entiende `celdas`/`grid` (F3): sortea la variante por tile. Cero código.

## 2. El telón v2 — `map-1-1.png` sin estrellas

Rehacer el fondo principal del 1-1 (2048×1280) **quitando las estrellas del prompt**: solo el
lavado oscuro de nebulosa que da identidad al sector (base `#07070F`, nubes cian hacia los bordes,
vetas violetas sutiles). Las estrellas las pone el cielo procedural, nítidas e infinitas; las
cocidas se estiran a manchones en la cota del telón.

> Deep space background wash for a game backdrop, 16:10. Very dark navy-black (#07070F) with soft
> wispy cyan-turquoise nebula concentrated toward the edges and faint violet undertones. NO stars
> at all, no planets, no bright spots, no vignette, no watermark — a pure dark nebula wash,
> gameplay and a procedural starfield render on top. 2048x1280.

Entra como `exports/map-1-1.png` reemplazando al actual (mismo enchufe de siempre).

## 3. Opcional (pulido, no bloquea el cierre de F3)

- **`planet-b` a 1024×1024**: es el planeta más cercano (p_factor 5) y el 512 se queda corto al
  hacer zoom. Mismo prompt de `planetas.md`, doble resolución.
- Los otros planetas y el sol aguantan a 512.

## Aceptación (bestiario, `-Calidad alta`)

- Ninguna costura recta visible en el cielo de las capturas.
- El mosaico no "canta" patrón (4 variantes + giros lo matan).
- Las estrellas se ven SOLO nítidas (las del cielo); cero manchones borrosos.
