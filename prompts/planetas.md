# Los tres planetas del 1-1 — capas 2, 5 y 6 del paralaje

El mapa original coloca tres planetas a distintas profundidades. Tres renders separados, **con croma verde**,
mismo contrato de siempre (luz axial, sin sombra de suelo, 1024×1024, el planeta ocupando ~80%).

## Planeta A — lejano (pFactor 9, se ve pequeño y frío)

> A single planet seen from space, perfectly centered, fully round. Frozen ice planet with pale
> cyan-blue surface, thin white cloud bands, subtle atmospheric rim glow on all edges (light from
> directly above the camera, no side terminator). High detail, video game background asset render.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

→ `source/renders/planeta-a.png` → export 512 → `assets/world/layers/planet-a.png`

## Planeta B — medio (pFactor 5, gaseoso violeta)

> A single gas giant planet seen from space, perfectly centered, fully round. Deep violet and indigo
> swirling cloud bands with faint turquoise storm accents, subtle atmospheric rim glow on all edges
> (light from directly above the camera, no side terminator). High detail, video game background asset
> render. Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

→ `source/renders/planeta-b.png` → export 512 → `assets/world/layers/planet-b.png`

## Planeta C — cercano (pFactor 6, rocoso oscuro)

> A single rocky planet seen from space, perfectly centered, fully round. Dark charcoal rocky surface
> with faint orange-ember crack lines and thin gray atmosphere, subtle rim glow on all edges (light
> from directly above the camera, no side terminator). High detail, video game background asset render.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

→ `source/renders/planeta-c.png` → export 512 → `assets/world/layers/planet-c.png`

## Post-proceso (los tres)

```bash
py -3 tools/chroma-key.py source/renders/planeta-a.png source/renders/planeta-a-cut.png
# (idem b y c; luego se agregan a export-png.py con lado 512)
```

Nota: la luz axial importa aquí también — un terminador lateral "cantaría" contra el resto del arte.
