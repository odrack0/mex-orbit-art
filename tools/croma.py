# -*- coding: utf-8 -*-
"""El recorte del croma. UN solo sitio, porque vivio en dos y se separaron.

`chroma-key.py` (renders fijos) y `video-atlas.py` (video a atlas) nacieron con
el mismo criterio copiado y pegado. Cuando el recorte del atlas se rehizo por el
contorno de la estacion, el de las naves se quedo con el despill viejo — el que
quitaba el 92% del verde sobrante y SUMABA un 30% a rojo y azul, que sobre croma
puro deja un teal. Dos copias de una regla son una regla y un fallo esperando.
"""
import numpy as np
from scipy.ndimage import (binary_closing, binary_dilation, binary_fill_holes,
                           distance_transform_edt, label)


def recortar(a, T=22.0):
    """Recorte del croma por DESMEZCLA, no por mascara binaria + desenfoque.

    El primer keyer umbralizaba y luego difuminaba la mascara. Eso trae tres
    defectos que resultaron ser el mismo defecto:

      · **Silueta con escalones.** Umbralizar cuantiza el contorno a pixeles
        enteros, y difuminar despues no recupera la forma: la suaviza uniforme.
      · **Ribete de croma.** Un pixel de borde es `objeto*a + croma*(1-a)`. El
        despill solo baja el canal verde; lo que el croma aporto en LUMINANCIA
        se queda dentro. De ahi el ribete —turquesa con el despill viejo, oscuro
        con el nuevo—, que en la estacion se ve porque se dibuja a 2,5x su celda.
      · **Vanos rellenos de verde.** Un hueco cerrado se rellenaba o no segun su
        TAMANIO (< 2500 px), y el tamanio nunca fue el criterio: los vanos del
        aro de la base miden ~1.400 px y quedaban dentro, en verde.

    Un keyer de verdad estima un alfa CONTINUO y desmezcla: resta lo que puso el
    croma y divide por el alfa. El borde queda del color que tiene el objeto, con
    su forma real y a resolucion mayor que el pixel, sin erosiones ni parches.
    """
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    greenness = g - np.maximum(r, b)
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # El croma se MIDE en el propio video en vez de darlo por supuesto: cada
    # generador entrega un verde distinto, y desmezclar con el color equivocado
    # tinie el borde tanto como no desmezclar.
    puro = greenness > max(np.percentile(greenness, 88), T)
    if puro.any():
        croma = np.array([np.median(a[:, :, c][puro]) for c in range(3)])
        k = max(float(np.median(greenness[puro])), 1.0)
    else:
        croma, k = np.array([0.0, 177.0, 64.0]), 120.0

    # Alfa CONTINUO: 1 sin verde, 0 en croma puro, rampa en medio. La rampa es
    # el borde real del objeto, medido, no un desenfoque inventado despues.
    alpha = np.clip(1.0 - greenness / k, 0.0, 1.0)
    alpha[greenness / np.maximum(lum, 1.0) > 0.25] = 0.0   # la sombra es croma oscurecido

    # DESMEZCLA (unpremultiply), pero solo donde el alfa da para dividir.
    #
    # Dividir por 0,05 multiplica el error por veinte: el borde no salia limpio,
    # salia PUNTEADO de verde oscuro — ruido amplificado, no croma. Por debajo de
    # 0,25 no hay senial que recuperar, y el color de esos pixeles lo pone el
    # sangrado de mas abajo, que es informacion real del objeto.
    seg = alpha[:, :, None]
    out = (a - croma[None, None, :] * (1.0 - seg)) / np.maximum(seg, 0.25)

    # Limpieza sobre una version binaria del alfa. Un hueco cerrado es fondo si
    # es VERDE, y mota si no lo es — sea del tamanio que sea.
    pieza = binary_closing(alpha > 0.5, np.ones((3, 3)))
    rellenar = np.zeros_like(pieza)
    lab_h, nh = label(binary_fill_holes(pieza) & ~pieza)
    for i in range(1, nh + 1):
        hueco = lab_h == i
        if greenness[hueco].mean() < 12.0:
            rellenar |= hueco
    solido = pieza | rellenar
    lab, n = label(solido)
    if n > 1:
        tam = np.bincount(lab.ravel())
        tam[0] = 0
        solido = np.isin(lab, np.where(tam >= max(24, int(0.00004 * solido.size)))[0])

    alpha = np.where(rellenar & solido, 1.0, alpha)
    # fuera de la pieza (mas un pixel para no comerse la rampa) no queda nada
    alpha = np.where(binary_dilation(solido, np.ones((3, 3))), alpha, 0.0)

    # SANGRADO DE COLOR. El paso que faltaba, y el que se veia.
    #
    # Godot filtra la textura en bilineal, y al filtrar mezcla el RGB de los
    # texeles vecinos SIN mirar su alfa. Un texel transparente que guarde croma
    # verde no es inofensivo por ser invisible: su color entra en la media y tinie
    # el borde del de al lado. A 1x apenas se nota; la base se dibuja a 2,5x su
    # celda y ahi cada texel del contorno se reparte entre varios pixeles de
    # pantalla, asi que el ribete se multiplica.
    #
    # La cura es de manual: a cada pixel transparente se le pone el color del
    # pixel OPACO mas cercano. Sigue siendo invisible —el alfa manda—, pero ahora
    # lo que el filtro mezcla es el color del objeto y no el del croma.
    # Alcanza a TODO lo que no tiene color propio fiable: lo transparente del
    # todo y tambien la banda de alfa bajo que la desmezcla no puede reconstruir.
    opaco = alpha > 0.5
    if opaco.any():
        _, idx = distance_transform_edt(~opaco, return_indices=True)
        out = np.where((alpha > 0.25)[:, :, None], out, out[idx[0], idx[1]])
    return np.dstack([np.clip(out, 0, 255), alpha * 255.0]).astype(np.uint8), solido
