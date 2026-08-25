# -*- coding: utf-8 -*-
"""Genera preview/index.html: visor autocontenido (data URIs) de los assets del slice.
Uso:  py -3 tools/gen-preview.py
"""
import base64
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dato(ruta, mime):
    with open(os.path.join(RAIZ, ruta), 'rb') as f:
        return f'data:{mime};base64,' + base64.b64encode(f.read()).decode()


PNG = 'image/png'
SVG = 'image/svg+xml'

D = {
    'fondo': dato('world/backgrounds/map-1-1.png', PNG),
    'tile': dato('world/backgrounds/starfield-tile.png', PNG),
    'laserc': dato('fx/laser-cyan.png', PNG),
    'laserr': dato('fx/laser-red.png', PNG),
    'expl': dato('fx/explosion-sheet.png', PNG),
    'caja': dato('world/props/cargo-box.svg', SVG),
    'portal': dato('world/props/portal.svg', SVG),
    'phx': dato('placeholders/phoenix-placeholder.svg', SVG),
    'vex': dato('placeholders/vex-placeholder.svg', SVG),
    'est': dato('placeholders/station-placeholder.svg', SVG),
    'fphx': dato('ships/phoenix.svg', SVG),
    'fvex': dato('npcs/vex.svg', SVG),
    'fest': dato('world/props/station.svg', SVG),
}

HTML = """<title>Assets Slice E2</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Michroma&family=Exo+2:wght@400;600&family=JetBrains+Mono&display=swap">
<style>
  :root{--bg:#07070F;--cyan:#00E5FF;--violet:#A78BFA;--warn:#FFC85C;--txt:#E8F0FF;--muted:#8A97B8;
    --edge:rgba(0,229,255,.3);--edge-soft:rgba(120,140,180,.22)}
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--txt);font-family:'Exo 2',sans-serif;padding:32px 24px 60px}
  h1{font-family:'Michroma';font-size:16px;letter-spacing:.2em;color:var(--cyan);text-transform:uppercase}
  .sub{font-size:12px;color:var(--muted);margin:6px 0 30px}
  h2{font-family:'Michroma';font-size:10px;letter-spacing:.2em;color:var(--txt);text-transform:uppercase;
    margin:34px 0 12px;padding-left:10px;border-left:3px solid var(--cyan)}
  .grid{display:flex;flex-wrap:wrap;gap:14px}
  .card{background:rgba(13,17,29,.74);border:1px solid var(--edge-soft);padding:12px;position:relative}
  .card::before{content:"";position:absolute;top:-1px;left:-1px;width:11px;height:11px;
    border-top:1.5px solid var(--cyan);border-left:1.5px solid var(--cyan)}
  .card h3{font-family:'Michroma';font-size:8px;letter-spacing:.14em;color:var(--muted);
    text-transform:uppercase;margin-bottom:10px}
  .card .meta{font-family:'JetBrains Mono';font-size:9.5px;color:var(--muted);margin-top:8px}
  .stage{background:url(__TILE__) #07070F;display:flex;align-items:center;justify-content:center;
    gap:26px;padding:18px;min-height:120px}
  .big img{width:100%;display:block;border:1px solid var(--edge-soft)}
  .tag{display:inline-block;font-family:'Michroma';font-size:7px;letter-spacing:.12em;padding:3px 8px;
    margin-left:8px;text-transform:uppercase}
  .tag.ok{color:#3DF58C;border:1px solid rgba(61,245,140,.4)}
  .tag.prop{color:var(--warn);border:1px solid rgba(255,200,92,.4)}
  .tag.dev{color:var(--violet);border:1px solid rgba(167,139,250,.4)}
  .tag.pend{color:#FF3D6E;border:1px solid rgba(255,61,110,.4)}
  .expl{image-rendering:auto;background:#0A0E18;padding:8px;border:1px solid var(--edge-soft)}
  .laser{background:#0A0E18;padding:14px 18px;border:1px solid var(--edge-soft);display:flex;
    flex-direction:column;gap:14px}
  .prompt{max-width:520px;font-size:12px;color:var(--muted);line-height:1.5}
  .prompt b{color:var(--txt)}
  .prompt code{font-family:'JetBrains Mono';font-size:10px;color:var(--cyan)}
</style>
<h1>Assets del Slice E2</h1>
<div class="sub">mex-orbit-art · primera pasada (2026-08-25) · lo procedural y los props son propuesta;
naves/NPC/estación esperan su render IA — los placeholders son solo para desarrollo</div>

<h2>Fondo del mapa 1-1 <span class="tag ok">generado</span></h2>
<div class="card big"><img src="__FONDO__" alt="Fondo del mapa 1-1">
  <div class="meta">world/backgrounds/map-1-1.png · 2048×1260 (ratio 1.625 del mapa 20800×12800) · procedural determinista</div></div>

<h2>Efectos <span class="tag ok">generados</span></h2>
<div class="grid">
  <div class="card"><h3>Láseres (blend ADD)</h3>
    <div class="laser"><img src="__LASERC__" width="256" alt="láser cian"><img src="__LASERR__" width="256" alt="láser rojo"></div>
    <div class="meta">fx/laser-cyan.png · fx/laser-red.png · 256×24</div></div>
  <div class="card"><h3>Explosión · 8 frames</h3>
    <img class="expl" src="__EXPL__" width="560" alt="explosión">
    <div class="meta">fx/explosion-sheet.png · 8 × 128×128</div></div>
</div>

<h2>Props del mundo <span class="tag prop">propuesta a dictamen</span></h2>
<div class="grid">
  <div class="card"><h3>Caja de carga</h3>
    <div class="stage"><img src="__CAJA__" width="40" alt="caja 40px"><img src="__CAJA__" width="64"><img src="__CAJA__" width="128"></div>
    <div class="meta">world/props/cargo-box.svg · en juego ~40 px (izquierda)</div></div>
  <div class="card"><h3>Portal</h3>
    <div class="stage"><img src="__PORTAL__" width="90" alt="portal 90px"><img src="__PORTAL__" width="160"></div>
    <div class="meta">world/props/portal.svg · en juego ~140 px</div></div>
</div>

<h2>Naves, NPC y estación — vectorizados del render IA <span class="tag ok">finales a dictamen</span></h2>
<div class="grid">
  <div class="card"><h3>Phoenix · nave inicial</h3>
    <div class="stage"><img src="__FPHX__" width="150" alt="phoenix a tamaño de juego"><img src="__FPHX__" width="300"></div>
    <div class="meta">ships/phoenix.svg · izquierda: ~150 px, el tamaño real en juego</div></div>
  <div class="card"><h3>Vex · alien base</h3>
    <div class="stage"><img src="__FVEX__" width="150" alt="vex a tamaño de juego"><img src="__FVEX__" width="300"></div>
    <div class="meta">npcs/vex.svg · izquierda: ~150 px</div></div>
  <div class="card"><h3>Estación base</h3>
    <div class="stage"><img src="__FEST__" width="300" alt="estación"><img src="__FEST__" width="440"></div>
    <div class="meta">world/props/station.svg · en juego ~300 px (izquierda)</div></div>
</div>

<h2>Placeholders de desarrollo <span class="tag dev">sustituidos por los finales</span></h2>
<div class="grid">
  <div class="card"><h3>Phoenix (stand-in)</h3>
    <div class="stage"><img src="__PHX__" width="72" alt="phoenix placeholder"><img src="__PHX__" width="128"></div>
    <div class="meta">placeholders/phoenix-placeholder.svg</div></div>
  <div class="card"><h3>Vex (stand-in)</h3>
    <div class="stage"><img src="__VEX__" width="72" alt="vex placeholder"><img src="__VEX__" width="128"></div>
    <div class="meta">placeholders/vex-placeholder.svg</div></div>
  <div class="card"><h3>Estación (stand-in)</h3>
    <div class="stage"><img src="__EST__" width="150" alt="estación placeholder"><img src="__EST__" width="220"></div>
    <div class="meta">placeholders/station-placeholder.svg</div></div>
</div>

<h2>Origen <span class="tag ok">pipeline completo</span></h2>
<div class="grid">
  <div class="card prompt"><h3>Cómo se produjeron</h3>
    Render IA cenital 1024 con el contrato aprobado (ortográfica estricta, proa arriba, luz axial, croma
    verde) → <code>chroma-key.py</code> (recorte + despill) → <code>vectorize-ship.py</code> (bandas de
    luminancia + pasada cromática). Los renders fuente viven en <code>source/renders/</code>; regenerar es
    correr los mismos comandos de <code>prompts/*.md</code>.</div>
</div>
"""

for clave, uri in D.items():
    HTML = HTML.replace('__' + clave.upper() + '__', uri)

destino = os.path.join(RAIZ, 'preview', 'index.html')
os.makedirs(os.path.dirname(destino), exist_ok=True)
with open(destino, 'w', encoding='utf-8') as f:
    f.write(HTML)
print(f'preview/index.html  {os.path.getsize(destino) // 1024} KB')
