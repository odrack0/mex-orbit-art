# Mordax — el que muerde

**Identidad**: quinta especie (*mordax*, mordaz, el que muerde). Su nombre es una **promesa
mecánica**, no un adorno: el Mordax es agresivo pero de **radio corto** — no te caza por medio
sector como el Ferox, muerde lo que se le acerca. Su diseño tiene que avisarlo antes de que
abra fuego.

**La idea**: el bicho **es** una boca. Visto desde arriba —que es el único ángulo que existe en
este juego— una mandíbula radial se lee de inmediato y no se parece a nada más del bestiario.
Donde el Ferox tiene hojas y el Skarn es un peñasco, el Mordax es unas **fauces apuntándote**.

**Regla de legibilidad**: quitina otra vez, como el Vex, pero de otro color para que no se
confunda con esa familia: **rojo-pardo oscuro** en vez de morado-negro. Y el contraste lo pone
la boca: anillo de **dientes pálidos** en el centro, el único elemento claro del cuerpo. A 150
px se distingue por ese ojo blanco dentado en medio de una masa oscura.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a hostile alien predator seen from directly above,
> front pointing straight up, perfectly centered. The creature is dominated by a huge circular
> radial maw at its center, ringed with rows of pale ivory fangs pointing inward, like a
> lamprey mouth opened toward the viewer. Around the maw, a thick armored carapace of dark
> red-brown chitin plates with six short muscular limbs tucked underneath and a pair of
> sensory barbs at the front. Glowing crimson-red eyes clustered above the mouth and thin red
> emissive seams between the plates. Hungry, aggressive, close-range brawler — industrial dark
> sci-fi, high detail, video game enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: entre el Skarn y el Ferox — ancho y achaparrado, más disco que flecha.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Mordax.jpeg source/renders/mordax-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
```

**Ojo con el umbral emisivo**: la lección del Skarn y del Ferox se repite aquí. Los **dientes
pálidos** tienen algo de rojo y el cuerpo es rojo-pardo, así que un umbral bajo encendería el
bicho entero. Debe encenderse la **mirada y las costuras**, no la dentadura ni el caparazón —
se mira la capa emisiva antes de darla por buena.
