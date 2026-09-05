# Brief de texturas — qué pedirle al generador para que encaje en el mundo

> Complementa el **contrato del concepto 3D** del [README](README.md) (que
> gobierna la imagen que va a Meshy). Este documento gobierna el **paso de
> texturizado**: qué tiene que salir en cada canal PBR para que la malla se lea
> bien bajo la luz que el juego tiene de verdad.

La luz de Astrion no es negociable desde el arte: es **una sola direccional**,
sin sombras, con un ambiente rosado bajísimo y un cielo de reflexión casi
negro. Una textura bonita en el visor de Meshy puede convertirse en una mancha
plana o en un espejo negro al entrar. Todo lo que sigue sale de
`mex-orbit-client/data/config/lighting.json` y de medir las texturas que hoy
tenemos.

---

## 1. El mundo, en números

| Dial | Valor | Qué le hace a tu textura |
|---|---|---|
| Sol direccional | blanco `ffffff`, energía **1,0**, specular **0,7**, tilt 100 / pan 35 (arriba-izquierda) | Es la **única** luz de forma. Si pintas tu propia luz, se pelea con esta |
| Ambiente | `ffa5ae` (rosa) a **0,2** | El relleno es casi nada, y **rosado**. La cara en sombra se hunde |
| Sombras | **no hay** | Una sombra pintada no gira con el bicho: canta al primer giro |
| Cielo de reflexión | gradiente muy oscuro (`1c2434` → `3b2d28` → `050608`), energía **0,6** | Un metal refleja **casi negro**. Metálico alto = pieza negra |
| `metallic_scale` | **0,6** | Tu mapa metálico se multiplica por esto antes de usarse |
| `roughness_scale` | **0,9** | Tu mapa de rugosidad se usa casi tal cual |
| `roughness` (sin mapa) | **0,35** | Si no entregas mapa, **todo el bicho** es brillo cerrado uniforme |
| Rim / fresnel | rim 0,3, tint 0,5 | El cliente ya te pone el borde iluminado. No lo pintes |
| Glow | bloom 0,25, **umbral 0,9** | Solo florece lo que pase de 0,9. Un emisivo pálido no brilla |
| Luz del héroe | punto azul `2e7dff` a 0,6, solo en tu nave | Tu propia nave recibe un tinte azul que los NPCs no |
| Tamaño en pantalla | **124–248 px** de `screen_size` | El detalle fino no existe; hierve al moverse |

---

## 2. Estado real de lo que tenemos hoy

Medido sobre los 15 GLB del cliente (luminancia en sRGB de la textura, no del
render):

| asset | mapas que trae | base p50 | base p95 | emisivo > 0,5 |
|---|---|---:|---:|---:|
| **aci-01** | base + emis | **0,38** | **0,54** | **4,4 %** |
| aci-05 | ORM + base + emis + normal | 0,22 | 0,31 | 4,1 % |
| aci-03 | ORM + base + emis + normal | 0,13 | 0,21 | 2,1 % |
| aci-04 | ORM + base + emis + normal | 0,16 | 0,31 | 1,4 % |
| vorax | base + emis | 0,20 | 0,85 | 1,3 % |
| phoenix | base + emis | 0,30 | 0,45 | 1,0 % |
| skarnox | base + emis | 0,17 | 0,28 | 0,8 % |
| aci-02 | ORM + base + emis + normal | 0,24 | 0,38 | 0,3 % |
| **ferox** | base + emis | **0,64** | **0,90** | **0 %** |
| mordax | base + emis | 0,17 | 0,73 | 0 % |
| gravit | base + emis | 0,32 | 0,76 | 0 % |
| vex | base + emis | 0,18 | 0,40 | 0 % |
| gravon | ORM + base + emis + normal | 0,19 | 0,26 | 0 % |
| skarn | ORM + base + emis + normal | 0,17 | 0,32 | 0 % |
| vexor | base + emis | 0,15 | 0,33 | 0 % |

Tres problemas, todos arreglables desde el prompt:

1. **9 de 15 no traen rugosidad, metálico ni normales.** Sin mapa de rugosidad
   el cliente aplica **0,35 plano a todo el bicho**: la roca y el metal pulido
   quedan con el mismo brillo. Toda la narrativa de material se pierde.
2. **8 de 15 no emiten nada** (0 % de texels por encima de 0,5). El emisivo se
   deriva del **color dominante del base color**: si el generador pinta las
   luces como degradados pálidos con centro blanco, no hay canal dominante que
   cazar y el bicho sale apagado.
3. **El rango de luminancia se va por los dos lados.** `ferox` a p50 0,64 y p95
   0,90 se quema con sol 1,0 + specular 0,7. `aci-03`, `gravon`, `skarn` y
   `vexor` a p50 ~0,15 se hunden, porque el único relleno es el ambiente a 0,2.
   `mordax`, `gravit` y `vorax` tienen p95 de 0,73–0,85 contra p50 de 0,17–0,32:
   eso son **brillos pintados dentro del albedo**, luz falsa que pelea con el sol.

`aci-01` es el que mejor se comporta y su perfil (p50 0,38, p95 0,54, emisivo
4,4 %) es de donde salen los objetivos de abajo.

---

## 3. Objetivos por canal

| Canal | Objetivo | Por qué |
|---|---|---|
| **Base Color** | p50 **0,28–0,45** · p95 **≤ 0,65** · p05 **≥ 0,08** | Rango comprimido: ni se quema con el sol ni se hunde con el ambiente a 0,2 |
| Base Color — luz pintada | **ninguna** | Sin degradados de iluminación, sin AO horneada, sin rim, sin sombra proyectada |
| Base Color — parches emisivos | **≥ 3 %** del área, color **plano y saturado**, borde duro | El emisivo se extrae por canal dominante; sin canal dominante no hay emisión |
| **Roughness** | p50 **0,45–0,70**, con variación real entre materiales | Se multiplica por 0,9. Por debajo de 0,3 sale espejo negro contra el cielo oscuro |
| **Metallic** | casco **≤ 0,25** · adornos hasta 0,8 · **menos del 20 %** del área por encima de 0,5 | Se multiplica por 0,6 y refleja un cielo casi negro: metálico alto = pieza negra |
| **Normal** | relieve **medio**: placas, grietas, chapas, escamas | El detalle fino hierve a 124–248 px; el medio es lo único que sobrevive |
| **AO** | **no entregar** | El cliente no cablea el canal de oclusión; si la horneas en el base color, es luz pintada |

### Colores de emisión admitidos

Uno por especie, plano y saturado, sin halo ni núcleo blanco:

`#00FFFF` cian · `#FF00FF` magenta · `#FF2000` rojo · `#00FF40` verde ·
`#FFE000` amarillo

### Cuerpo contra fondo

El fondo del 1-1 es **nebulosa naranja sobre negro**. Un cuerpo naranja o rojo
se funde con él salvo que sea lava emisiva. Gris plomo, obsidiana, quitina
oscura y hueso frío separan bien.

---

## 4. El prompt

Para el paso de texturizado de Meshy (o cualquier generador PBR). Sustituye lo
que va entre corchetes.

```text
PBR texture set for a [sci-fi combat drone / mineral alien / armored hull] seen
from above in a top-down space game. The model is lit in-engine by a SINGLE
white directional light from the upper left plus a very weak flat ambient fill.
Paint MATERIAL, never lighting.

BASE COLOR
- Mid-value surface, average luminance around 35%, nothing brighter than 65%,
  nothing crushed to black. Narrow value range.
- NO baked lighting of any kind: no highlights, no ambient occlusion, no cast
  shadows, no rim light, no gradients that imply a light direction.
- Material colours only: [dark gunmetal grey painted metal / obsidian chitin /
  cold bone / weathered iron], desaturated, with large readable colour blocks.
- Panel lines, seams, plate edges, scratches, rust, grime and wear ARE wanted,
  painted as albedo variation.
- Emissive areas painted as FLAT SOLID [cyan #00FFFF] patches with hard edges,
  fully saturated, no halo, no glow, no white core, covering at least 3% of the
  texture. One emissive colour only.

ROUGHNESS
- Mid to high roughness overall, around 0.55 average. Real contrast between
  materials: worn metal and rock rough, trim and lenses smoother.
- Nothing mirror-polished: minimum roughness 0.30.

METALLIC
- Mostly non-metal. Hull and body below 0.25. Reserve high metallic for small
  trim, bolts and exposed mechanical parts, under 20% of the surface.
- Never a fully metallic body.

NORMAL
- Medium-frequency relief only: armour plates, seams, large dents, scales,
  bolts. No micro-noise, no fabric weave, no fine speckle.

Output 1024x1024 or 2048x2048, base colour + roughness + metallic + normal.
```

**Negativo:**

```text
baked lighting, ambient occlusion, cast shadow, drop shadow, rim light,
specular highlights painted in, glow, bloom, halo, white hot core, gradient
lighting, studio reflection, high contrast, blown highlights, pure black, pure
white, fully metallic, chrome, mirror, glass, transparency, subsurface, fur,
smoke, micro noise, fine speckle, text, logo, watermark, decals, tiny greebles
```

---

## 5. Comprobar antes de aceptar

```bash
py tools/asset-audit/validate_texture.py ../mex-orbit-client/assets/npcs/aci-01.glb
```

Comprueba los objetivos del §3 sobre el GLB texturizado: qué mapas trae, la
banda de luminancia del base color, la rugosidad, el metálico y la cobertura
emisiva por canal.

Y la prueba que no automatiza nada: **mira el bicho en el juego, no en el visor
de Meshy.** El visor lo enseña con luz de estudio; el juego, con un sol y un
ambiente de 0,2.

---

## 6. Lo que NO se arregla con textura

- **La curvatura de un ala plana** se arregla con normal map — eso sí. Pero la
  **silueta** no: si el contorno es pobre, ninguna textura lo salva. Ver
  [ASTRION_LOW_POLY_MODELING_STANDARD](../../mex-orbit-docs/03-guidelines/astrion-lowpoly/ASTRION_LOW_POLY_MODELING_STANDARD.md) §5.
- **La resolución no compra lectura.** Un bicho ocupa 124–248 px: a 1024 ya
  sobran texels (medido en DarkOrbit: 110 texels por triángulo bastaban). Subir
  a 2048 no lo hace más legible, solo más caro en VRAM.
