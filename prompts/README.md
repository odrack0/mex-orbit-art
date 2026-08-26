# Prompts de render — assets del slice E2

Prompts listos para el generador de imágenes (Gemini / Recraft). El **contrato de render** aplica a todos —
violarlo invalida el render para el pipeline:

1. **Ortográfica cenital estricta** (top-down puro; la IA deriva a 3/4 — rechazar esos intentos).
2. **Proa hacia arriba**, centrada.
3. **Luz axial desde la cámara** (sin dirección lateral: con rotación libre en Godot un reflejo lateral "gira" y canta).
4. **Fondo verde croma plano** (`#00B140`), sin sombra proyectada al suelo, sin viñeta.
5. **1024×1024**, la nave ocupando ~70% del lienzo.
6. Escala relativa coherente entre naves (la Phoenix es pequeña; anotada en cada prompt).

Al recibir el render: validar la silueta a tamaño de juego (~150 px) antes de exportar.

## Post-proceso (pipeline PNG — dictamen 2026-08-25)

**El master canónico es el render recortado** (`source/renders/*-cut.png`); los exports del juego son
downscale Lanczos directo — cero pérdida. La vectorización quedó retirada del pipeline (posterizaba el
brillo y mordía los contornos); `tools/vectorize-ship.py` se conserva solo como herramienta de estilo.

```bash
py -3 tools/chroma-key.py source/renders/<Asset>.jpeg source/renders/<asset>-cut.png
py -3 tools/export-png.py            # regenera todos los exports (naves/NPCs 512, estación 1024, props 256)
```

Extras del pipeline:
- `tools/extract-emissive.py` — capa emisiva (núcleo/venas/reactor) para glow animado en el juego.
- `tools/obsidiana.py` — pasada de coherencia del catálogo (casco obsidiana, especulares oro, decorado turquesa), con dial de fuerza.

| Asset | Archivo de prompt | Export |
|---|---|---|
| Nave inicial Phoenix | [`phoenix.md`](phoenix.md) | `exports/phoenix.png` (512) |
| Alien Vex | [`vex.md`](vex.md) | `exports/vex.png` + `vex-emissive.png` (512) |
| Alien Vexor (forma mayor del Vex) | [`vexor.md`](vexor.md) | `exports/vexor.png` + `vexor-emissive.png` (512) |
| Alien Skarn (especie mineral) | [`skarn.md`](skarn.md) | `exports/skarn.png` + `skarn-emissive.png` (512) |
| Alien Skarnox (forma mayor del Skarn) | [`skarnox.md`](skarnox.md) | `exports/skarnox.png` + `skarnox-emissive.png` (512) — **falta render** |
| Alien Ferox (cazador óseo) | [`ferox.md`](ferox.md) | `exports/ferox.png` + `ferox-emissive.png` (512) — **falta render** |
| Estación base | [`station.md`](station.md) | `exports/station.png` + `station-emissive.png` (1024) |
| Caja de carga | [`caja.md`](caja.md) | `exports/cargo-box.png` + `cargo-box-emissive.png` (256) |
| Portal | [`portal.md`](portal.md) | `exports/portal.png` + `portal-emissive.png` (256) |
