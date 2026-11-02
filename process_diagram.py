"""Animated geothermal process diagram (HTML + CSS + JavaScript canvas/SVG)
rendered inside Streamlit via components.html. Values are injected from the model."""
import json


def build_html(d: dict) -> str:
    data = json.dumps(d)
    return """
<div id="wrap">
<style>
  :root { --bg:#0b1220; --card:#121b2e; --ink:#e7edf7; --mute:#8fa3c2; --hot:#ff5a3c; --warm:#ffb347; --cold:#4cc9f0; --ok:#35d49a; }
  * { box-sizing:border-box; font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif; }
  body { margin:0; background:transparent; }
  #wrap { background:linear-gradient(180deg,#0b1220,#0f1a30); border-radius:16px; padding:14px; color:var(--ink); }
  svg { width:100%; height:auto; display:block; }
  .lbl { fill:var(--ink); font-size:13px; font-weight:600; }
  .sub { fill:var(--mute); font-size:11px; }
  .big { fill:var(--ink); font-size:20px; font-weight:700; }
  .flowH { stroke-dasharray:10 8; animation: dashH 1.1s linear infinite; }
  .flowC { stroke-dasharray:10 8; animation: dashC 1.1s linear infinite; }
  @keyframes dashH { to { stroke-dashoffset:-36; } }
  @keyframes dashC { to { stroke-dashoffset:36; } }
  .pulse { animation: pulse 2.2s ease-in-out infinite; transform-origin:center; transform-box:fill-box; }
  @keyframes pulse { 0%,100%{opacity:.55} 50%{opacity:1} }
  .stage { cursor:pointer; }
  .stage:hover rect.card { stroke:#6ea8ff; }
  #tip { margin-top:8px; font-size:12.5px; color:var(--mute); min-height:34px; }
  #tip b { color:var(--ink); }
</style>
<svg id="svg" viewBox="0 0 960 470" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="earth" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2a3a2c"/><stop offset=".08" stop-color="#3a2f27"/>
      <stop offset=".5" stop-color="#4a2a22"/><stop offset="1" stop-color="#7a2a1c"/>
    </linearGradient>
    <linearGradient id="res" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ff8a5c" stop-opacity=".55"/><stop offset="1" stop-color="#ff3d2e" stop-opacity=".75"/>
    </linearGradient>
    <radialGradient id="glow"><stop offset="0" stop-color="#ffb347" stop-opacity=".7"/><stop offset="1" stop-color="#ffb347" stop-opacity="0"/></radialGradient>
  </defs>

  <!-- sky + ground -->
  <rect x="0" y="0" width="960" height="150" fill="#0d1830"/>
  <rect x="0" y="150" width="960" height="320" fill="url(#earth)"/>
  <line x1="0" y1="150" x2="960" y2="150" stroke="#4d6b4f" stroke-width="3"/>

  <!-- reservoir -->
  <rect id="reservoir" x="150" y="355" width="660" height="70" rx="12" fill="url(#res)"/>
  <ellipse class="pulse" cx="480" cy="390" rx="260" ry="46" fill="url(#glow)"/>
  <text class="lbl" x="480" y="384" text-anchor="middle">Reservoir</text>
  <text class="sub" x="480" y="402" text-anchor="middle" id="resTxt"></text>

  <!-- wells -->
  <path id="prodWell" d="M250 150 L250 380" stroke="#ff5a3c" stroke-width="7" fill="none" opacity=".9"/>
  <path id="injWell"  d="M710 150 L710 380" stroke="#4cc9f0" stroke-width="7" fill="none" opacity=".9"/>
  <path class="flowH" d="M250 380 L250 160" stroke="#ffd2a8" stroke-width="3" fill="none"/>
  <path class="flowC" d="M710 160 L710 380" stroke="#c9f1ff" stroke-width="3" fill="none"/>
  <text class="lbl" x="226" y="270" text-anchor="end">Production well</text>
  <text class="sub" x="226" y="286" text-anchor="end" id="tpTxt"></text>
  <text class="lbl" x="734" y="270">Injection well</text>
  <text class="sub" x="734" y="286" id="tiTxt"></text>

  <!-- thermal front in reservoir -->
  <ellipse id="coldFront" cx="710" cy="390" rx="20" ry="28" fill="#4cc9f0" opacity=".28"/>

  <!-- surface: pump, heat exchanger / ORC, consumer -->
  <g class="stage" data-k="pump">
    <rect class="card" x="640" y="62" width="140" height="62" rx="12" fill="#121b2e" stroke="#2a3a5c"/>
    <text class="lbl" x="710" y="88" text-anchor="middle">Pumps</text>
    <text class="sub" x="710" y="106" text-anchor="middle" id="pumpTxt"></text>
  </g>
  <g class="stage" data-k="plant">
    <rect class="card" x="355" y="40" width="250" height="84" rx="14" fill="#121b2e" stroke="#2a3a5c"/>
    <text class="lbl" x="480" y="66" text-anchor="middle" id="plantName"></text>
    <text class="big" x="480" y="96" text-anchor="middle" id="plantMW"></text>
    <text class="sub" x="480" y="114" text-anchor="middle" id="plantSub"></text>
  </g>
  <g class="stage" data-k="well">
    <rect class="card" x="180" y="62" width="140" height="62" rx="12" fill="#121b2e" stroke="#2a3a5c"/>
    <text class="lbl" x="250" y="88" text-anchor="middle">Wellhead</text>
    <text class="sub" x="250" y="106" text-anchor="middle" id="whTxt"></text>
  </g>
  <g class="stage" data-k="market">
    <rect class="card" x="400" y="-10" width="160" height="0" rx="12" fill="none"/>
  </g>

  <!-- surface piping -->
  <path class="flowH" d="M250 150 L250 124 M320 93 L355 93" stroke="#ff8a5c" stroke-width="4" fill="none"/>
  <path class="flowH" d="M320 93 L355 93" stroke="#ff8a5c" stroke-width="4" fill="none"/>
  <path class="flowC" d="M605 93 L640 93" stroke="#4cc9f0" stroke-width="4" fill="none"/>
  <path class="flowC" d="M710 124 L710 150" stroke="#4cc9f0" stroke-width="4" fill="none"/>

  <!-- consumer -->
  <g id="consumer" transform="translate(790,30)">
    <rect x="0" y="40" width="120" height="70" rx="10" fill="#121b2e" stroke="#2a3a5c"/>
    <text class="lbl" x="60" y="66" text-anchor="middle" id="consName"></text>
    <text class="sub" x="60" y="84" text-anchor="middle" id="consTxt"></text>
    <text class="sub" x="60" y="100" text-anchor="middle" id="consTxt2"></text>
  </g>
  <path d="M605 70 L790 70" stroke="#ffb347" stroke-width="3" fill="none" class="flowH"/>

  <!-- depth ruler -->
  <line x1="40" y1="150" x2="40" y2="425" stroke="#556" stroke-width="1.5"/>
  <text class="sub" x="52" y="168" id="d0">0 m</text>
  <text class="sub" x="52" y="425" id="d1"></text>
  <text class="sub" x="52" y="300" id="gr"></text>

  <!-- stage timeline -->
  <g transform="translate(20,440)">
    <text class="sub" x="0" y="0">Year</text>
    <rect x="40" y="-9" width="800" height="8" rx="4" fill="#1b2a47"/>
    <rect id="yearBar" x="40" y="-9" width="0" height="8" rx="4" fill="#35d49a"/>
    <text class="sub" id="yearTxt" x="850" y="0"></text>
  </g>
</svg>
<div id="tip"><b>Tip:</b> click a stage to see what it does. Animation runs through the project life and updates the produced temperature live.</div>
</div>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id);
$('resTxt').textContent = D.t_res.toFixed(0) + ' °C  ·  ' + D.depth.toLocaleString() + ' m  ·  k ' + D.k + ' mD';
$('d1').textContent = D.depth.toLocaleString() + ' m';
$('gr').textContent = D.grad.toFixed(0) + ' °C/km';
$('plantName').textContent = D.use_case;
$('consName').textContent = D.use_case.startsWith('Power') ? 'Grid' : 'District heat';
$('consTxt').textContent = D.homes.toLocaleString() + (D.use_case.startsWith('Power') ? ' homes (elec.)' : ' homes');
$('consTxt2').textContent = (D.life_gwh).toFixed(0) + ' GWh lifetime';
$('tiTxt').textContent = D.t_inj.toFixed(0) + ' °C  ·  ' + D.flow.toFixed(0) + ' kg/s';

const tips = {
  well:  '<b>Wellhead</b> – produced brine arrives here after losing a few degrees on the way up.',
  plant: '<b>' + D.use_case + '</b> – heat extracted until the brine is cooled down to the reinjection temperature.',
  pump:  '<b>Pumps</b> – ' + D.pump_kw.toFixed(0) + ' kW parasitic load keeps the loop pressurised and the brine moving.',
};
document.querySelectorAll('.stage').forEach(g => g.addEventListener('click', () => { $('tip').innerHTML = tips[g.dataset.k] || ''; }));

function lerp(a,b,t){return a+(b-a)*t}
function colorFor(T){ // map temperature to blue->orange->red
  const t = Math.max(0, Math.min(1, (T - D.t_inj) / (D.t_res - D.t_inj + 1e-6)));
  const r = Math.round(lerp(76,255,t)), g = Math.round(lerp(201,90,t)), b = Math.round(lerp(240,60,t));
  return `rgb(${r},${g},${b})`;
}
let t = 0, last = performance.now();
const T = D.years.length - 1;
function frame(now) {
  const dt = (now - last) / 1000; last = now;
  t = (t + dt * (T / 14)) % T;            // 14 s per project life
  const i = Math.min(T, Math.floor(t));
  const Tp = D.t_prod[i], MW = D.mw[i];
  $('tpTxt').textContent = Tp.toFixed(0) + ' °C';
  $('whTxt').textContent = Tp.toFixed(0) + ' °C';
  $('plantMW').textContent = MW.toFixed(1) + ' MW';
  $('plantSub').textContent = D.use_case.startsWith('Power') ? 'net electric' : 'thermal delivered';
  $('pumpTxt').textContent = D.pump_kw.toFixed(0) + ' kW';
  $('prodWell').setAttribute('stroke', colorFor(Tp));
  const frac = (D.t_res - Tp) / Math.max(1, D.t_res - D.t_inj);
  const rx = 20 + 520 * Math.min(1, t / D.bt_years) * 0.5 + (t > D.bt_years ? 80 : 0);
  $('coldFront').setAttribute('rx', Math.min(rx, 540)); $('coldFront').setAttribute('opacity', (0.22 + 0.5 * Math.min(1, frac*3)).toFixed(2));
  $('coldFront').setAttribute('cx', 710 - Math.min(rx, 540) * 0.55);
  $('yearBar').setAttribute('width', 800 * (t / T));
  $('yearTxt').textContent = 'Year ' + D.years[i].toFixed(0);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
</div>
""".replace("__DATA__", data)
