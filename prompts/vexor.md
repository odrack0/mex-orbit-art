# Vexor — el Vex evolucionado

**Identidad**: la misma especie que el Vex (*vex*, latín *vexare*, molestar), pero su **forma mayor** — la regla
de la taxonomía: sufijo **-or** = forma mayor. El parentesco debe leerse de un vistazo: si el jugador ve un Vexor
junto a un Vex, tiene que entender que es "el mismo bicho, crecido", no otra especie. Sigue siendo tier `BASE`
(las escaleras Elite/Titan son otra cosa).

**Regla de legibilidad**: el salto de tier se cuenta con **masa y silueta**, no cambiando de color — el acento es
**rojo hostil**, igual que el Vex, nunca cian. Lo que crece: el tamaño, el número de placas, y pasa de **un núcleo
a dos** con las vetas encendidas más largas y ramificadas.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a large hostile alien creature-ship, front pointing straight up, perfectly
> centered. Same biomechanical species as a smaller insectoid alien but grown and armored: heavy angular carapace
> of overlapping chitin plates, four forward claw-like protrusions instead of two, a broader thorax and a thick
> segmented abdomen with bony ridges. Very dark purple-black chitin with TWO glowing crimson-red cores along the
> centerline and long branching red emissive veins spreading across the plates. Bulky, dangerous, clearly a bigger
> evolved form of a lesser creature — industrial dark sci-fi, high detail, video game enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: notablemente mayor que la Phoenix y que el Vex — debe ocupar más lienzo y leerse pesado.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Vexor.jpeg source/renders/vexor-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
py -3 tools/extract-emissive.py     # los dos núcleos y las vetas -> vexor-emissive.png
```

La capa emisiva es la que da la vida: en el juego late en intensidad de blend aditivo, más rápido que el Vex
(dos corazones, no uno).
