# Skarn — el alien mineral

**Identidad**: **especie nueva**, no un Vex crecido. *Skarn* es un término geológico real (roca dura de contacto):
un alien **mineral**, no insectoide. Es el segundo bicho que el jugador aprende a distinguir, y su trabajo de
diseño es enseñar que el bestiario tiene **familias**, no una sola criatura en varios tamaños. Tier `BASE`.

**Regla de legibilidad**: contra el Vex debe ganar la lectura de **material** — quitina orgánica frente a **roca y
cristal**. Silueta compacta y rocosa, casi sin apéndices; el Vex es angular y con garras, el Skarn es un peñasco.
El acento sigue siendo **rojo hostil** (la familia entera lo comparte), pero aquí es **magma en las grietas**, no
un núcleo biológico: brillo cálido rojo-naranja repartido por las fisuras en vez de concentrado en un ojo.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a hostile mineral alien creature, front pointing straight up, perfectly
> centered. Chunky asteroid-like body made of fractured dark basalt rock and embedded crystal shards, thick
> irregular stone plates, a blunt armored front with no limbs, heavy and compact silhouette. Deep charcoal-grey
> and black rock with glowing red-orange molten magma light seeping from the cracks and fissures between the
> plates, and a few dull crimson crystal spikes on the back. Ancient, heavy, geological — not insectoid, not
> mechanical — industrial dark sci-fi, high detail, video game enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: el más grande de los tres bichos del 1-1 — macizo, más ancho que largo.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Skarn.jpeg source/renders/skarn-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
py -3 tools/extract-emissive.py     # el magma de las grietas -> skarn-emissive.png
```

Ojo con el croma: la roca oscura sobre verde recorta bien, pero los **cristales translúcidos** pueden chupar
verde en los bordes. Si pasa, subir el umbral del chroma-key antes de dar por bueno el recorte.

En el juego su pulso es **lento y de valles largos** (la roca no palpita como un bicho): magma que respira.
