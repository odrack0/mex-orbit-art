# Portal — el salto entre mapas

**Identidad**: anillo de metal oscuro con un vórtice violeta→cian; masivo pero elegante. En juego rinde
a ~140 px. Reemplaza al SVG geométrico provisional. Acento **violeta** (los portales son violeta en la
identidad N; el cian es de la facción/estación).

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a sci-fi jump gate ring, perfectly centered.
> Massive dark gunmetal ring with armored segments and four small node lights, containing a swirling
> energy vortex portal — deep violet spiraling into bright cyan-white at the center, with thin luminous
> spiral arms. Industrial sci-fi, high detail, video game asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: el objeto ocupa ~80% del lienzo.

## Post-proceso (pipeline PNG)

```bash
py -3 tools/chroma-key.py source/renders/portal.png source/renders/portal-cut.png
# el vano central del anillo es fondo legitimo: HOLE_MAX se queda en el default
# export directo 256 + vortice como capa emisiva (para animarle rotacion/pulso en el juego)
py -3 tools/extract-emissive.py source/renders/portal-cut.png exports/portal-emissive.png c 256 14
```

(y agregar la pieza a `tools/export-png.py` con lado 256.)
