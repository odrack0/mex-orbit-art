# Gravon — la forma mayor del Gravit

**Identidad**: cierra la pareja que el Gravit dejó abierta. Sufijo **-on** = forma mayor, igual
que `-or` y `-ox`; con esto el jugador tiene la regla completa en las manos: **-it/-in** para lo
menor, **-on/-or/-ox** para lo mayor. Es la tercera pareja del mapa (Vex→Vexor, Skarn→Skarnox,
Gravit→**Gravon**), y a la tercera ya nadie necesita que se lo expliquen.

**Regla de legibilidad**: mismo material y mismo lenguaje que el Gravit —**hierro meteórico
pulido**, anillos concéntricos, núcleo hundido— pero con la masa multiplicada. Lo que crece: el
tamaño, el número de anillos, y pasa de **un núcleo a tres** alineados en el eje. El anillo
exterior aparece **fracturado**, dejando ver maquinaria interna: es tan denso que se está
partiendo por su propio peso.

Nada de cambiar de paleta: el salto se cuenta con masa, como en las otras dos parejas.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a large hostile alien machine-creature, front pointing
> straight up, perfectly centered. Massive dense body of dark polished meteoric iron built as
> many concentric ring segments, far heavier and more layered than a smaller version of itself.
> THREE glowing crimson-red cores recessed along the vertical axis instead of one. The outermost
> ring is cracked open in places, exposing dark internal machinery underneath — so dense it is
> splitting under its own weight. Six blunt anchor spikes around the rim. Smooth reflective
> gunmetal and near-black armor with thin red light bleeding from every seam. Industrial dark
> sci-fi, high detail, video game enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: grande y compacto — ocupa mucho lienzo pero sigue siendo un disco macizo, no una
silueta con apéndices.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Gravon.jpeg source/renders/gravon-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
```

El Gravit salió limpio con umbral emisivo 20 (metal oscuro sin decorado claro, el rojo del
núcleo domina solo). El Gravon hereda el mismo valor; si la maquinaria interna expuesta tira a
rojiza, se sube.
