# Assets del vertical slice E2 — inventario y estado

**Actualizado: 2026-08-25.** El slice (*login → volar → matar un Vex → recoger carga → base → refinar →
almacén → vender*) necesita exactamente esto para ser jugable. Regla de origen por tipo:

- **Todo lo renderizado** (naves, NPCs, estación, caja, portal) → pipeline **PNG directo** (dictamen 2026-08-25): render cenital 1024 → `chroma-key.py` → downscale Lanczos (`export-png.py`) + capas emisivas (`extract-emissive.py`) + pasada de coherencia opcional (`obsidiana.py`). **Jamás dibujados a mano; la vectorización quedó retirada del pipeline** (posterizaba el brillo y mordía contornos — comparación del 25-ago).
- Tamaños de export (dial): naves/NPCs **512** (aguantan el zoom 3× de cámara), estación **1024**, props **256**.
- **Fondos y efectos** → procedurales, generados por `tools/gen-slice-procedural.py` (deterministas, regenerables).
- **UI** → cubierta por el sistema de diseño N (`mex-orbit-docs/05-arte/03-sistema-diseno-ui.md`), no vive en este repo.

## Estado

| Asset | Estado | Archivo | Origen |
|---|---|---|---|
| Fondo del mapa 1-1 | ✅ generado | `world/backgrounds/map-1-1.png` (2048×1260) | procedural |
| Tile de estrellas (parallax) | ✅ generado | `world/backgrounds/starfield-tile.png` (1024, repetible) | procedural |
| Láser cian (jugador) | ✅ generado | `fx/laser-cyan.png` (256×24, blend ADD) | procedural |
| Láser rojo (hostil) | ✅ generado | `fx/laser-red.png` | procedural |
| Explosión (8 frames) | ✅ generado | `fx/explosion-sheet.png` (8×128) | procedural |
| Caja de carga | ✅ propuesta | `world/props/cargo-box.svg` | SVG geométrico |
| Portal | ✅ propuesta | `world/props/portal.svg` | SVG geométrico |
| **Nave Phoenix** | ✅ **vectorizada** (render 2026-08-25) | `ships/phoenix.svg` · fuente `source/renders/Phoenix.jpeg` | pipeline IA |
| **NPC Vex** | ✅ **vectorizado** | `npcs/vex.svg` · fuente `source/renders/Vex.jpeg` | pipeline IA |
| **Estación base** | ✅ **vectorizada** | `world/props/station.svg` · fuente `source/renders/Base.jpeg` | pipeline IA |
| Placeholders (Phoenix/Vex/estación) | 🗄️ obsoletos | `placeholders/` | sustituidos por los finales; se conservan como referencia |

## Contrato de render (resumen — completo en `prompts/README.md`)

Cenital ortográfica estricta · proa arriba · luz axial desde la cámara · croma verde `#00B140` sin sombra ·
1024×1024 con la pieza al ~70% · escala relativa coherente. Validar la silueta a ~150 px antes de vectorizar.

## Cómo regenerar lo procedural

```bash
py -3 tools/gen-slice-procedural.py
```

Semilla fija (`20260825`): regenerar produce exactamente los mismos bytes. Cambiar la estética = cambiar el
script, no retocar el PNG.

## Pendientes conocidos

- Los tres renders IA (Phoenix, Vex, estación) — requieren pasar los prompts por Gemini/Recraft y correr el post-proceso.
- La pasada de coherencia "Obsidiana" (`tools/design-mexorbit.py`) se aplicará cuando haya ≥2 naves para unificar material.
- Dirección de estilo del mundo (paleta de nebulosas por facción/zona, densidad de decorado): sesión de arte propia; el fondo actual es la base neutral.
