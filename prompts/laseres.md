# Láseres — el haz normal y el potenciado

**Identidad**: neón. Un tubo de luz, no una mancha luminosa. Lo que distingue al neón de un simple
resplandor es el **contraste entre un núcleo nítido y un halo suave** — los haces actuales son todo
halo y ningún núcleo, y por eso se leen como borrones.

## Dos reglas del pipeline que NO son negociables

**1. El arte va en BLANCO Y NEGRO. Sin color.**

El color lo pone el juego con `modulate`, según la munición equipada: CEL-1 rojo `#FA0000`, CEL-2 azul
`#0079F9`, y los que vengan. Un haz ya coloreado no se puede teñir — saldría marrón o sucio. Es la
misma regla que los iconos de la UI, y por el mismo motivo.

**2. Fondo NEGRO puro, no transparente.**

El haz se dibuja en **blend aditivo**, y en aditivo el negro no aporta nada: es transparente de hecho.
Pedir negro en vez de transparencia es más fiable —los generadores respetan mal el alfa— y aquí sale
gratis.

## Geometría

Horizontal, **apuntando a la derecha**: el juego rota el sprite con `rotation = delta.angle()` y el
arte se da por hecho que apunta a `+X`. Centrado verticalmente, ocupando todo el ancho del lienzo.

| | Lienzo a pedir | Proporción | Export final |
|---|---|---|---|
| Normal | 1024×160 | 6,4:1 | `beam.png` 156×24 |
| Potenciado | 1024×264 | 3,9:1 | `beam-skilled.png` 156×40 |

**El potenciado es el MISMO arma**, no otra: mismo lenguaje, mismo perfil, solo más grueso y más
brillante. Si parecen dos armas distintas, está mal.

## Prompt — haz normal

> A horizontal neon energy beam on a pure black background, pointing right, centered, spanning the full
> width of the frame. WHITE AND GREYSCALE ONLY — absolutely no color, no hue, no tint of any kind.
>
> Structure, from the middle outward: a razor-sharp pure white core line, very thin and perfectly
> crisp; a tight bright halo hugging that core; and a soft wide bloom fading smoothly to pure black at
> the top and bottom edges. The contrast between the sharp core and the soft bloom is the whole point —
> it must read as a neon tube, not as a blurred streak.
>
> The beam TAPERS to points at both ends, like a bolt in flight — not a rounded rectangle, not a
> capsule, not a lozenge. Slightly brighter and denser toward the leading (right) tip.
>
> Flat and even along its length: no segmentation, no dashes, no lightning, no particles, no sparks, no
> lens flare, no starburst, no background stars, no glare crosses. Nothing but the beam.
>
> 1024x160 pixels, pure black background (#000000).

## Prompt — haz potenciado

Idéntico al anterior salvo el bloque de grosor y el lienzo:

> ...a razor-sharp pure white core line — **thicker and more intense than a standard beam, roughly
> double the core width**; a tight bright halo hugging that core; and a **stronger, wider** soft bloom
> fading smoothly to pure black at the top and bottom edges.
>
> ...1024x264 pixels, pure black background (#000000).

## Al recibirlos

```bash
py -3 ../mex-orbit-testing/assets/matiz.py source/renders/beam.png
```

Si el matiz sale con saturación por encima de ~0,10, **el generador coló color** y hay que rechazarlo:
teñir sobre un haz que ya tira a un lado da un color que no es el de la munición.

Y mirarlos **a tamaño de juego** antes de exportar: 156 px de largo por 24 de grosor es muy poco
lienzo, y un núcleo que a 1024 se ve nítido puede desaparecer al bajar. Si el núcleo se pierde, es
que era demasiado fino en el original.
