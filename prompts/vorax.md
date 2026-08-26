# Vorax — el devorador

**Identidad**: sexta especie (*vorax*, voraz). Es el primer bicho del bestiario cuyo nombre
describe una **conducta** y no una forma: el Vorax **huye cuando lo tienes casi muerto**. Te
cuesta una fortuna bajarlo y, si te descuidas, se te escapa con el escudo regenerándose. Esa
frustración es el personaje.

**Contra el Mordax**: los dos son criaturas de boca, así que tienen que separarse a la primera
ojeada. El Mordax es un **disco** con una mandíbula radial en el centro — compacto, achaparrado.
El Vorax es **alargado**: una garganta con cuerpo, segmentada, más sanguijuela que cangrejo. Uno
muerde; el otro **traga**.

**Regla de legibilidad**: sexta lectura de material. Ya hay quitina (Vex), metal (Gravit), roca
(Skarn), hueso (Ferox) y caparazón con dentadura (Mordax). El Vorax es **carne**: piel oscura
lustrosa y semitraslúcida por la que **se ven las vísceras encendidas** — se aprecia lo que
acaba de tragarse. El acento rojo hostil aquí no es un núcleo ni una veta: son sus tripas.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a hostile alien predator seen from directly above, front
> pointing straight up, perfectly centered. Long segmented worm-like body, widest at the front
> and tapering toward the back, built from overlapping rings of dark glossy semi-translucent
> flesh. At the front, a wide round gullet opening ringed with soft inward-curving barbs — a
> throat, not a jaw. Through the translucent skin, glowing crimson-red innards and a pulsing
> digestive tract are visible along the whole length of the body. Slick, wet, organic and
> repulsive — a devourer — industrial dark sci-fi, high detail, video game enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: largo, no ancho — el más alargado del bestiario después del Ferox, pero con mucho
más cuerpo.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Vorax.jpeg source/renders/vorax-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
```

**Ojo con la piel semitraslúcida**: es el primer asset del catálogo que no es opaco, y el
chroma-key puede colarse por las zonas finas y comerse el cuerpo. Si aparecen agujeros, se baja
el umbral de verdor antes de dar por bueno el recorte.

Su capa emisiva es **más grande que ninguna** — las vísceras recorren todo el cuerpo, no son un
punto. Umbral de partida 25; si el cuerpo entero se enciende, subir.
