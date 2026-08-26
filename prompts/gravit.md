# Gravit — la forma MENOR

**Identidad**: cuarta especie (*gravis*, pesado). Y aquí está su trabajo real de diseño: es el
primer bicho con sufijo **-it**, que en la taxonomía significa **forma menor**. Hasta ahora el
jugador solo ha visto los sufijos mayores (Vex→**Vexor**, Skarn→**Skarnox**); con el Gravit
aprende la otra mitad de la regla. Su forma mayor —el **Gravon**— existe en la taxonomía y
llegará después: el nombre ya promete que hay algo más grande ahí fuera.

**La paradoja que tiene que leerse**: es *pequeño* y aun así *pesadísimo*. No es frágil, es
**denso** — un pedazo de materia compactada. Contra el Skarn (piedra porosa y agrietada) debe
leerse como **metal meteórico macizo**: pulido, sin fisuras, compacto hasta lo absurdo.

**Regla de legibilidad**: cuarta familia de material. Ya hay quitina (Vex), roca (Skarn) y
hueso (Ferox); el Gravit es **hierro oscuro**. Superficie lisa y reflectante en vez de
texturada, con anillos concéntricos alrededor de un núcleo hundido. El acento sigue siendo
**rojo hostil**, aquí concentrado en ese único núcleo y en las ranuras entre anillos.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a small hostile alien machine-creature, front pointing
> straight up, perfectly centered. Compact dense body of dark polished meteoric iron, smooth
> reflective armor with no cracks, built as concentric ring segments around a sunken central
> core, with four short blunt anchor spikes at the cardinal points. Extremely heavy and
> massive despite its small size — a chunk of compressed matter. Deep gunmetal and near-black
> metal with a single glowing crimson-red core recessed at the center and thin red light
> bleeding from the seams between the rings. Industrial dark sci-fi, high detail, video game
> enemy asset render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: el más pequeño del bestiario, por debajo del Vex — pero macizo, nada de siluetas
finas ni apéndices largos.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Gravit.jpeg source/renders/gravit-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
```

**Ojo con el metal pulido**: es reflectante, así que puede recoger verde del croma en los
bordes redondeados. Si pasa, se ajusta el umbral antes de dar por bueno el recorte.
