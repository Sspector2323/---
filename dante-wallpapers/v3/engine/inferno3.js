/* INFERNO III — живые обои-триптих по живописным картам девяти кругов.
 * Картины оживляются шейдером (дым плывёт, кровь и болото рябят, огонь дрожит от жара,
 * крылья Люцифера и головы Цербера двигаются), поверх — частицы и свет.
 * Данте и Вергилий проходят все круги за цикл (по умолчанию 9 минут), три монитора синхронны.
 * Настройки: window.INFERNO_CONFIG или URL: screen=1|2|3|all|auto, cycle (сек), fps, quotes, poets, t (отладка).
 */
(function () {
  "use strict";
  const cfg = Object.assign({ screen: "auto", cycle: 540, fps: 30, quotes: 1, poets: 1 }, window.INFERNO_CONFIG || {});
  const qs = new URLSearchParams(location.search);
  for (const k of ["screen", "cycle", "fps", "t", "quotes", "poets"]) if (qs.has(k)) cfg[k] = qs.get(k);
  cfg.cycle = Math.min(1200, Math.max(120, +cfg.cycle || 540));
  cfg.fps = Math.min(60, Math.max(10, +cfg.fps || 30));
  const on = (v) => !(v === "0" || v === 0 || v === false);
  cfg.quotes = on(cfg.quotes); cfg.poets = on(cfg.poets);
  const BASE = window.INFERNO_ASSETS || "assets/";

  const TAU = Math.PI * 2, OUTRO = 14;
  const WIN_W = 608, WIN_H = 880, TOP = 24, GAP = 24;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const smooth = (t) => t * t * (3 - 2 * t);
  const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
  const noise1 = (x) => { const i = Math.floor(x), f = x - i; const u = f * f * (3 - 2 * f); return lerp(hash(i), hash(i + 1), u); };
  function rngf(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  // ======================================================================
  // ЭФФЕКТЫ ШЕЙДЕРА. Координаты — доли окна (0..1, y вниз).
  //  flow(cx,cy,rx,ry, amp, speed, scale, dx,dy)   — дым/туман/облака текут
  //  ripple(cx,cy,rx,ry, amp, speed, freq)           — рябь воды/крови/грязи
  //  heat(cx,cy,rx,ry, amp, speed, flicker)          — огонь: дрожь от жара + мерцание
  //  glow(cx,cy,r, amp, speed, [r,g,b])              — пульсирующий свет
  //  swing(cx,cy,rx,ry, angle, speed, phase, px,py)  — поворот области вокруг шарнира (крылья, головы)
  //  breath(cx,cy,rx,ry, amp, speed, phase, px,py)   — «дыхание»: масштаб вокруг точки
  //  shift(cx,cy,rx,ry, amp, speed, phase, dx,dy)    — толчки туда-обратно
  // ======================================================================
  const F = (cx, cy, rx, ry, amp, speed, scale, dx, dy) => [1, cx, cy, rx, ry, amp, speed, 0, dx ?? 1, dy ?? 0, scale ?? 6, 0];
  const RIP = (cx, cy, rx, ry, amp, speed, freq) => [2, cx, cy, rx, ry, amp, speed, 0, 0, 0, freq ?? 60, 0];
  const HEAT = (cx, cy, rx, ry, amp, speed, flick) => [3, cx, cy, rx, ry, amp, speed, 0, flick ?? 0.25, 0, 0, 0];
  const GLOW = (cx, cy, r, amp, speed, col, ph) => [4, cx, cy, r, r, amp, speed, ph ?? 0, col[0] / 255, col[1] / 255, col[2] / 255, 0];
  const SW = (cx, cy, rx, ry, ang, speed, ph, px, py) => [5, cx, cy, rx, ry, ang, speed, ph, px, py, 0, 0];
  const BR = (cx, cy, rx, ry, amp, speed, ph, px, py) => [6, cx, cy, rx, ry, amp, speed, ph, px, py, 0, 0];
  const SH = (cx, cy, rx, ry, amp, speed, ph, dx, dy) => [7, cx, cy, rx, ry, amp, speed, ph, dx, dy, 0, 0];

  const SCENES = [
    { // I. ЛИМБ — туман между колоннами, тени бродят
      q: "sanza speme vivemo in disio", qru: "без надежды живём в желании", tint: "190,205,225",
      fx: [F(0.5, 0.82, 0.75, 0.2, 0.010, 0.05, 4, 1, 0), F(0.5, 0.45, 0.45, 0.35, 0.006, 0.03, 3, 1, -0.3), F(0.6, 0.15, 0.4, 0.2, 0.005, 0.025, 3, -1, 0),
        SW(0.66, 0.79, 0.05, 0.11, 0.02, 0.35, 0, 0.66, 0.9), BR(0.18, 0.66, 0.2, 0.08, 0.01, 0.4, 1, 0.18, 0.72),
        GLOW(0.05, 0.63, 0.06, 0.35, 1.1, [255, 70, 40]), GLOW(0.52, 0.72, 0.05, 0.3, 0.9, [255, 70, 40], 2), GLOW(0.94, 0.66, 0.05, 0.3, 1.3, [255, 70, 40], 4),
        GLOW(0.55, 0.3, 0.35, 0.12, 0.25, [170, 200, 225])],
      parts: { ash: 60, fog: ["150,170,190", 0.8, 0.14] },
    },
    { // II. СЛАДОСТРАСТИЕ — вихрь, души несёт ветер, молнии
      q: "Amor, ch'a nullo amato amar perdona", qru: "любовь, что любить велит любимым", tint: "235,210,220",
      fx: [F(0.5, 0.3, 0.75, 0.4, 0.016, 0.12, 3, 1, -0.6), F(0.55, 0.47, 0.6, 0.14, 0.012, 0.35, 7, 1, -0.4), F(0.5, 0.15, 0.6, 0.2, 0.012, 0.18, 4, -1, 0.3),
        BR(0.37, 0.75, 0.16, 0.16, 0.012, 0.6, 0, 0.37, 0.95), SW(0.6, 0.8, 0.12, 0.1, 0.07, 0.5, 1, 0.52, 0.88),
        GLOW(0.62, 0.08, 0.08, 0.45, 1.4, [230, 30, 30]), GLOW(0.84, 0.62, 0.08, 0.45, 1.1, [230, 30, 30], 1), GLOW(0.2, 0.35, 0.06, 0.4, 1.7, [230, 30, 30], 3),
        GLOW(0.3, 0.22, 0.25, 0.18, 0.4, [190, 210, 230])],
      parts: { flakes: 90, streaks: 40, lightning: [0.35, 0.22] },
    },
    { // III. ЧРЕВОУГОДИЕ — ливень, Цербер рвёт грешника
      q: "Cerbero, fiera crudele e diversa", qru: "Цербер, зверь жестокий и чудовищный", tint: "200,210,215",
      fx: [SW(0.76, 0.42, 0.16, 0.12, 0.03, 1.6, 0, 0.6, 0.4), SW(0.6, 0.33, 0.12, 0.08, 0.025, 1.2, 1.5, 0.52, 0.38), SW(0.09, 0.35, 0.1, 0.1, 0.12, 0.9, 0, 0.17, 0.38),
        BR(0.45, 0.4, 0.28, 0.14, 0.01, 0.9, 0, 0.45, 0.5), SW(0.38, 0.78, 0.1, 0.05, 0.05, 0.7, 2, 0.28, 0.8), BR(0.75, 0.75, 0.16, 0.08, 0.012, 0.6, 1, 0.75, 0.8),
        RIP(0.5, 0.86, 0.7, 0.2, 0.0035, 1.2, 70), F(0.6, 0.1, 0.6, 0.15, 0.008, 0.1, 3, -1, 0.2)],
      parts: { rain: 380, splash: 50, lightning: [0.75, 0.05] },
    },
    { // IV. СКУПОСТЬ — грузы толкают навстречу, сыплются обломки и монеты
      q: "mal dare e mal tener lo mondo pulcro ha tolto loro", qru: "худо давали и худо хранили — и потеряли прекрасный мир", tint: "255,215,150",
      fx: [SH(0.24, 0.45, 0.27, 0.28, 0.006, 0.9, 0, 1, 0), SH(0.76, 0.45, 0.27, 0.28, 0.006, 0.9, 0, -1, 0),
        F(0.5, 0.2, 0.5, 0.25, 0.008, 0.1, 3, 0.2, -1), BR(0.75, 0.13, 0.16, 0.15, 0.01, 0.5, 0, 0.75, 0.3),
        GLOW(0.96, 0.22, 0.08, 0.4, 1.0, [220, 40, 20]), GLOW(0.5, 0.42, 0.1, 0.0, 0.0, [255, 210, 150])],
      parts: { debris: [0.5, 0.42], glints: 40, ash: 30 },
    },
    { // V. ГНЕВ — маяк, кровавое болото, драка
      q: "Tristi fummo ne l'aere dolce che dal sol s'allegra", qru: "угрюмы были мы в сладком воздухе, что радуется солнцу", tint: "255,150,140",
      fx: [GLOW(0.48, 0.075, 0.07, 0.9, 2.2, [255, 40, 30]), F(0.5, 0.3, 0.65, 0.25, 0.010, 0.08, 3, 1, -0.2),
        RIP(0.5, 0.78, 0.7, 0.3, 0.004, 1.0, 50), F(0.5, 0.85, 0.6, 0.2, 0.006, 0.15, 5, 1, 0),
        SW(0.3, 0.52, 0.07, 0.06, 0.06, 1.4, 0, 0.33, 0.58), SW(0.47, 0.55, 0.08, 0.06, 0.05, 1.1, 2, 0.47, 0.6), SW(0.65, 0.56, 0.08, 0.07, 0.05, 1.3, 1, 0.62, 0.62),
        BR(0.5, 0.63, 0.32, 0.12, 0.01, 0.9, 0, 0.5, 0.72), GLOW(0.38, 0.82, 0.04, 0.5, 0.7, [255, 30, 20]), GLOW(0.62, 0.83, 0.04, 0.5, 0.9, [255, 30, 20], 2)],
      parts: { embers: 50, bubbles: 40, beam: [0.48, 0.075] },
    },
    { // VI. ЕРЕСЬ — горящие гробницы
      q: "Qui son li eresiarche con lor seguaci", qru: "здесь ересиархи со своими последователями", tint: "255,170,110",
      fx: [HEAT(0.42, 0.47, 0.07, 0.06, 0.007, 2.2, 0.35), HEAT(0.73, 0.62, 0.08, 0.07, 0.007, 2.0, 0.35), HEAT(0.3, 0.63, 0.08, 0.07, 0.007, 2.4, 0.35),
        HEAT(0.62, 0.84, 0.13, 0.12, 0.009, 1.8, 0.4), HEAT(0.27, 0.84, 0.12, 0.12, 0.009, 2.1, 0.4), HEAT(0.88, 0.45, 0.07, 0.06, 0.006, 2.3, 0.3), HEAT(0.2, 0.44, 0.06, 0.05, 0.006, 2.5, 0.3),
        HEAT(0.5, 0.32, 0.5, 0.06, 0.004, 1.5, 0.25), F(0.5, 0.14, 0.6, 0.18, 0.012, 0.09, 3, 1, -0.4),
        SW(0.68, 0.88, 0.06, 0.06, 0.06, 1.5, 0, 0.66, 0.93), SW(0.31, 0.83, 0.07, 0.05, 0.05, 1.3, 1, 0.33, 0.87)],
      parts: { embers: 140, smoke: true },
    },
    { // VII. НАСИЛИЕ — кровавая река, гарпии, огненный дождь
      q: "Uomini fummo, e or siam fatti sterpi", qru: "мы были людьми, а стали терновником", tint: "255,160,110",
      fx: [RIP(0.45, 0.21, 0.55, 0.07, 0.004, 1.3, 90), F(0.45, 0.21, 0.5, 0.06, 0.004, 0.2, 8, 1, 0),
        SW(0.07, 0.34, 0.09, 0.08, 0.10, 2.2, 0, 0.12, 0.38), SW(0.9, 0.32, 0.1, 0.08, -0.10, 2.0, 1, 0.84, 0.38),
        SW(0.12, 0.06, 0.07, 0.04, 0.02, 0.5, 0, 0.06, 0.07), F(0.5, 0.68, 0.7, 0.08, 0.010, 0.12, 3, 1, 0), F(0.5, 0.05, 0.6, 0.08, 0.008, 0.08, 3, 1, 0),
        HEAT(0.6, 0.93, 0.08, 0.05, 0.006, 2.0, 0.4), HEAT(0.42, 0.92, 0.05, 0.04, 0.005, 2.3, 0.4), HEAT(0.02, 0.85, 0.05, 0.05, 0.005, 2.1, 0.4), GLOW(0.3, 0.21, 0.2, 0.25, 0.8, [255, 50, 30])],
      parts: { meteors: 22, embers: 40, arrows: [[0.13, 0.06, 1], [0.9, 0.06, -1]] },
    },
    { // VIII. ЗЛЫЕ ЩЕЛИ — смола, змеи, бичи бесов
      q: "Luogo è in inferno detto Malebolge", qru: "есть место в аду, зовущееся Злые Щели", tint: "215,190,240",
      fx: [F(0.85, 0.68, 0.14, 0.13, 0.006, 0.6, 22, 1, 1), SW(0.85, 0.7, 0.13, 0.12, 0.025, 1.4, 0, 0.85, 0.78),
        RIP(0.73, 0.43, 0.12, 0.04, 0.003, 1.5, 120), RIP(0.18, 0.95, 0.22, 0.06, 0.004, 1.2, 80),
        SW(0.2, 0.15, 0.06, 0.06, 0.12, 2.4, 0, 0.23, 0.2), SW(0.36, 0.21, 0.06, 0.05, 0.10, 2.0, 1, 0.37, 0.27),
        HEAT(0.06, 0.62, 0.06, 0.08, 0.005, 2.0, 0.35), HEAT(0.42, 0.52, 0.05, 0.06, 0.005, 2.3, 0.35), GLOW(0.06, 0.6, 0.08, 0.4, 1.3, [255, 120, 40]),
        F(0.5, 0.05, 0.6, 0.1, 0.008, 0.08, 3, 1, 0), BR(0.37, 0.56, 0.16, 0.1, 0.008, 0.5, 0, 0.37, 0.64)],
      parts: { embers: 60, ash: 20 },
    },
    { // IX. ПРЕДАТЕЛЬСТВО — Люцифер машет крыльями во льду
      q: "Lo 'mperador del doloroso regno", qru: "владыка скорбного царства", tint: "190,225,245",
      fx: [SW(0.25, 0.28, 0.3, 0.3, 0.045, 0.55, 0, 0.38, 0.43), SW(0.75, 0.28, 0.3, 0.3, -0.045, 0.55, 0, 0.62, 0.43),
        BR(0.5, 0.5, 0.2, 0.13, 0.01, 0.55, 0.8, 0.5, 0.62), SW(0.5, 0.4, 0.05, 0.04, 0.03, 1.4, 0, 0.5, 0.37),
        F(0.5, 0.62, 0.7, 0.07, 0.008, 0.15, 4, 1, 0), F(0.5, 0.85, 0.6, 0.15, 0.004, 0.05, 6, 1, 0),
        GLOW(0.5, 0.38, 0.03, 0.5, 1.2, [255, 40, 30]), GLOW(0.5, 0.67, 0.1, 0.3, 0.5, [200, 30, 30])],
      parts: { snow: 220, breath: [[0.43, 0.43], [0.5, 0.42], [0.57, 0.43]] },
    },
  ];

  // ======================================================================
  // WebGL: картины + эффекты
  // ======================================================================
  const glc = document.getElementById("gl"), fxc = document.getElementById("fx");
  const ctx = fxc.getContext("2d");
  const gl = glc.getContext("webgl2", { premultipliedAlpha: false, antialias: false }) || null;
  const MAXFX = 16;
  const VS = `#version 300 es
in vec2 p; out vec2 vUv; void main(){ vUv = vec2(p.x*0.5+0.5, 0.5-p.y*0.5); gl_Position = vec4(p,0.,1.); }`;
  const FS = `#version 300 es
precision highp float;
in vec2 vUv; out vec4 o;
uniform sampler2D tex; uniform float t, aspect, dim, flash, archR, archH;
uniform int n; uniform vec4 A[${MAXFX}], B[${MAXFX}], Cc[${MAXFX}];
float h(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }
float vn(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(h(i),h(i+vec2(1,0)),f.x), mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float s=0., a=.5; for(int i=0;i<4;i++){ s+=a*vn(p); p*=2.03; a*=.5; } return s; }
float msk(vec2 uv, vec4 a, vec4 b){ vec2 d=(uv-a.yz)/vec2(a.w,b.x); return 1.-smoothstep(.45,1.,length(d)); }
void main(){
  vec2 uv0 = vUv;
  // стрельчатая арка: всё вне её прозрачно
  float ax = (uv0.x-.5)*aspect, ay = uv0.y*1.0;
  if (ay < archH) { float cxl = -.5*aspect + archR, cxr = .5*aspect - archR;
    float yl = archH - sqrt(max(archR*archR-(ax-cxl)*(ax-cxl),0.)), yr = archH - sqrt(max(archR*archR-(ax-cxr)*(ax-cxr),0.));
    if (ay < (ax<0.? yl: yr)) discard; }
  // медленный «дрейф камеры»
  vec2 uv = .5 + (uv0-.5)*.965 + vec2(sin(t*.043), cos(t*.031))*.008;
  vec2 d = vec2(0.); vec3 add = vec3(0.); float br = 1.;
  for (int i=0;i<${MAXFX};i++){ if(i>=n) break;
    vec4 a=A[i], b=B[i], c=Cc[i]; int ty=int(a.x+.5); float m=msk(uv,a,b);
    if (m<=0.001 && ty!=4) continue;
    float amp=b.y, sp=b.z, ph=b.w;
    if (ty==1){ vec2 q=uv*c.z + c.xy*t*sp; d += (vec2(fbm(q), fbm(q+vec2(5.2,1.3)))-.5)*amp*m*2.; }
    else if (ty==2){ d.x += sin(uv.y*c.z + t*sp*6. + fbm(uv*8.)*4.)*amp*m; d.y += cos(uv.x*c.z*.6 + t*sp*4.)*amp*.5*m; }
    else if (ty==3){ vec2 q=vec2(uv.x*28., uv.y*12. + t*sp*3.); d += (vec2(fbm(q), fbm(q+3.1))-.5)*amp*m*2.;
      br += m*c.x*(fbm(vec2(t*sp*2.5, a.y*40.))-.45)*2.; }
    else if (ty==4){ float r=length((uv-a.yz)*vec2(aspect,1.))/a.w; float g=exp(-r*r*1.6)*(.75+.25*sin(t*sp+ph)+.12*(vn(vec2(t*sp*2.,ph))-.5)); add += c.xyz*g*amp; }
    else if (ty==5){ float an=amp*sin(t*sp+ph)*m; vec2 p=(uv-c.xy)*vec2(aspect,1.); vec2 r=vec2(p.x*cos(an)-p.y*sin(an), p.x*sin(an)+p.y*cos(an)); d += (r-p)/vec2(aspect,1.); }
    else if (ty==6){ d -= (uv-c.xy)*amp*sin(t*sp+ph)*m; }
    else if (ty==7){ float s=sin(t*sp+ph); d += c.xy*amp*sign(s)*pow(abs(s),.6)*m; }
  }
  vec3 col = texture(tex, clamp(uv+d, .001, .999)).rgb;
  col *= br;
  col = 1.-(1.-col)*(1.-add);          // свет — «экраном», не выжигает
  col += flash*vec3(.8,.85,1.)*(.35+.65*col);
  // виньетка, зерно, приглушение неактивных окон
  vec2 vv = uv0-.5; col *= 1.-.55*pow(clamp(length(vv*vec2(1.,.85))*1.25,0.,1.),2.2);
  col += (h(uv0*vec2(1213.,917.)+fract(t*7.))-.5)*.035;
  col *= dim;
  o = vec4(col,1.);
}`;
  let prog, locs = {}, textures = [], quad;
  function initGL() {
    if (!gl) return false;
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return null; } return s; };
    const v = sh(gl.VERTEX_SHADER, VS), f = sh(gl.FRAGMENT_SHADER, FS);
    if (!v || !f) return false;
    prog = gl.createProgram(); gl.attachShader(prog, v); gl.attachShader(prog, f); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { console.error(gl.getProgramInfoLog(prog)); return false; }
    for (const u of ["tex", "t", "aspect", "dim", "flash", "archR", "archH", "n", "A", "B", "Cc"]) locs[u] = gl.getUniformLocation(prog, u);
    quad = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const lp = gl.getAttribLocation(prog, "p"); gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 2, gl.FLOAT, false, 0, 0);
    return true;
  }
  function uploadTex(img) {
    const tx = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tx);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return tx;
  }
  const packed = SCENES.map((s) => {
    const A = new Float32Array(MAXFX * 4), B = new Float32Array(MAXFX * 4), Cc = new Float32Array(MAXFX * 4);
    s.fx.slice(0, MAXFX).forEach((e, i) => { A.set(e.slice(0, 4), i * 4); B.set(e.slice(4, 8), i * 4); Cc.set(e.slice(8, 12), i * 4); });
    return { A, B, Cc, n: Math.min(MAXFX, s.fx.length) };
  });
  const ARCH_R = 0.62 * WIN_W, ARCH_H = Math.sqrt(ARCH_R ** 2 - (ARCH_R - WIN_W / 2) ** 2);

  function drawGLWindow(idx, rect, t, dim, flash) {
    const [x, y, w, h] = rect; // в пикселях устройства, y от верха
    gl.viewport(x, glc.height - y - h, w, h);
    gl.useProgram(prog);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, textures[idx]);
    gl.uniform1i(locs.tex, 0); gl.uniform1f(locs.t, t); gl.uniform1f(locs.aspect, WIN_W / WIN_H);
    gl.uniform1f(locs.dim, dim); gl.uniform1f(locs.flash, flash);
    gl.uniform1f(locs.archR, ARCH_R / WIN_H); gl.uniform1f(locs.archH, ARCH_H / WIN_H);
    const P = packed[idx];
    gl.uniform1i(locs.n, P.n); gl.uniform4fv(locs.A, P.A); gl.uniform4fv(locs.B, P.B); gl.uniform4fv(locs.Cc, P.Cc);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  // ======================================================================
  // 2D: частицы, свет, поэты, рама
  // ======================================================================
  const spriteCache = {};
  function glowSprite(rgb) {
    if (spriteCache[rgb]) return spriteCache[rgb];
    const c = document.createElement("canvas"); c.width = c.height = 128;
    const x = c.getContext("2d"), g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, `rgba(${rgb},1)`); g.addColorStop(0.22, `rgba(${rgb},0.5)`); g.addColorStop(0.55, `rgba(${rgb},0.12)`); g.addColorStop(1, `rgba(${rgb},0)`);
    x.fillStyle = g; x.fillRect(0, 0, 128, 128);
    return (spriteCache[rgb] = c);
  }
  function glow(c, x, y, r, rgb, a) {
    if (a <= 0.003) return;
    c.globalAlpha = Math.min(1, a); c.drawImage(glowSprite(rgb), x - r, y - r, r * 2, r * 2); c.globalAlpha = 1;
  }
  let smokeTex;
  function makeSmoke() {
    const c = document.createElement("canvas"); c.width = 256; c.height = 256;
    const x = c.getContext("2d"); x.filter = "blur(14px)"; const r = rngf(5);
    for (let i = 0; i < 26; i++) { x.fillStyle = `rgba(255,255,255,${0.05 + r() * 0.08})`; x.beginPath(); x.arc(70 + r() * 116, 70 + r() * 116, 18 + r() * 40, 0, TAU); x.fill(); }
    smokeTex = c;
  }

  function initParts(sc, r) {
    const P = sc.parts, W = WIN_W, H = WIN_H, st = {};
    if (P.ash) st.ash = Array.from({ length: P.ash }, () => ({ x: r() * W, y: r() * H, s: r(), ph: r() * TAU }));
    if (P.flakes) st.flakes = Array.from({ length: P.flakes }, () => ({ a: r() * TAU, rr: r(), y: r(), s: r() }));
    if (P.streaks) st.streaks = Array.from({ length: P.streaks }, () => ({ y: r(), ph: r() * TAU, l: 0.3 + r() * 0.6, s: r() }));
    if (P.rain) st.rain = Array.from({ length: P.rain }, () => ({ x: r() * (W + 200), y: r(), z: r() }));
    if (P.splash) st.splash = Array.from({ length: P.splash }, () => ({ x: r() * W, y: H * (0.6 + r() * 0.4), ph: r() }));
    if (P.glints) st.glints = Array.from({ length: P.glints }, () => ({ x: r() * W, y: H * (0.72 + r() * 0.28), ph: r() * TAU, s: r() }));
    if (P.embers) st.embers = Array.from({ length: P.embers }, () => ({ x: r() * W, y: r(), s: r(), ph: r() * TAU }));
    if (P.bubbles) st.bubbles = Array.from({ length: P.bubbles }, () => ({ x: W * (0.1 + r() * 0.8), y: H * (0.62 + r() * 0.34), ph: r() }));
    if (P.meteors) st.meteors = Array.from({ length: P.meteors }, () => ({ x: r() * (W + 200), ph: r(), s: r() }));
    if (P.snow) st.snow = Array.from({ length: P.snow }, () => ({ x: r(), y: r() * H, s: r() }));
    if (P.debris) st.debris = Array.from({ length: 40 }, () => ({ a: -Math.PI * (0.1 + r() * 0.8), v: 40 + r() * 120, s: r(), coin: r() < 0.35 }));
    return st;
  }

  function drawParts(c, sc, st, t, wi) {
    const P = sc.parts, W = WIN_W, H = WIN_H;
    c.globalCompositeOperation = "lighter";
    if (P.fog) { // ползущий туман
      const [rgb, y, a] = P.fog;
      for (let k = 0; k < 7; k++) { const x = ((k * 140 + t * (6 + k)) % (W + 300)) - 150; c.globalAlpha = a; c.drawImage(tintSmoke(rgb), x - 120, H * y - 80 + Math.sin(t * 0.2 + k) * 20, 320, 180); }
      c.globalAlpha = 1;
    }
    if (st.ash) for (const p of st.ash) { const y = ((p.y - t * (3 + p.s * 5)) % H + H) % H; glow(c, p.x + Math.sin(t * 0.3 + p.ph) * 14, y, 2 + p.s * 3, sc.tint, 0.35); }
    if (P.lightning) { // молния: вспышка + разряд
      const L = noise1(t * 0.35 + wi * 7.3);
      st.flash = L > 0.84 ? (L - 0.84) * 6 : 0;
      if (st.flash > 0.05) {
        const seed = Math.floor(t * 0.35 + wi * 7.3);
        c.strokeStyle = `rgba(230,240,255,${clamp(st.flash, 0, 1)})`; c.lineWidth = 2.2; c.shadowColor = "rgba(200,220,255,1)"; c.shadowBlur = 14;
        c.beginPath(); let x = W * (P.lightning[0] + (hash(seed) - 0.5) * 0.4), y = 0; c.moveTo(x, y);
        for (let i = 0; i < 14; i++) { x += (hash(seed * 13 + i) - 0.5) * 46; y += H * 0.025 + hash(seed + i * 3) * 12; c.lineTo(x, y); }
        c.stroke(); c.shadowBlur = 0;
        glow(c, x, y * 0.5, 260, "200,215,255", st.flash * 0.5);
      }
    }
    if (st.streaks) { c.lineCap = "round"; for (const s of st.streaks) { const y = H * (0.2 + s.y * 0.5) + Math.sin(t * 0.4 + s.ph) * 30, x = ((t * (80 + s.s * 140) + s.ph * 200) % (W + 400)) - 200; c.strokeStyle = "rgba(220,225,235,0.10)"; c.lineWidth = 1.2 + s.s * 2; c.beginPath(); c.moveTo(x, y); c.quadraticCurveTo(x + 80 * s.l, y - 30 * s.l, x + 200 * s.l, y - 10 * s.l); c.stroke(); } }
    c.globalCompositeOperation = "source-over";
    if (st.flakes) { c.fillStyle = "rgba(8,6,8,0.85)"; for (const f of st.flakes) { const a = f.a + t * (0.5 + f.s * 0.6), R = W * (0.2 + f.rr * 0.45), cx = W * 0.5, cy = H * (0.25 + f.y * 0.4); const x = cx + Math.cos(a) * R, y = cy + Math.sin(a) * R * 0.35 - ((t * 10 * f.s) % 80); c.save(); c.translate(x, y); c.rotate(a * 3); c.fillRect(-2 - f.s * 3, -1, 4 + f.s * 6, 2.2); c.restore(); } }
    if (st.rain) {
      c.lineCap = "round";
      for (const [z0, al, lw, len] of [[0.35, 0.16, 1, 16], [0.7, 0.24, 1.3, 26], [1.0, 0.34, 1.7, 40]]) {
        c.strokeStyle = `rgba(200,212,220,${al})`; c.lineWidth = lw; c.beginPath();
        for (const d of st.rain) { if (d.z > z0 || d.z < z0 - 0.35) continue; const y = ((d.y + t * (0.9 + z0 * 0.9)) % 1) * (H + 80) - 40, x = d.x - y * 0.18 - 60; c.moveTo(x, y); c.lineTo(x - len * 0.18, y + len); }
        c.stroke();
      }
      for (const s of st.splash) { const p = (t * 1.7 + s.ph) % 1; c.strokeStyle = `rgba(210,220,225,${0.4 * (1 - p)})`; c.lineWidth = 1; c.beginPath(); c.ellipse(s.x, s.y, 2 + p * 10, 0.8 + p * 3, 0, 0, TAU); c.stroke(); }
    }
    c.globalCompositeOperation = "lighter";
    if (st.glints) for (const g of st.glints) { const a = Math.max(0, Math.sin(t * (0.8 + g.s) + g.ph)) ** 12; if (a > 0.02) { glow(c, g.x, g.y, 6 + g.s * 6, "255,225,140", a); c.fillStyle = `rgba(255,250,220,${a})`; c.fillRect(g.x - 7 * a, g.y - 0.5, 14 * a, 1); c.fillRect(g.x - 0.5, g.y - 7 * a, 1, 14 * a); } }
    if (st.debris) { // удар грузов: летят каменная крошка и монеты
      const ph = (t / 6) % 1, [ux, uy] = P.debris;
      if (ph < 0.06) glow(c, ux * W, uy * H, 120, "255,210,150", (1 - ph / 0.06) * 0.6);
      if (ph < 0.6) for (const d of st.debris) { const tt = ph * 6, x = ux * W + Math.cos(d.a) * d.v * tt, y = uy * H + Math.sin(d.a) * d.v * tt + 90 * tt * tt;
        if (d.coin) glow(c, x, y, 4, "255,210,110", 1 - ph / 0.6); else { c.globalCompositeOperation = "source-over"; c.fillStyle = `rgba(20,16,12,${1 - ph / 0.6})`; c.fillRect(x, y, 2 + d.s * 4, 2 + d.s * 3); c.globalCompositeOperation = "lighter"; } }
    }
    if (st.embers) for (const e of st.embers) { const p = (e.y + t * 0.035 * (0.5 + e.s)) % 1, y = H * (1 - p), x = e.x + Math.sin(t * 0.9 + e.ph) * 18 * p; glow(c, x, y, 2.5 + e.s * 3.5, "255,150,60", 0.9 * Math.sin(p * Math.PI)); }
    if (P.smoke) for (let k = 0; k < 5; k++) { const p = (t * 0.02 + k / 5) % 1; c.globalCompositeOperation = "source-over"; c.globalAlpha = 0.18 * Math.sin(p * Math.PI); c.drawImage(tintSmoke("40,28,24"), W * (0.1 + 0.2 * k) - 100, H * (0.5 - p * 0.45) - 100, 260, 220); c.globalAlpha = 1; c.globalCompositeOperation = "lighter"; }
    if (st.bubbles) for (const b of st.bubbles) { const p = (t * 0.35 + b.ph) % 1; c.strokeStyle = `rgba(255,120,110,${0.45 * (1 - p)})`; c.lineWidth = 1; c.beginPath(); c.ellipse(b.x, b.y, 2 + p * 9, 0.8 + p * 2.4, 0, 0, TAU); c.stroke(); }
    if (P.beam) { // вращающийся луч маяка
      const [bx, by] = P.beam, a = t * 0.6, X = bx * W, Y = by * H;
      for (const dir of [0, Math.PI]) {
        const ang = a + dir, s = Math.cos(ang);
        if (s < -0.2) continue;
        const len = 700, spread = 0.09, k = 0.12 * clamp(s + 0.2, 0, 1);
        const g = c.createRadialGradient(X, Y, 0, X, Y, len); g.addColorStop(0, `rgba(255,60,40,${k * 2})`); g.addColorStop(1, "rgba(255,40,30,0)");
        c.fillStyle = g; c.beginPath(); c.moveTo(X, Y); c.lineTo(X + Math.cos(ang - spread) * len * Math.sign(Math.sin(ang) + 2), Y + Math.sin(ang - spread) * len * 0.25); c.lineTo(X + Math.cos(ang + spread) * len, Y + Math.sin(ang + spread) * len * 0.25); c.closePath(); c.fill();
      }
      glow(c, X, Y, 60, "255,70,50", 0.6 + 0.3 * Math.sin(t * 2.2));
    }
    if (st.meteors) { // огненный дождь — «как снег в Альпах без ветра»
      c.lineCap = "round";
      for (const m of st.meteors) {
        const p = (t * 0.09 * (0.6 + m.s) + m.ph) % 1, y = H * (0.55 + p * 0.5), x = m.x - p * 140 - 60;
        const g = c.createLinearGradient(x + 26, y - 50, x, y); g.addColorStop(0, "rgba(255,120,30,0)"); g.addColorStop(1, "rgba(255,200,110,0.9)");
        c.strokeStyle = g; c.lineWidth = 2 + m.s * 3; c.beginPath(); c.moveTo(x + 26, y - 50); c.lineTo(x, y); c.stroke();
        glow(c, x, y, 8 + m.s * 8, "255,170,70", 0.9);
        if (p > 0.92) glow(c, x, y, 30, "255,120,40", (p - 0.92) * 10);
      }
    }
    if (P.arrows) for (const [ax, ay, dir] of P.arrows) { // стрелы кентавров в реку
      const ph = (t * 0.22 + (dir > 0 ? 0 : 0.5)) % 1;
      if (ph < 0.35) { const k = ph / 0.35, x0 = ax * W, y0 = ay * H, x1 = W * (dir > 0 ? 0.55 : 0.38), y1 = H * 0.21;
        const x = lerp(x0, x1, k), y = lerp(y0, y1, k) - Math.sin(k * Math.PI) * 40, ang = Math.atan2(y1 - y0 - Math.cos(k * Math.PI) * 40 * Math.PI, x1 - x0);
        c.strokeStyle = "rgba(255,220,180,0.9)"; c.lineWidth = 1.6; c.beginPath(); c.moveTo(x, y); c.lineTo(x - Math.cos(ang) * 22, y - Math.sin(ang) * 22); c.stroke(); glow(c, x, y, 5, "255,200,150", 0.7); }
      else if (ph < 0.45) glow(c, W * (dir > 0 ? 0.55 : 0.38), H * 0.21, 20, "255,80,60", (0.45 - ph) * 8);
    }
    if (st.snow) { c.strokeStyle = "rgba(225,240,255,0.35)"; c.lineWidth = 1; c.beginPath(); const gust = 0.6 + 0.4 * Math.sin(t * 0.55); for (const s of st.snow) { const x = ((s.x + t * 0.04 * (0.5 + s.s) * (0.5 + gust)) % 1) * (W + 60) - 30, y = s.y + Math.sin(t * 0.8 + s.s * 20) * 10; c.moveTo(x, y); c.lineTo(x + 3 + s.s * 10 * gust, y + 0.6); } c.stroke();
      for (const s of st.snow) if (s.s > 0.85) { const x = ((s.x + t * 0.03) % 1) * W, y = s.y; glow(c, x, y, 3, "230,245,255", 0.5); } }
    if (P.breath) for (const [bx, by] of P.breath) for (let k = 0; k < 3; k++) { const p = (t * 0.25 + k / 3 + bx) % 1; c.globalCompositeOperation = "source-over"; c.globalAlpha = 0.22 * Math.sin(p * Math.PI); c.drawImage(tintSmoke("200,225,240"), bx * W - 30 - p * 20 + (bx - 0.5) * p * 120, by * H + p * 30 - 30, 60 + p * 90, 50 + p * 60); c.globalAlpha = 1; c.globalCompositeOperation = "lighter"; }
    c.globalCompositeOperation = "source-over"; c.globalAlpha = 1;
  }
  const smokeTints = {};
  function tintSmoke(rgb) {
    if (smokeTints[rgb]) return smokeTints[rgb];
    const c = document.createElement("canvas"); c.width = c.height = 256; const x = c.getContext("2d");
    x.drawImage(smokeTex, 0, 0); x.globalCompositeOperation = "source-in"; x.fillStyle = `rgb(${rgb})`; x.fillRect(0, 0, 256, 256);
    return (smokeTints[rgb] = c);
  }

  // Поэты — тёмные силуэты в плащах с тёплым ореолом (под живопись)
  function poet(c, x, y, h, ph, who) {
    c.save(); c.translate(x, y - Math.abs(Math.sin(ph)) * h * 0.02); const k = h / 100; c.scale(k, k);
    c.globalCompositeOperation = "lighter"; glow(c, 0, -50, 70, "255,200,140", 0.35); c.globalCompositeOperation = "source-over";
    const robe = who === "dante" ? "#3a0a0c" : "#14161c", rim = who === "dante" ? "rgba(255,120,90,0.9)" : "rgba(220,225,240,0.75)";
    const sw = Math.sin(ph) * 5;
    const draw = (col, dx, dy) => {
      c.fillStyle = col; c.beginPath(); c.moveTo(-9 + dx, -78 + dy);
      c.bezierCurveTo(-15 + dx, -50 + dy, -18 + sw * 0.4 + dx, -20 + dy, -20 + sw + dx, dy); c.lineTo(20 + sw + dx, dy);
      c.bezierCurveTo(18 + sw * 0.4 + dx, -20 + dy, 15 + dx, -50 + dy, 10 + dx, -78 + dy); c.closePath(); c.fill();
      c.beginPath(); c.ellipse(1 + dx, -87 + dy, 8, 9.5, 0, 0, TAU); c.fill();
      if (who === "dante") { c.beginPath(); c.moveTo(-9 + dx, -86 + dy); c.quadraticCurveTo(-4 + dx, -103 + dy, 9 + dx, -97 + dy); c.lineTo(11 + dx, -90 + dy); c.closePath(); c.fill(); }
    };
    draw(rim, 1.5, -2); draw(robe, 0, 0);
    if (who !== "dante") { c.strokeStyle = "rgba(150,200,120,0.9)"; c.lineWidth = 2; c.beginPath(); c.arc(1, -89, 9, Math.PI, TAU); c.stroke(); }
    c.restore();
  }

  // ======================================================================
  const IM = {}; let DPR = 1, CW = 0, CH = 0, panels = [], mode = String(cfg.screen), ready = false, glOK = false;
  const states = SCENES.map((s, i) => initParts(s, rngf(100 + i)));

  function archPath(c, i) {
    const x0 = GAP + i * (WIN_W + GAP), w = WIN_W, r = ARCH_R, ys = TOP + ARCH_H;
    c.beginPath(); c.moveTo(x0, TOP + WIN_H);
    for (let k = 0; k <= 40; k++) { const x = x0 + (k / 40) * w / 2; c.lineTo(x, ys - Math.sqrt(Math.max(0, r * r - (x - (x0 + r)) ** 2))); }
    for (let k = 0; k <= 40; k++) { const x = x0 + w / 2 + (k / 40) * w / 2; c.lineTo(x, ys - Math.sqrt(Math.max(0, r * r - (x - (x0 + w - r)) ** 2))); }
    c.lineTo(x0 + w, TOP + WIN_H); c.closePath();
  }
  function layout() {
    DPR = Math.min(2, window.devicePixelRatio || 1); CW = window.innerWidth; CH = window.innerHeight;
    for (const cv of [glc, fxc]) { cv.width = Math.round(CW * DPR); cv.height = Math.round(CH * DPR); cv.style.width = CW + "px"; cv.style.height = CH + "px"; }
    panels = [];
    const wide = mode === "all" || (mode === "auto" && CW / CH > 4), n = wide ? 3 : 1, pw = CW / n;
    for (let g = 0; g < n; g++) { const s = Math.min(pw / 1920, CH / 1080); panels.push({ ox: g * pw + (pw - 1920 * s) / 2, oy: (CH - 1080 * s) / 2, s, group: wide ? g : mode === "auto" ? -1 : clamp((+mode || 1) - 1, 0, 2) }); }
  }
  function clock() {
    const now = cfg.t !== undefined ? +cfg.t + performance.now() / 1000 : Date.now() / 1000;
    const p = ((now % cfg.cycle) + cfg.cycle) % cfg.cycle, seg = (cfg.cycle - OUTRO) / 9, ci = Math.min(8, Math.floor(p / seg));
    return { now, ci, prog: p < cfg.cycle - OUTRO ? (p - ci * seg) / seg : 1, outro: p >= cfg.cycle - OUTRO ? (p - (cfg.cycle - OUTRO)) / OUTRO : -1 };
  }
  function wrap(c, text, x, y, maxW, lh) {
    const words = text.split(" "); let line = "", lines = [];
    for (const w of words) { const test = line ? line + " " + w : w; if (c.measureText(test).width > maxW && line) { lines.push(line); line = w; } else line = test; }
    lines.push(line); lines.forEach((l, k) => c.fillText(l, x, y + (k - (lines.length - 1) / 2) * lh));
  }
  function stars(c, o, t, i) {
    const a = smooth(clamp(o * 4, 0, 1)) * smooth(clamp((1 - o) * 3, 0, 1));
    c.save(); c.globalAlpha = a;
    const g = c.createLinearGradient(0, 0, 0, WIN_H); g.addColorStop(0, "#02040c"); g.addColorStop(1, "#0c1632"); c.fillStyle = g; c.fillRect(0, 0, WIN_W, WIN_H);
    const r = rngf(9 + i);
    for (let k = 0; k < 300; k++) { const x = r() * WIN_W, y = r() * WIN_H, s = r() * r() * 2.4 + 0.4; c.fillStyle = `rgba(255,250,235,${0.4 + 0.6 * r() * (0.6 + 0.4 * Math.sin(t * 2 + k))})`; c.fillRect(x, y, s, s); }
    if (i === 1) {
      c.globalCompositeOperation = "lighter";
      for (const [sx, sy] of [[-40, -70], [12, 34], [-64, -6], [44, -22]]) glow(c, WIN_W / 2 + sx, 330 + sy, 28, "255,252,235", a);
      c.globalCompositeOperation = "source-over";
      c.textAlign = "center"; c.fillStyle = "rgba(240,240,255,0.95)"; c.font = "italic 32px 'Cormorant Garamond', Georgia, serif";
      c.fillText("e quindi uscimmo", WIN_W / 2, 560); c.fillText("a riveder le stelle", WIN_W / 2, 600);
      c.fillStyle = "rgba(200,210,235,0.85)"; c.font = "18px 'Cormorant Garamond', Georgia, serif"; c.fillText("И здесь мы вышли вновь узреть светила.", WIN_W / 2, 644);
    }
    c.restore();
  }

  let last = 0;
  function frame(ts) {
    requestAnimationFrame(frame);
    if (!ready || ts - last < 1000 / cfg.fps - 2) return;
    last = ts;
    const { now, ci, prog, outro } = clock(), t = now % 100000;
    if (glOK) { gl.viewport(0, 0, glc.width, glc.height); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); }
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, fxc.width, fxc.height);
    for (const P of panels) {
      const group = P.group >= 0 ? P.group : Math.floor(ci / 3);
      for (let i = 0; i < 3; i++) {
        const idx = group * 3 + i, sc = SCENES[idx], st = states[idx], active = idx === ci && outro < 0;
        const x0 = GAP + i * (WIN_W + GAP);
        const k = DPR * P.s, rect = [Math.round((P.ox + x0 * P.s) * DPR), Math.round((P.oy + TOP * P.s) * DPR), Math.round(WIN_W * k), Math.round(WIN_H * k)];
        if (glOK) drawGLWindow(idx, rect, t + idx * 37, active ? 1.0 : 0.88, st.flash || 0);
        ctx.setTransform(k, 0, 0, k, P.ox * DPR, P.oy * DPR);
        ctx.save(); archPath(ctx, i); ctx.clip(); ctx.translate(x0, TOP);
        if (!glOK && IM["plate_" + (idx + 1)]) ctx.drawImage(IM["plate_" + (idx + 1)], 0, 0, WIN_W, WIN_H);
        drawParts(ctx, sc, st, t + idx * 37, idx);
        if (active && cfg.poets) {
          const x = -40 + prog * (WIN_W + 80), ph = t * 4.2, y = WIN_H - 26;
          poet(ctx, x, y, 66, ph, "virgil"); poet(ctx, x - 30, y, 66, ph + 1.4, "dante");
        }
        if (active && cfg.quotes) {
          const a = smooth(clamp(prog * 7, 0, 1)) * smooth(clamp((1 - prog) * 7, 0, 1));
          if (a > 0) {
            ctx.save(); ctx.globalAlpha = a; ctx.textAlign = "center";
            const g = ctx.createLinearGradient(0, WIN_H - 190, 0, WIN_H - 70); g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(0.5, "rgba(0,0,0,0.5)"); g.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = g; ctx.fillRect(0, WIN_H - 190, WIN_W, 120);
            ctx.shadowColor = "rgba(0,0,0,1)"; ctx.shadowBlur = 10;
            ctx.fillStyle = "rgba(255,244,228,0.96)"; ctx.font = "italic 25px 'Cormorant Garamond', Georgia, serif"; wrap(ctx, "«" + sc.q + "»", WIN_W / 2, WIN_H - 142, 520, 28);
            ctx.fillStyle = "rgba(232,216,202,0.9)"; ctx.font = "17px 'Cormorant Garamond', Georgia, serif"; ctx.fillText(sc.qru, WIN_W / 2, WIN_H - 98);
            ctx.restore();
          }
        }
        if (outro >= 0) stars(ctx, outro, t, i);
        ctx.restore();
      }
      ctx.setTransform(DPR * P.s, 0, 0, DPR * P.s, DPR * P.ox, DPR * P.oy);
      const fr = IM["frame_" + (group + 1)]; if (fr) ctx.drawImage(fr, 0, 0, 1920, 1080);
      if (outro < 0 && Math.floor(ci / 3) === group) {
        const i = ci % 3, cx = GAP + i * (WIN_W + GAP) + WIN_W / 2;
        ctx.globalCompositeOperation = "lighter"; glow(ctx, cx, 975, 150, "255,180,100", 0.2 + 0.06 * Math.sin(t * 2)); ctx.globalCompositeOperation = "source-over";
        ctx.strokeStyle = "rgba(255,200,120,0.6)"; ctx.lineWidth = 1.6; ctx.save(); archPath(ctx, i); ctx.stroke(); ctx.restore();
      }
    }
  }

  function setProp(name, val) {
    if (name === "screen") { mode = typeof val === "number" ? ["1", "2", "3", "all", "auto"][val] || "auto" : String(val); layout(); }
    if (name === "cycle") cfg.cycle = Math.min(1200, Math.max(120, +val * 60 || 540));
    if (name === "quotes") cfg.quotes = !!val;
    if (name === "poets") cfg.poets = !!val;
    if (name === "fps") cfg.fps = +val || 30;
  }
  window.livelyPropertyListener = setProp;
  window.wallpaperPropertyListener = { applyUserProperties(p) { for (const k in p) if (p[k] && "value" in p[k]) setProp(k, p[k].value); } };

  makeSmoke();
  window.addEventListener("resize", layout);
  layout();
  const names = []; for (let i = 1; i <= 9; i++) names.push("plate_" + i); names.push("frame_1", "frame_2", "frame_3");
  Promise.all(names.map((n) => new Promise((res) => { const im = new Image(); im.onload = () => { IM[n] = im; res(); }; im.onerror = () => res(); im.src = (window.INFERNO_DATA && window.INFERNO_DATA[n]) || BASE + n + ".webp"; }))).then(() => {
    try { glOK = initGL(); if (glOK) for (let i = 1; i <= 9; i++) textures[i - 1] = uploadTex(IM["plate_" + i]); }
    catch (e) { console.warn("WebGL недоступен, рисую без эффектов искажения", e); glOK = false; }
    ready = true;
  });
  requestAnimationFrame(frame);
})();
