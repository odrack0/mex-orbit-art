# Phoenix — nave inicial (STARTER)

**Identidad**: la primera nave de todo piloto. Pequeña, ágil, honesta — un dardo compacto, no un caza de guerra.
Debe leerse frágil junto a cualquier otra nave del catálogo. Familia de nombres: constelaciones.

**Referencia de rol**: heredera espiritual de la nave inicial clásica (ligera, 1 láser, 1 generador).

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a small starter spaceship, nose pointing straight up, perfectly centered.
> Compact dart-shaped hull with a narrow fuselage, two short swept wings, a small cockpit canopy near the front,
> and twin small engine nozzles at the rear with faint cyan glow. Dark gunmetal and obsidian armor plating with
> subtle panel lines, minimal turquoise-cyan emissive accents along the wing edges. Slightly worn, utilitarian,
> believable spacecraft — industrial sci-fi, high detail, PBR materials, video game asset render.
> Lighting strictly from directly above the ship (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: la más pequeña del catálogo — casco esbelto, sin masa excesiva.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/phoenix.png source/renders/phoenix-cut.png
py -3 tools/vectorize-ship.py source/renders/phoenix-cut.png ships/phoenix.svg 16 3 0.9 6 10 0.34
```

Validar silueta a ~150 px. Si el casco es metal neutro sin decorado de color, apagar la pasada cromática (`... 0.9 6 0`).
