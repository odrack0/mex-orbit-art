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
py -3 tools/chroma-key.py source/renders/Base.jpeg source/renders/station-cut.png
py -3 tools/vectorize-ship.py source/renders/station-cut.png world/props/station.svg 10 2 2.2 20 5 0.32
```

Parámetros muy aligerados (la pieza más grande del slice): calibrados 2026-08-25. Dos lecciones de esta pieza,
ya integradas en `chroma-key.py`: (1) los huecos grandes NO se rellenan — el vano entre el anillo de atraque y
la plataforma es fondo legítimo (5º argumento `HOLE_MAX`, default 2500 px); (2) el verdor se mide contra
`max(r,b)`, no la media — si no, el núcleo cian brillante se recorta como croma.
