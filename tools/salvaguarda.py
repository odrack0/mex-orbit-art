# -*- coding: utf-8 -*-
"""Impide que una herramienta escriba encima de una fuente.

Nacio de destruir `crudo/vexor-texture-v2.glb`: 130 MB de modelo generado en
Meshy sobrescritos por una exportacion de Blender que apuntaba a esa ruta. La
carpeta `crudo/` esta en .gitignore —con razon, son 130 MB por pieza— asi que no
habia copia. Un error de un argumento borro algo que cuesta creditos y no se
regenera igual dos veces.

Las tres reglas, en orden de lo que habria salvado el dia:

  1. Nunca escribir DENTRO de `crudo/`. Ahi solo entra lo que descarga el humano.
  2. Nunca escribir sobre la propia entrada.
  3. Al sobrescribir cualquier otro archivo, decirlo por pantalla.

Uso:  from salvaguarda import comprobar_salida
      comprobar_salida(entrada, salida)
"""
import os
import sys

# Carpetas que ninguna herramienta puede escribir. Se comparan por nombre de
# directorio, asi que vale para cualquier repo y cualquier disco.
PROHIBIDAS = ("crudo", "renders")


def comprobar_salida(entrada, salida):
    """Aborta si `salida` pisa una fuente. Devuelve la ruta si todo esta bien."""
    ent = os.path.abspath(entrada) if entrada else ""
    sal = os.path.abspath(salida)

    partes = [p.lower() for p in os.path.normpath(sal).split(os.sep)]
    for prohibida in PROHIBIDAS:
        if prohibida in partes:
            print("ABORTA: '%s' esta dentro de %s/, que es material FUENTE." % (salida, prohibida))
            print("        Ahi solo entra lo que descargas a mano. Escribe en otro sitio.")
            sys.exit(2)

    if ent and os.path.normcase(ent) == os.path.normcase(sal):
        print("ABORTA: la salida es la MISMA ruta que la entrada (%s)." % salida)
        sys.exit(2)

    if os.path.exists(sal):
        mb = os.path.getsize(sal) / 1048576.0
        print("AVISO: se sobrescribe %s (%.1f MB)" % (salida, mb))

    return salida
