# Vex — alien base de zona baja

**Identidad**: el alien más humilde del bestiario (especie *vex*, tier BASE). Biomecánico angular, hostil pero
menor: debe leerse como presa fácil junto a un Vexor o cualquier Elite. Familia de nombres: latín oscuro.

**Regla de legibilidad**: a un vistazo debe distinguirse de cualquier nave de jugador (silueta orgánica-angular
vs. fuselajes limpios) y su acento de color es **rojo hostil**, nunca cian.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a small hostile alien creature-ship, front pointing straight up, perfectly
> centered. Angular biomechanical carapace like a fusion of insect chitin and dark alien metal, asymmetric plating,
> two short forward claw-like protrusions, segmented abdomen tapering to the rear. Very dark purple-black chitin
> with a single glowing crimson-red core near the center and thin red emissive seams along the plates.
> Menacing but small and expendable — industrial dark sci-fi, high detail, video game enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: comparable a la Phoenix (es el enemigo del primer día).

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/vex.png source/renders/vex-cut.png
py -3 tools/vectorize-ship.py source/renders/vex-cut.png npcs/vex.svg 16 3 0.9 6 10 0.30
```

La pasada cromática va encendida: el núcleo y las vetas rojas son decorado de color sobre quitina oscura.
Nota: `sat_min` 0.30 porque el rojo sobre negro tiende a saturación media.
