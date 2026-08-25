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

**Escala**: ~2× el diámetro de la nave más grande; en juego rinde a ~300 px.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/station.png source/renders/station-cut.png
py -3 tools/vectorize-ship.py source/renders/station-cut.png world/props/station.svg 16 3 1.05 8 7 0.30
```

Parámetros aligerados (mucha superficie): `epsilon` 1.05, `area_min` 8, 7 bandas de croma — la combinación
recomendada del pipeline para piezas grandes con decorado de color.
