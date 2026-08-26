# Skarnox — la forma mayor del Skarn

**Identidad**: misma especie mineral que el Skarn (*skarn*, roca dura), en su **forma mayor** — sufijo **-ox**.
Con este bicho el jugador aprende que la regla de nombres **es una regla**: ya vio Vex→Vexor, ahora ve
Skarn→Skarnox y entiende la morfología sola. Tier `BASE`, y el **techo del 1-1**.

**Regla de legibilidad**: igual que con el Vexor, el salto se cuenta con **masa**, no cambiando de paleta. Lo que
crece: el tamaño, la profundidad de las fisuras y la cantidad de magma. Donde el Skarn tiene grietas, el Skarnox
tiene **fracturas abiertas que dejan ver el núcleo fundido**; sus cristales pasan de brotes sueltos a una
**corona** en la espalda.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a huge hostile mineral alien creature, front pointing straight up,
> perfectly centered. Massive fractured boulder body of dark basalt rock, thicker and more broken than a smaller
> rock creature: deep open fissures across the shell exposing a bright molten orange-white core underneath,
> heavy overlapping stone plates with jagged edges. A crown of large dull crimson crystal spikes clustered on the
> upper back and along the rim. Glowing red-orange magma light pouring from the wide cracks, brightest at the
> center. Ancient, colossal, geological — not insectoid, not mechanical — industrial dark sci-fi, high detail,
> video game enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: el más grande del bestiario del 1-1 — debe leerse pesado y lento.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Skarnox.jpeg source/renders/skarnox-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
```

**Ojo con el umbral emisivo**: los cristales rosados del Skarn entraban a la capa emisiva y brillaban como si
fueran magma — por eso su umbral está en 40 y no en 18. El Skarnox lleva más cristal todavía, así que hay que
**mirar su capa emisiva antes de darla por buena** y subir el umbral si los cristales se cuelan.
