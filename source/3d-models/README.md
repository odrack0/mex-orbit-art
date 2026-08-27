# Modelos 3D

```
crudo/          lo que devuelve Meshy — IGNORADO por git
<nombre>.glb    el master de trabajo — versionado
```

## Por qué el crudo no entra a git

Un modelo crudo de Meshy pesa **78 MB**: dos millones de triángulos y tres
texturas de 2048 para un bicho que se dibuja a 178 px en pantalla. Es diez veces
el archivo más grande que este repo tiene hoy (8,5 MB), no hay LFS, y git no
olvida: si entra una vez, cada clon lo paga para siempre.

La carpeta `crudo/` existe igualmente porque tenerlo a mano ahorra volver a
generarlo. Pero **una carpeta en el mismo disco no es un respaldo, es una copia**
— si de verdad quieres respaldo de los crudos, tienen que salir de esta máquina.

## Por qué el master sí

La regla de los vídeos (`source/renders/*.mp4`: «sin él no se puede reexportar a
otros fps ni a otra resolución») aplica igual aquí, porque un modelo de Meshy
tampoco se regenera igual dos veces.

Lo que se versiona es la versión **de la que se puede re-exportar a cualquier
presupuesto de juego**: 200 000 triángulos y texturas de 1024, unos 7,4 MB. Los
dos millones no hacen falta para nada — está medido que a 15 000 no se distinguen
a tamaño de juego.

## Cómo se produce cada cosa

```bash
# crudo -> master (esto se versiona)
blender --background --factory-startup --python ../../tools/normalize-model.py -- \
    crudo/vexor-texture.glb vexor.glb 200000 1024 r

# master -> asset de juego (esto va al cliente)
blender --background --factory-startup --python ../../tools/normalize-model.py -- \
    vexor.glb <cliente>/pruebas/vexor.glb 15000 512 r
```

Antes de normalizar, validar:

```bash
py -3 ../../../mex-orbit-testing/assets/validar-modelo.py crudo/vexor-texture.glb
```
