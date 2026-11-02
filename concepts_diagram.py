"""Animated schematics of five geothermal concepts (HTML + canvas + JavaScript), embedded in Streamlit
via components.html. Temperatures come from the user's design; everything else is schematic."""
import json


def build_concepts_html(d: dict) -> str:
    return _HTML.replace("__DATA__", json.dumps(d))


_HTML = r"""
<div id="wrap">
<style>
  :root { --ink:#e7edf7; --mute:#8fa3c2; --line:#2a3a5c; --card:#121b2e; --acc:#6ea8ff; }
  * { box-sizing:border-box; font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif; }
  body { margin:0; background:transparent; }
  #wrap { background:linear-gradient(180deg,#0b1220,#0f1a30); border-radius:16px; padding:14px; color:var(--ink); }
  #tabs { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }
  .tab { background:var(--card); color:var(--mute); border:1px solid var(--line); border-radius:999px; padding:7px 14px;
         font-size:13px; font-weight:600; cursor:pointer; }
  .tab:hover { color:var(--ink); border-color:var(--acc); }
  .tab.on { background:#1d3358; color:#fff; border-color:var(--acc); }
  canvas { width:100%; height:auto; display:block; border-radius:12px; background:#0b1220; }
  #ctl { display:flex; align-items:center; gap:12px; margin:10px 0 4px; color:var(--mute); font-size:12.5px; flex-wrap:wrap; }
  #ctl button { background:var(--card); color:var(--ink); border:1px solid var(--line); border-radius:8px; padding:5px 12px; cursor:pointer; }
  #ctl button:hover { border-color:var(--acc); }
  #chip { margin-left:auto; }
  #info { display:grid; grid-template-columns: 1.3fr 1fr; gap:14px; margin-top:8px; }
  @media (max-width:720px){ #info { grid-template-columns:1fr; } }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; font-size:13px; line-height:1.5; }
  .panel h3 { margin:0 0 6px; font-size:15px; }
  .panel h4 { margin:10px 0 2px; font-size:11.5px; letter-spacing:.06em; text-transform:uppercase; color:var(--mute); }
  .panel ul { margin:2px 0 0 18px; padding:0; }
  .tag { display:inline-block; font-size:11px; padding:1px 8px; border-radius:999px; background:#1d3358; color:#cfe0ff; margin-right:4px; }
</style>
<div id="tabs"></div>
<canvas id="cv"></canvas>
<div id="ctl">
  <button id="pp">Pause</button>
  <label>Speed <input id="spd" type="range" min="0.25" max="3" step="0.25" value="1"></label>
  <span id="chip"></span>
</div>
<div id="info"><div class="panel" id="how"></div><div class="panel" id="when"></div></div>

<script>
const D = __DATA__;
const W = 960, H = 500;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
(function fit(){ const r = window.devicePixelRatio || 1; cv.width = W*r; cv.height = H*r; ctx.setTransform(r,0,0,r,0,0); })();
const lerp = (a,b,t)=>a+(b-a)*t, clamp = (x,a,b)=>Math.max(a,Math.min(b,x));
const FONT = 'Inter, system-ui, sans-serif';
let simT = 0, paused = false, SPEED = 1;

function tcol(T){ const u = clamp((T-D.t_inj)/Math.max(1,D.t_res-D.t_inj),0,1);
  return [Math.round(lerp(76,255,u)), Math.round(lerp(201,90,u)), Math.round(lerp(240,60,u))]; }
const rgb = (c,a=1)=>`rgba(${c[0]},${c[1]},${c[2]},${a})`;
function rng(seed){ return function(){ seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed>>>15, 1|seed);
  t = t + Math.imul(t ^ t>>>7, 61|t) ^ t; return ((t ^ t>>>14)>>>0)/4294967296; }; }

// ---------- flow paths with particles ----------
function mkFlow(o){
  const cum=[0];
  for(let i=1;i<o.pts.length;i++) cum.push(cum[i-1]+Math.hypot(o.pts[i][0]-o.pts[i-1][0], o.pts[i][1]-o.pts[i-1][1]));
  return Object.assign({cum, L:cum[cum.length-1], n:10, speed:90, w:6, grow:0}, o);
}
function at(f,s){ s = clamp(s,0,f.L); let i=1; while(i<f.cum.length-1 && f.cum[i]<s) i++;
  const u=(s-f.cum[i-1])/Math.max(1e-6,f.cum[i]-f.cum[i-1]);
  return [lerp(f.pts[i-1][0],f.pts[i][0],u), lerp(f.pts[i-1][1],f.pts[i][1],u)]; }
function colAt(f,s){ const u=s/f.L;
  if(f.col) return f.col(u);
  const st=f.stops; if(u<=st[0][0]) return tcol(st[0][1]);
  for(let i=1;i<st.length;i++) if(u<=st[i][0]){ const k=(u-st[i-1][0])/Math.max(1e-6,st[i][0]-st[i-1][0]); return tcol(lerp(st[i-1][1],st[i][1],k)); }
  return tcol(st[st.length-1][1]); }
function drawFlow(f, vis=1, particles=true, alpha=1){
  ctx.lineCap='round'; ctx.lineWidth=f.w;
  const end = f.L*vis, step=8;
  for(let s=0;s<end;s+=step){ const a=at(f,s), b=at(f,Math.min(end,s+step+1));
    ctx.strokeStyle=rgb(colAt(f,s+step/2),.38*alpha); ctx.beginPath(); ctx.moveTo(a[0],a[1]); ctx.lineTo(b[0],b[1]); ctx.stroke(); }
  if(!particles || vis<1) return;
  for(let i=0;i<f.n;i++){ const s=((i*f.L/f.n)+simT*f.speed)%f.L, p=at(f,s), c=colAt(f,s);
    const r=f.w*0.42*(1+f.grow*(s/f.L));
    ctx.fillStyle=rgb(c,.9*alpha); ctx.beginPath(); ctx.arc(p[0],p[1],r,0,7); ctx.fill();
    ctx.fillStyle=`rgba(255,255,255,${.5*alpha})`; ctx.beginPath(); ctx.arc(p[0]-r*.25,p[1]-r*.25,r*.35,0,7); ctx.fill(); }
}

// ---------- drawing helpers ----------
function rr(x,y,w,h,r){ ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath(); }
function txt(s,x,y,o={}){ ctx.fillStyle=o.color||'#e7edf7'; ctx.font=`${o.weight||600} ${o.size||13}px ${FONT}`;
  ctx.textAlign=o.align||'center'; ctx.fillText(s,x,y); }
function box(x,y,w,h,title,sub,accent='#2a3a5c'){
  ctx.fillStyle='#121b2e'; rr(x,y,w,h,12); ctx.fill(); ctx.strokeStyle=accent; ctx.lineWidth=1.5; ctx.stroke();
  txt(title,x+w/2,y+(sub?h/2-3:h/2+5)); if(sub) txt(sub,x+w/2,y+h/2+14,{size:11,weight:400,color:'#8fa3c2'}); }
function casing(pts,w=10){ ctx.lineCap='round'; ctx.lineJoin='round'; ctx.strokeStyle='#1a1410'; ctx.lineWidth=w; ctx.beginPath();
  ctx.moveTo(pts[0][0],pts[0][1]); for(let i=1;i<pts.length;i++) ctx.lineTo(pts[i][0],pts[i][1]); ctx.stroke(); }
function glow(x,y,rx,ry,c,a){ ctx.save(); ctx.translate(x,y); ctx.scale(1,ry/rx);
  const g=ctx.createRadialGradient(0,0,0,0,0,rx); g.addColorStop(0,rgb(c,a)); g.addColorStop(1,rgb(c,0));
  ctx.fillStyle=g; ctx.beginPath(); ctx.arc(0,0,rx,0,7); ctx.fill(); ctx.restore(); }
function base(){
  let g=ctx.createLinearGradient(0,0,0,150); g.addColorStop(0,'#0a1328'); g.addColorStop(1,'#17294c');
  ctx.fillStyle=g; ctx.fillRect(0,0,W,150);
  ctx.fillStyle='rgba(180,200,230,.07)';
  for(let i=0;i<3;i++){ const x=((i*370+simT*6)%1200)-120; ctx.beginPath(); ctx.ellipse(x,28+i*24,70,13,0,0,7); ctx.fill(); }
  g=ctx.createLinearGradient(0,150,0,H); g.addColorStop(0,'#2a3a2c'); g.addColorStop(.06,'#3a2f27'); g.addColorStop(.55,'#4a2a22'); g.addColorStop(1,'#7a2a1c');
  ctx.fillStyle=g; ctx.fillRect(0,150,W,H-150);
  ctx.strokeStyle='#4d6b4f'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,150); ctx.lineTo(W,150); ctx.stroke();
  ctx.strokeStyle='#556'; ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(34,150); ctx.lineTo(34,470); ctx.stroke();
  txt('0 m',44,168,{size:11,weight:400,color:'#8fa3c2',align:'left'});
  txt(D.depth.toLocaleString()+' m',44,470,{size:11,weight:400,color:'#8fa3c2',align:'left'});
}
function label(s,x,y,o={}){ txt(s,x,y,Object.assign({size:12,weight:600},o)); }
function sub(s,x,y,o={}){ txt(s,x,y,Object.assign({size:11,weight:400,color:'#8fa3c2'},o)); }

// ---------- concepts ----------
const C = {};

// 1. Hydrothermal doublet
(function(){
  const loop = mkFlow({ pts:[[605,95],[710,95],[710,390],[250,390],[250,95],[355,95]],
    stops:[[0,D.t_inj],[.33,D.t_inj],[.40,D.t_inj],[.68,D.t_res],[1,D.t_res]], n:34, speed:110, w:7 });
  C.doublet = {
    name:'Hydrothermal doublet', tag:'Natural permeability',
    flows:[loop],
    bg(){ const g=ctx.createLinearGradient(0,355,0,425); g.addColorStop(0,'rgba(255,138,92,.55)'); g.addColorStop(1,'rgba(255,61,46,.75)');
      ctx.fillStyle=g; rr(150,355,660,70,12); ctx.fill();
      glow(480,390,280,46,[255,179,71],.35+.15*Math.sin(simT*2));
      label('Permeable aquifer',480,375); sub(D.t_res.toFixed(0)+' °C  ·  k '+D.k+' mD',480,415);
      casing([[250,150],[250,390]]); casing([[710,150],[710,390]]); },
    fg(){ const k=.5+.5*Math.sin(simT*2); glow(710,390,60+20*k,40+10*k,[76,201,240],.28);
      box(355,55,250,80,D.use_case,null); sub(D.mw0.toFixed(1)+' MW at start',480,112);
      label('Production well',226,250,{align:'end'}); sub(D.t_res.toFixed(0)+' °C reservoir',226,266,{align:'end'});
      label('Injection well',734,250,{align:'start'}); sub(D.t_inj.toFixed(0)+' °C return',734,266,{align:'start'}); },
    how:`<h3>Hydrothermal doublet</h3>Hot brine is pumped from a permeable aquifer, its heat is taken at the surface,
      and the cooled water is reinjected a kilometre or so away. The cold front slowly travels from the injector toward the producer.
      <h4>Watch</h4><ul><li>Thermal breakthrough: spacing and flow set how long the producer stays hot</li>
      <li>Flow is limited by permeability times thickness and by pump head</li><li>Scaling and corrosion in saline brines</li></ul>`,
    when:`<span class="tag">Best when</span> a thick, permeable, warm aquifer exists at 1.5-4 km.
      <h4>Examples in the Benchmarks tab</h4><ul><li>Insheim and Landau (Germany, power)</li><li>Paris Basin and Netherlands (heat)</li><li>Munich, Pyrzyce, Aarhus (planned)</li></ul>`
  };
})();

// 2. Enhanced geothermal system
(function(){
  const R=rng(7), fr=[];
  for(let i=0;i<8;i++){ const y0=395, pts=[[338,y0]]; const m=3+Math.floor(R()*2);
    for(let k=1;k<=m;k++) pts.push([lerp(338,622,k/(m+1))+(R()-.5)*26, 345+R()*105]);
    pts.push([622,y0]);
    fr.push(mkFlow({ pts, stops:[[0,D.t_inj],[.3,lerp(D.t_inj,D.t_res,.5)],[1,D.t_res]], n:4, speed:55+R()*30, w:3.2 })); }
  const inj = mkFlow({ pts:[[355,95],[250,95],[250,300],[338,395]], stops:[[0,D.t_inj],[1,D.t_inj]], n:12, speed:90, w:7 });
  const prod = mkFlow({ pts:[[622,395],[710,300],[710,95],[605,95]], stops:[[0,D.t_res],[1,D.t_res]], n:12, speed:90, w:7 });
  const dots=[]; for(let i=0;i<40;i++) dots.push([345+R()*270, 340+R()*115, R()*5]);
  C.egs = {
    name:'Enhanced geothermal (EGS)', tag:'Engineered permeability', flows:[],
    custom(){
      const cyc=simT%17, stim=cyc<6, p=stim?clamp(cyc/4.5,0,1):1;
      ctx.fillStyle='rgba(20,10,8,.45)'; rr(318,325,324,140,14); ctx.fill();
      ctx.strokeStyle='rgba(255,255,255,.05)'; ctx.lineWidth=1; for(let i=0;i<10;i++){ ctx.beginPath(); ctx.moveTo(318,325+i*14); ctx.lineTo(642,325+i*14); ctx.stroke(); }
      glow(480,400,200,60,[255,100,50],.28);
      label('Hot, low-permeability rock',480,482);
      casing(inj.pts,10); casing(prod.pts,10);
      drawFlow(inj,1,true); drawFlow(prod,stim?0:1,!stim,stim?.0:1);
      fr.forEach(f=>{ if(stim){ ctx.save(); ctx.lineWidth=f.w+1.5; drawFlow(f,p,false,1.8); ctx.restore(); } else drawFlow(f,1,true); });
      if(stim){ dots.forEach(d=>{ const ph=((simT*1.4)+d[2])%5; if(ph<.6){ const a=1-ph/.6;
        ctx.strokeStyle=`rgba(255,235,120,${a})`; ctx.lineWidth=1.5; ctx.beginPath(); ctx.arc(d[0],d[1],2+ph*14,0,7); ctx.stroke(); } }); }
      box(355,55,250,80,D.use_case,null); sub(stim?'idle during stimulation':D.mw0.toFixed(1)+' MW at start',480,112);
      label(stim?'1 · Hydraulic stimulation: fractures open, microseismic events':'2 · Circulation: water sweeps the fracture network',480,28,{size:13,color:stim?'#ffd27a':'#7fe3b8'});
      label('Injector',226,230,{align:'end'}); label('Producer',734,230,{align:'start'});
    },
    how:`<h3>Enhanced geothermal system</h3>Where the rock is hot but tight, high-pressure injection opens and shears natural fractures.
      The wells are then joined by a fracture network that acts as the heat exchanger.
      <h4>Watch</h4><ul><li>Induced seismicity: needs monitoring and a traffic-light protocol</li>
      <li>Short-circuiting: one dominant fracture cools the producer early</li><li>Stimulation cost and success are the main uncertainties</li></ul>`,
    when:`<span class="tag">Best when</span> temperature is high but permeability is poor, or a deep granite basement is the target.
      <h4>Examples in the Benchmarks tab</h4><ul><li>Soultz-sous-Forêts and Rittershoffen (France)</li><li>Fervo Project Red and Cape Station (USA)</li><li>Utah FORGE (research)</li></ul>`
  };
})();

// 3. Closed loop
(function(){
  const down = mkFlow({ pts:[[400,95],[300,95],[300,335]], stops:[[0,D.t_inj],[1,D.t_inj]], n:12, speed:80, w:7 });
  const up = mkFlow({ pts:[[660,335],[660,95],[560,95]], stops:[[0,D.t_res*.97],[1,D.t_res*.97]], n:12, speed:80, w:7 });
  const lat=[]; for(let i=0;i<5;i++){ const y=358+i*21;
    lat.push(mkFlow({ pts:[[300,335],[335,y],[625,y],[660,335]], stops:[[0,D.t_inj],[.12,D.t_inj],[.75,D.t_res*.97],[1,D.t_res*.97]], n:6, speed:60, w:4.5 })); }
  C.closed = {
    name:'Closed loop', tag:'No brine produced', flows:[],
    custom(){
      ctx.fillStyle='rgba(120,30,20,.40)'; rr(240,318,480,150,16); ctx.fill();
      glow(480,400,260,90,[255,110,50],.22+.08*Math.sin(simT*1.5));
      label('Hot dry rock: heat conducts in, no fluid exchange',480,488);
      for(let x=360;x<=600;x+=40){ const o=(simT*14+x)%12;
        [[345,-1],[455,1]].forEach(([y0,dir])=>{ ctx.strokeStyle='rgba(255,170,90,.55)'; ctx.lineWidth=2; ctx.beginPath();
          ctx.moveTo(x,y0+dir*(10-o*.5)); ctx.lineTo(x,y0+dir*(4-o*.5)); ctx.stroke(); }); }
      casing(down.pts,10); casing(up.pts,10); lat.forEach(f=>casing(f.pts,7));
      drawFlow(down); drawFlow(up); lat.forEach(f=>drawFlow(f));
      box(400,55,160,80,D.use_case,null); sub(D.mw0.toFixed(1)+' MW (design basis)',480,112);
      label('Cold in',276,230,{align:'end'}); label('Hot out',684,230,{align:'start'});
      label('Sealed multilateral loop',480,28,{size:13,color:'#9ad7ff'});
    },
    how:`<h3>Closed-loop (Eavor-type) system</h3>Working fluid circulates in a sealed U-shaped loop of long horizontal laterals and picks up heat only by conduction through the pipe wall.
      Flow can run by thermosiphon after a start-up pump.
      <h4>Watch</h4><ul><li>Conduction-limited: far less heat per metre of well than a permeable reservoir</li>
      <li>Needs many kilometres of lateral drilling, so cost per MW is the issue</li><li>Removes reservoir, brine, scaling and seismicity risk</li></ul>`,
    when:`<span class="tag">Best when</span> there is hot rock with no permeability or fluid, or permitting rules out producing brine.
      <h4>Examples in the Benchmarks tab</h4><ul><li>Eavor-Loop Geretsried (Germany)</li></ul>`
  };
})();

// 4. Flash steam
(function(){
  const steamC = ()=>[236,243,255], coolC = ()=>[190,205,230];
  const prod = mkFlow({ pts:[[200,395],[200,138],[300,138],[300,112]], col:u=>tcol(lerp(D.t_res,D.t_res*.9,u)), n:22, speed:130, w:8, grow:.8 });
  const steam = mkFlow({ pts:[[335,72],[335,52],[520,52],[520,95],[530,95]], col:steamC, n:12, speed:150, w:5 });
  const exh = mkFlow({ pts:[[560,125],[560,130],[700,130]], col:coolC, n:8, speed:110, w:5 });
  const cond = mkFlow({ pts:[[790,110],[825,110]], col:coolC, n:3, speed:60, w:4 });
  const brine = mkFlow({ pts:[[335,135],[335,147],[760,147],[760,385]], stops:[[0,lerp(D.t_inj,D.t_res,.6)],[1,lerp(D.t_inj,D.t_res,.4)]], n:22, speed:100, w:6 });
  const rech = mkFlow({ pts:[[760,385],[480,398],[200,395]], stops:[[0,lerp(D.t_inj,D.t_res,.4)],[1,D.t_res]], n:14, speed:60, w:5 });
  C.flash = {
    name:'Flash / dry steam', tag:'High enthalpy', flows:[],
    custom(){
      glow(480,478,330,50,[255,150,40],.55+.1*Math.sin(simT*1.7));
      sub('Heat source: magmatic intrusion',480,492,{color:'#ffd9a0'});
      const g=ctx.createLinearGradient(0,350,0,420); g.addColorStop(0,'rgba(255,138,92,.5)'); g.addColorStop(1,'rgba(255,61,46,.7)');
      ctx.fillStyle=g; rr(120,350,760,70,12); ctx.fill(); label('Two-phase reservoir',480,372);
      casing(prod.pts.slice(0,3),10); casing([[760,150],[760,385]],9);
      [rech,prod,brine,steam,exh,cond].forEach(f=>drawFlow(f));
      // separator
      ctx.fillStyle='#121b2e'; rr(300,72,70,64,16); ctx.fill(); ctx.strokeStyle='#2a3a5c'; ctx.lineWidth=1.5; ctx.stroke();
      label('Separator',335,100); sub('steam | brine',335,116);
      // turbine
      ctx.fillStyle='#121b2e'; ctx.beginPath(); ctx.arc(560,95,32,0,7); ctx.fill(); ctx.stroke();
      ctx.save(); ctx.translate(560,95); ctx.rotate(simT*5);
      ctx.strokeStyle='#9ad7ff'; ctx.lineWidth=3; for(let i=0;i<6;i++){ ctx.rotate(Math.PI/3); ctx.beginPath(); ctx.moveTo(4,0); ctx.lineTo(26,0); ctx.stroke(); }
      ctx.restore(); label('Turbine',560,146);
      box(595,78,50,34,'G',null); sub('generator',620,126);
      // condenser + cooling tower
      box(700,72,90,64,'Condenser',null);
      ctx.fillStyle='#1b2740'; ctx.strokeStyle='#2a3a5c'; ctx.beginPath(); ctx.moveTo(830,140); ctx.lineTo(850,70); ctx.lineTo(890,70); ctx.lineTo(910,140); ctx.closePath(); ctx.fill(); ctx.stroke();
      for(let i=0;i<5;i++){ const ph=((simT*.5)+i/5)%1; ctx.fillStyle=`rgba(220,230,245,${.5*(1-ph)})`;
        ctx.beginPath(); ctx.arc(870+Math.sin(ph*6+i)*10,62-ph*45,6+ph*9,0,7); ctx.fill(); }
      label('Cooling tower',870,156,{size:11});
      label('Production well',186,260,{align:'end'}); sub('steam + brine',186,276,{align:'end'});
      label('Reinjection',780,270,{align:'start'}); sub('brine + condensate',780,286,{align:'start'});
      label(D.use_case.startsWith('Power')?'Power plant':'Steam used for power; heat is a by-product',480,28,{size:13,color:'#ffd27a'});
    },
    how:`<h3>Flash and dry-steam power</h3>Very hot fluid flashes to steam as pressure falls up the well. A separator splits steam
      (to the turbine) from brine (back into the ground with the condensate). Output per well is far larger than from a low-temperature doublet.
      <h4>Watch</h4><ul><li>Needs roughly 180 °C or more at depth, in practice a volcanic or high-heat-flow setting</li>
      <li>Non-condensable gases (CO2, H2S) and scaling need treatment</li><li>Reinjection keeps pressure up and manages the resource</li></ul>`,
    when:`<span class="tag">Best when</span> a high-enthalpy field is available; this is the proven large-scale power route.
      <h4>Examples in the Benchmarks tab</h4><ul><li>The Geysers (USA), Larderello (Italy)</li><li>Hellisheiði and Nesjavellir (Iceland)</li><li>Wairakei (NZ), Sarulla (Indonesia), Olkaria (Kenya)</li></ul>`
  };
})();

// 5. District heating network
(function(){
  const Ts = lerp(D.t_inj,D.t_res,.7), Tr = lerp(D.t_inj,D.t_res,.25);
  const geo = mkFlow({ pts:[[150,390],[150,95],[420,95],[420,390],[150,390]],
    stops:[[0,D.t_res],[.38,D.t_res],[.48,D.t_inj],[.76,D.t_inj],[1,D.t_res]], n:34, speed:100, w:7 });
  const sup = mkFlow({ pts:[[370,62],[880,62],[880,102],[370,102]], stops:[[0,Ts],[.46,Ts],[.50,Tr],[1,Tr]], n:30, speed:85, w:5 });
  C.heat = {
    name:'District heating', tag:'Direct use', flows:[],
    custom(){
      const g=ctx.createLinearGradient(0,360,0,420); g.addColorStop(0,'rgba(255,138,92,.5)'); g.addColorStop(1,'rgba(255,61,46,.7)');
      ctx.fillStyle=g; rr(100,360,380,60,12); ctx.fill(); label('Aquifer',290,376); sub(D.t_res.toFixed(0)+' °C',290,412);
      casing([[150,150],[150,390]]); casing([[420,150],[420,390]]);
      drawFlow(geo);
      box(200,50,170,80,'Heat exchanger',null); sub('geothermal side | network side',285,108,{size:10});
      drawFlow(sup);
      for(let i=0;i<5;i++){ const x=470+i*80, k=.5+.5*Math.sin(simT*2+i);
        ctx.strokeStyle=rgb(tcol(Ts),.6); ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(x+22,102); ctx.lineTo(x+22,118); ctx.stroke();
        ctx.fillStyle='#1d2b47'; ctx.fillRect(x,120,44,30);
        ctx.fillStyle='#35496f'; ctx.beginPath(); ctx.moveTo(x-5,120); ctx.lineTo(x+22,102+14); ctx.lineTo(x+49,120); ctx.closePath(); ctx.fill();
        ctx.fillStyle=`rgba(255,200,110,${.45+.4*k})`; ctx.fillRect(x+8,128,10,10); ctx.fillRect(x+26,128,10,10); }
      label('Production',126,250,{align:'end'}); label('Injection',444,250,{align:'start'});
      label('District network',640,30,{size:13,color:'#ffd27a'});
      sub('supply',900,86,{align:'start'}); sub('return',900,106,{align:'start'});
      sub(D.use_case.startsWith('Power')?'Design basis is power; heat shown for comparison':D.mw0.toFixed(1)+' MW delivered at start',640,46);
    },
    how:`<h3>Geothermal district heating</h3>A heat exchanger isolates the corrosive brine from a clean network loop. Supply and return temperatures set
      how much heat each kilogram of brine delivers; a heat pump can lower the return temperature or lift the supply.
      <h4>Watch</h4><ul><li>The load is local: pipe length and heat density drive the economics</li>
      <li>Heat sells for less than power per MWh, so capex per kW is critical</li><li>Seasonal demand, so peak boilers or storage often back it up</li></ul>`,
    when:`<span class="tag">Best when</span> a warm aquifer lies under a city with an existing or plannable heat network.
      <h4>Examples in the Benchmarks tab</h4><ul><li>Paris Basin (54 units) and Netherlands</li><li>Munich (planned 50 MWth), Pyrzyce, Aarhus</li></ul>`
  };
})();

// ---------- UI ----------
const order = ['doublet','egs','closed','flash','heat'];
let cur = 'doublet';
const tabs = document.getElementById('tabs');
order.forEach(k=>{ const b=document.createElement('button'); b.className='tab'; b.textContent=C[k].name; b.dataset.k=k;
  b.onclick=()=>select(k); tabs.appendChild(b); });
function select(k){ cur=k; simT=0; document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.k===k));
  document.getElementById('how').innerHTML=C[k].how; document.getElementById('when').innerHTML=C[k].when; }
document.getElementById('pp').onclick=e=>{ paused=!paused; e.target.textContent=paused?'Play':'Pause'; };
document.getElementById('spd').oninput=e=>{ SPEED=parseFloat(e.target.value); };
document.getElementById('chip').textContent='Your design: '+D.t_res.toFixed(0)+' °C · '+D.depth.toLocaleString()+' m · '+D.flow.toFixed(0)+' kg/s · reinjection '+D.t_inj.toFixed(0)+' °C';
select('doublet');

let last=performance.now();
function frame(now){
  const dt=Math.min(.1,(now-last)/1000); last=now; if(!paused) simT+=dt*SPEED;
  ctx.clearRect(0,0,W,H); base();
  const c=C[cur];
  if(c.custom) c.custom(); else { c.bg(); c.flows.forEach(f=>drawFlow(f)); c.fg(); }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
</div>
"""
