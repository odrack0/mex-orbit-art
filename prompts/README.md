# Prompts de render — assets del slice E2

Prompts listos para el generador de imágenes (Gemini / Recraft). El **contrato de render** aplica a todos —
violarlo invalida el render para el pipeline:

1. **Ortográfica cenital estricta** (top-down puro; la IA deriva a 3/4 — rechazar esos intentos).
2. **Proa hacia arriba**, centrada.
3. **Luz axial desde la cámara** (sin dirección lateral: con rotación libre en Godot un reflejo lateral "gira" y canta).
4. **Fondo verde croma plano** (`#00B140`), sin sombra proyectada al suelo, sin viñeta.
5. **1024×1024**, la nave ocupando ~70% del lienzo.
6. Escala relativa coherente entre naves (la Phoenix es pequeña; anotada en cada prompt).

Al recibir el render: validar la silueta a tamaño de juego (~150 px) **antes** de vectorizar.

```bash
py -3 tools/chroma-key.py source/renders/<asset>.png source/renders/<asset>-cut.png
py -3 tools/vectorize-ship.py source/renders/<asset>-cut.png ships/<asset>.svg 16 3 0.9 6 10 0.34
```

(Parámetros base del README del pipeline; la pasada cromática se apaga con `0` en cascos de metal neutro.)

| Asset | Archivo de prompt | Destino |
|---|---|---|
| Nave inicial Phoenix | [`phoenix.md`](phoenix.md) | `ships/phoenix.svg` |
| Alien Vex | [`vex.md`](vex.md) | `npcs/vex.svg` |
| Estación base | [`station.md`](station.md) | `world/props/station.svg` |
