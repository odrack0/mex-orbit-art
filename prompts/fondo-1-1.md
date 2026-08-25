# Fondo principal del mapa 1-1 — la capa `isMain`

**Identidad**: el lienzo profundo del sector natal. Espacio oscuro (#07070F de base) con nebulosas frías
**cian/turquesa** (la luz del 1-1 original era `0xA3FFFF`), sutiles vetas violetas y campos de estrellas.
Debe ser **oscuro y despejado en general** — encima vuelan naves y HUD; la nebulosa decora, no invade.

**OJO — este render es distinto a los demás**: es una imagen a sangre completa, **SIN croma verde** y sin
objeto central. Se usa tal cual (recorte a 2048×1280 si el generador da otro aspecto).

## Prompt (pegar en Gemini / Recraft)

> Deep space background for a top-down space game, seamless dark starfield scene, 16:10 wide.
> Very dark navy-black space (#07070F base) with soft wispy cyan-turquoise nebula clouds concentrated
> toward the edges, faint violet undertones, scattered small stars of varying brightness, two or three
> subtle distant star clusters. No planets, no ships, no lens flare, no bright center — mostly dark and
> calm, the nebula must stay subtle so gameplay reads on top. High detail, no vignette, no watermark,
> 2048x1280.

## Post-proceso

Guardar como `source/renders/fondo-1-1.png` (sin chroma-key). Se recorta/ajusta a 2048×1280 y entra como
`exports/map-1-1.png`, reemplazando al procedural actual en la capa `isMain` (pFactor 10).
