# Ferox — el cazador

**Identidad**: **tercera especie** del bestiario (*ferox*, feroz). Ni quitina de insecto ni roca: un **depredador
óseo**, rápido y afilado. Su papel no es aguantar, es **alcanzarte** — es el bicho veloz del 1-1. Tier `BASE`.

**Regla de legibilidad — la decisión importante**: las dos familias que ya existen son **oscuras** (quitina
morada-negra del Vex, basalto gris del Skarn). El Ferox se separa por **valor, no solo por forma**: carcasa
**pálida, hueso-marfil**, que a 150 px se distingue de las otras dos de un vistazo incluso antes de leer su
silueta. El acento sigue siendo **rojo hostil**, aquí como ojos y costuras encendidas sobre el hueso claro.

Silueta: alargada y flechada, hojas en vez de garras — todo lo contrario del peñasco del Skarn.

## Prompt (pegar en Gemini / Recraft)

> Strict top-down orthographic view of a fast hostile alien predator, front pointing straight up, perfectly
> centered. Sleek elongated arrow-shaped body made of pale bone-white and ivory carapace plates over dark sinew,
> two long curved blade-like arms swept forward from the shoulders, a narrow pointed head, and a thin whip-like
> tail trailing behind. Smooth polished bone armor with sharp edges, ribbed segments along the spine. Glowing
> crimson-red eyes clustered on the head and thin red emissive seams running between the bone plates.
> Lean, fast and lethal — a hunter, not a tank — industrial dark sci-fi, high detail, video game enemy asset
> render.
> Lighting strictly from directly above (camera axis), no side lighting, no ground shadow.
> Flat solid chroma green background (#00B140), no vignette, no other objects, 1024x1024.

**Escala**: más largo que ancho; entre el Vexor y el Skarn en masa, pero estilizado — debe parecer rápido parado.

## Post-proceso

```bash
py -3 tools/chroma-key.py source/renders/Ferox.jpeg source/renders/ferox-cut.png
py -3 tools/export-png.py           # regenera todos los exports (NPCs a 512)
```

**Ojo con el croma**: es el primer asset **claro** del catálogo. El chroma-key trae un dial de luminancia mínima
(`LMIN`) pensado para naves oscuras; con hueso pálido hay que revisar que no se coma bordes brillantes. Y en la
capa emisiva, cuidado con el mismo problema del Skarn al revés: el hueso marfil tiene algo de rojo, así que si
el cuerpo entero se enciende, **subir el umbral**.
