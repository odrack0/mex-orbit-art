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

- **Se generan sobre NEGRO PURO, no con transparencia.** Los generadores no dan alfa gradual
  fiable para gas (recortes duros, halos), y el margen es justo la instrucción que ignoran. El
  alfa lo deriva `tools/nebula-alpha.py` de la luminancia — para una nube que emite luz es el alfa
  físicamente correcto — y ese mismo tool **impone el margen de 120 px por código**, celda a
  celda, garantizado. Misma filosofía que el croma de las naves: la IA rinde donde es buena y el
  post asegura el contrato.
- La nube **aislada y centrada** en su celda, dejando aire hacia los bordes (el tool funde lo que
  invada, pero una nube pegada al borde queda recortada: mejor centrada de origen).
- Las 4 variantes claramente distintas en silueta (el código las sortea por tile y las gira en
  pasos de 90°).

| Archivo | Capa (cota) | Identidad |
|---|---|---|
| `nebula-far-atlas.png` | profunda (−3500) | Polvo tenue y frío, azul-gris muy oscuro, apenas presencia — es lo que se ve DETRÁS de todo |
| `nebula-mid-atlas.png` | media (−2950) | Nebulosa cian/turquesa (la familia del 1-1, luz `0xA3FFFF`), cuerpo suave con algo de veta |
| `nebula-near-atlas.png` | cercana (−2400) | Nube más densa y con detalle interno, cian con vetas violetas (`#A78BFA` de la paleta), la que más se desplaza al volar |

### Los tres prompts, listos (pegar en Gemini / Recraft) — sobre NEGRO

**`nebula-far-atlas.png`:**

> A 2x2 grid of 4 different faint space dust wisps on a PURE BLACK background, each wisp isolated
> and centered in its own 1024x1024 quadrant with generous black space around it, never touching
> the quadrant edges. Extremely subtle dark blue-grey gas wisps, barely-there volumetric dust,
> very low contrast — this is the deepest background layer of a space game and must almost
> disappear. Each of the 4 wisps clearly different in silhouette. No stars, no planets, no
> watermark, no vignette, no grid lines. 2048x2048.

**`nebula-mid-atlas.png`:**

> A 2x2 grid of 4 different wispy space nebula clouds on a PURE BLACK background, each cloud
> isolated and centered in its own 1024x1024 quadrant with generous black space around it, never
> touching the quadrant edges. Soft volumetric cyan-turquoise gas clouds with faint violet
> undertones, dark space game art style, subtle and calm — gameplay must read on top. Each of the
> 4 clouds clearly different in silhouette. No stars, no planets, no watermark, no vignette, no
> grid lines. 2048x2048.

**`nebula-near-atlas.png`:**

> A 2x2 grid of 4 different dense space nebula clouds on a PURE BLACK background, each cloud
> isolated and centered in its own 1024x1024 quadrant with generous black space around it, never
> touching the quadrant edges. Denser volumetric cyan-turquoise clouds with rich internal detail
> and distinct violet streaks (#A78BFA accents), the closest and most visible nebula layer of a
> dark space game, still dark enough for gameplay to read on top. Each of the 4 clouds clearly
> different in silhouette. No stars, no planets, no watermark, no vignette, no grid lines.
> 2048x2048.

### Post-proceso y enchufe

1. Guardar el crudo (sobre negro) en `source/renders/nebula-<capa>-atlas.png`.
2. Derivar el alfa e imponer el margen:
   ```bash
   py tools/nebula-alpha.py source/renders/nebula-mid-atlas.png \
       ../mex-orbit-client/assets/world/layers/nebula-mid-atlas.png
   ```
   El tool imprime la cobertura por celda y avisa de variantes VACIAS (<2%, regenerar) o que
   INVADEN el margen (>60%, regenerar más centrada). El margen de 120 px queda garantizado por
   código — no depende de que la IA lo respete.
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

**`planet-b` a 1024**: es el planeta más cercano (p_factor 5) y el 512 se queda corto al hacer
zoom. Misma identidad de `planetas.md`, fuente al doble para exportar 1024 limpio:

> A single gas giant planet seen from space, perfectly centered, fully round. Deep violet and
> indigo swirling cloud bands with faint turquoise storm accents, subtle atmospheric rim glow on
> all edges (light from directly above the camera, no side terminator). Very high detail, video
> game background asset render. Flat solid chroma green background (#00B140), no vignette, no
> other objects, 2048x2048.

→ `source/renders/planeta-b-v2.png` → `py -3 tools/chroma-key.py` → export **1024** →
`assets/world/layers/planet-b.png` (mismo nombre: reemplaza, cero cambios de JSON).

Los otros planetas y el sol aguantan a 512.

## Aceptación (bestiario, `-Calidad alta`)

- Ninguna costura recta visible en el cielo de las capturas.
- El mosaico no "canta" patrón (4 variantes + giros lo matan).
- Las estrellas se ven SOLO nítidas (las del cielo); cero manchones borrosos.
