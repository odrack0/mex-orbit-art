# Caja de carga — el botín que sueltan los aliens

**Identidad**: contenedor pequeño y legible a ~40 px en juego. Debe *llamar* al jugador: metal oscuro
con emisivo cian que la haga brillar sobre el fondo estelar. Reemplaza al SVG geométrico provisional.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a small sci-fi cargo container, perfectly centered.
> Compact rectangular armored crate with reinforced ribs, dark gunmetal and obsidian plating,
> one bright glowing turquoise-cyan emissive strip across the center and a small cyan status light.
> Slightly worn industrial metal, high detail, video game loot asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: pequeña — en juego rinde a ~40 px; el objeto ocupa ~60% del lienzo.

## Post-proceso (pipeline PNG)

```bash
py -3 tools/chroma-key.py source/renders/caja.png source/renders/caja-cut.png
# export directo 256 + capa emisiva cian
py -3 tools/extract-emissive.py source/renders/caja-cut.png exports/cargo-box-emissive.png c 256 16
```

(y agregar la pieza a `tools/export-png.py` con lado 256.)
