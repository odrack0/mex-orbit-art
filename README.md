# mex-orbit-art

La fuente de todo el arte del juego: **cero assets heredados — identidad visual propia desde el vector**.

> **MexOrbit** es nombre temporal del proyecto. Documentación en español.

## Qué es

- **Los archivos fuente** (vectorial: SVG/proyectos de edición) de naves, aliens, drones, items, efectos, mapas/fondos y UI — la base vectorial de naves ya aprobada en fase 0 es el punto de partida del estilo.
- **El pipeline de exportación**: de fuente vectorial a los formatos que `mex-orbit-client` consume (spritesheets/texturas/atlas), reproducible y documentado.
- **La guía de identidad visual**: paleta, estilo, y la iconografía de las 5 familias de nombres del diseño (materiales, legendarios, códigos de equipo, constelaciones, taxonomía alien).

## Qué NO es

- No es el repo de assets *importados* del cliente (eso es salida del pipeline, versionada en `mex-orbit-client`); aquí vive la **fuente**.
- Nada derivado de BigPoint entra a este repo — ni sprites, ni trazas, ni paletas calcadas.

## Organización (propuesta inicial, por definir con el pilar de arte)

```
ships/        # naves (constelaciones)
aliens/       # taxonomía (Vex → Imperator)
items/        # iconografía de equipo, materiales, consumibles
ui/           # design system: componentes, iconos, tipografía
maps/         # fondos y elementos de mapa
fx/           # efectos (láseres, explosiones, recubrimientos)
pipeline/     # scripts de exportación
brand/        # identidad (nota: el nombre del juego es temporal — nada de logos definitivos aún)
```

## Relación con otros repos

| Repo | Relación |
|---|---|
| `mex-orbit-client` | Consumidor de las exportaciones |
| `mex-orbit-docs` | El pilar 05-arte define la dirección; aquí se ejecuta |

## Estado

Repo recién creado.
