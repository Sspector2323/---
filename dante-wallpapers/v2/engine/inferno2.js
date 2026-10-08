/* INFERNO II — живые обои-триптих на три монитора.
 * Каждый монитор — готическая рама с тремя окнами; в каждом окне свой круг Ада.
 * Данте и Вергилий проходят все 9 кругов за цикл (по умолчанию 9 минут) и уходят
 * с одного монитора на другой. Время берётся из системных часов — три обоины синхронны.
 * Настройки: window.INFERNO_CONFIG или параметры URL: screen=1|2|3|all|auto, cycle (сек), fps, t (отладка).
 */
(function () {
  "use strict";
  const cfg = Object.assign({ screen: "auto", cycle: 540, fps: 30, quotes: 1 }, window.INFERNO_CONFIG || {});
  const qs = new URLSearchParams(location.search);
  for (const k of ["screen", "cycle", "fps", "t", "quotes"]) if (qs.has(k)) cfg[k] = qs.get(k);
  cfg.cycle = Math.min(1200, Math.max(120, +cfg.cycle || 540));
  cfg.fps = Math.min(60, Math.max(10, +cfg.fps || 30));
  cfg.quotes = !(cfg.quotes === "0" || cfg.quotes === 0);
  const SPEC = window.INFERNO_SPEC;
  const BASE = window.INFERNO_ASSETS || "assets/";

  const TAU = Math.PI * 2, OUTRO = 14;
  const WIN_W = 560, WIN_H = 930, TOP = 30, GAP = 60, PATH_Y = 878;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const smooth = (t) => t * t * (3 - 2 * t);
  const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
  const noise1 = (x) => { const i = Math.floor(x), f = x - i; const u = f * f * (3 - 2 * f); return lerp(hash(i), hash(i + 1), u); };
  function rngf(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  // ---------------- спрайты ----------------
  const spriteCache = {};
  function glowSprite(rgb) {
    if (spriteCache[rgb]) return spriteCache[rgb];
    const c = document.createElement("canvas"); c.width = c.height = 128;
    const x = c.getContext("2d"), g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, `rgba(${rgb},1)`); g.addColorStop(0.25, `rgba(${rgb},0.45)`); g.addColorStop(0.6, `rgba(${rgb},0.1)`); g.addColorStop(1, `rgba(${rgb},0)`);
    x.fillStyle = g; x.fillRect(0, 0, 128, 128);
    return (spriteCache[rgb] = c);
  }
  function glow(c, x, y, r, rgb, a) {
    if (a <= 0) return;
    const o = c.globalCompositeOperation, ga = c.globalAlpha;
    c.globalCompositeOperation = "lighter"; c.globalAlpha = Math.min(1, a);
    c.drawImage(glowSprite(rgb), x - r, y - r, r * 2, r * 2);
    c.globalCompositeOperation = o; c.globalAlpha = ga;
  }
  const flames = [];
  function makeFlames() {
    for (let v = 0; v < 4; v++) {
      const c = document.createElement("canvas"); c.width = 96; c.height = 192;
      const x = c.getContext("2d"); x.filter = "blur(5px)";
      const r = rngf(10 + v);
      for (const [col, sc] of [["255,90,20", 1], ["255,170,50", 0.72], ["255,240,190", 0.42]]) {
        x.fillStyle = `rgba(${col},0.95)`; x.beginPath();
        const w = 30 * sc, h = 150 * sc, cx = 48 + (r() - 0.5) * 6;
        x.moveTo(cx - w, 180); x.bezierCurveTo(cx - w * 1.1, 180 - h * 0.45, cx - w * 0.2 + (r() - 0.5) * 20, 180 - h * 0.7, cx + (r() - 0.5) * 16, 180 - h);
        x.bezierCurveTo(cx + w * 0.3, 180 - h * 0.7, cx + w * 1.1, 180 - h * 0.45, cx + w, 180); x.closePath(); x.fill();
      }
      flames.push(c);
    }
  }
  function fire(c, x, y, w, h, t, seed, a) {
    const o = c.globalCompositeOperation; c.globalCompositeOperation = "lighter";
    for (let k = 0; k < 2; k++) {
      const f = noise1(t * 3.1 + seed * 7 + k * 13), g = noise1(t * 4.3 + seed * 3 + k * 5);
      const hh = h * (0.7 + 0.55 * f), ww = w * (0.85 + 0.3 * g);
      c.globalAlpha = (a ?? 1) * (k ? 0.6 : 0.9);
      const img = flames[(Math.floor(t * 9 + seed * 3 + k * 2)) % flames.length];
      c.save(); c.translate(x, y); c.transform(1, 0, (g - 0.5) * 0.35, 1, 0, 0);
      c.drawImage(img, -ww * (1 + k * 0.2) / 2, -hh * (1 - k * 0.2), ww * (1 + k * 0.2), hh * (1 - k * 0.2) * 1.05);
      c.restore();
    }
    c.globalAlpha = 1; c.globalCompositeOperation = o;
  }
  let fogTex;
  function makeFog() {
    const c = document.createElement("canvas"); c.width = 1024; c.height = 256;
    const x = c.getContext("2d"); x.filter = "blur(18px)"; const r = rngf(77);
    for (let i = 0; i < 70; i++) {
      const px = r() * 1024, py = 60 + r() * 140, rx = 40 + r() * 120, ry = 14 + r() * 34, a = 0.06 + r() * 0.12;
      x.fillStyle = `rgba(255,255,255,${a})`;
      for (const dx of [-1024, 0, 1024]) { x.beginPath(); x.ellipse(px + dx, py, rx, ry, 0, 0, TAU); x.fill(); }
    }
    fogTex = c;
  }
  function fogBand(c, y, h, t, speed, rgb, a, off) {
    const o = c.globalCompositeOperation; c.globalCompositeOperation = "lighter";
    const tint = tintFog(rgb);
    c.globalAlpha = a;
    const sx = ((t * speed + (off || 0)) % 1024 + 1024) % 1024, w = 1024 * (h / 256);
    for (let x = -sx * (h / 256); x < WIN_W; x += w) c.drawImage(tint, x, y - h / 2, w, h);
    c.globalAlpha = 1; c.globalCompositeOperation = o;
  }
  const fogTints = {};
  function tintFog(rgb) {
    if (fogTints[rgb]) return fogTints[rgb];
    const c = document.createElement("canvas"); c.width = 1024; c.height = 256;
    const x = c.getContext("2d"); x.drawImage(fogTex, 0, 0); x.globalCompositeOperation = "source-in"; x.fillStyle = `rgb(${rgb})`; x.fillRect(0, 0, 1024, 256);
    return (fogTints[rgb] = c);
  }

  // ---------------- фигуры ----------------
  // Позы: углы от вертикали вниз (+ к +x). lean — наклон корпуса, head — наклон головы.
  function bodyPath(c, P) {
    const hipX = 0, hipY = -50, L = P.lean || 0;
    const nx = hipX + Math.sin(L) * 30, ny = hipY - Math.cos(L) * 30;
    const sx = hipX + Math.sin(L) * 26, sy = hipY - Math.cos(L) * 26;
    const px = Math.cos(L), py = Math.sin(L);
    c.lineCap = "round"; c.lineJoin = "round";
    const limb = (x, y, a1, l1, w1, a2, l2, w2) => {
      const kx = x + Math.sin(a1) * l1, ky = y + Math.cos(a1) * l1;
      c.lineWidth = w1; c.beginPath(); c.moveTo(x, y); c.lineTo(kx, ky); c.stroke();
      c.lineWidth = w2; c.beginPath(); c.moveTo(kx, ky); c.lineTo(kx + Math.sin(a2) * l2, ky + Math.cos(a2) * l2); c.stroke();
    };
    if (!P.noLegs) {
      limb(hipX - px * 3, hipY - py * 3, P.tl ?? -0.08, 25, 10, P.sl ?? -0.05, 25, 7.5);
      limb(hipX + px * 3, hipY + py * 3, P.tr ?? 0.08, 25, 10, P.sr ?? 0.05, 25, 7.5);
    }
    c.beginPath(); // торс
    c.moveTo(hipX - px * 7, hipY - py * 7); c.lineTo(hipX + px * 7, hipY + py * 7);
    c.quadraticCurveTo(sx + px * 9 + Math.sin(L) * 2, (hipY + sy) / 2 + py * 9, sx + px * 11, sy + py * 11);
    c.lineTo(sx - px * 11, sy - py * 11);
    c.quadraticCurveTo(sx - px * 9, (hipY + sy) / 2 - py * 9, hipX - px * 7, hipY - py * 7);
    c.fill();
    c.lineWidth = 6.5; c.beginPath(); c.moveTo(sx, sy); c.lineTo(nx, ny); c.stroke();
    const hx = nx + Math.sin(L + (P.head || 0)) * 8, hy = ny - Math.cos(L + (P.head || 0)) * 8;
    if (P.noHead !== true) { c.beginPath(); c.ellipse(hx, hy, 6.8, 8, L + (P.head || 0), 0, TAU); c.fill(); }
    limb(sx - px * 9, sy - py * 9, P.ul ?? -0.12, 17, 6.5, P.fl ?? -0.05, 16, 5.2);
    limb(sx + px * 9, sy + py * 9, P.ur ?? 0.12, 17, 6.5, P.fr ?? 0.05, 16, 5.2);
    return [hx, hy];
  }
  // st: fill, rim, rx, ry (направление света), rot, flip, alpha
  function fig(c, x, y, h, P, st) {
    c.save(); c.translate(x, y); if (st.rot) c.rotate(st.rot);
    const k = h / 100; c.scale(st.flip ? -k : k, k);
    if (st.alpha !== undefined) c.globalAlpha = st.alpha;
    let head;
    if (st.rim) {
      c.save(); c.translate((st.rx || 0) * 2.4, (st.ry ?? -1) * 2.4);
      c.fillStyle = c.strokeStyle = st.rim; bodyPath(c, P); c.restore();
    }
    c.fillStyle = c.strokeStyle = st.fill; head = bodyPath(c, P);
    c.restore();
    return head;
  }
  const walkP = (ph, lean) => ({ lean: lean ?? 0.06, head: 0.1, tl: 0.42 * Math.sin(ph), tr: -0.42 * Math.sin(ph), sl: 0.42 * Math.sin(ph) - 0.45 * Math.max(0, Math.cos(ph)), sr: -0.42 * Math.sin(ph) - 0.45 * Math.max(0, -Math.cos(ph)), ul: -0.35 * Math.sin(ph), fl: -0.35 * Math.sin(ph) + 0.35, ur: 0.35 * Math.sin(ph), fr: 0.35 * Math.sin(ph) + 0.35 });

  // Поэты: Данте (красный плащ, капюшон) и Вергилий (серо-синий, лавр)
  function poet(c, x, y, h, ph, who, light) {
    c.save(); c.translate(x, y - Math.abs(Math.sin(ph)) * h * 0.02); const k = h / 100; c.scale(k, k);
    glow(c, 0, -55, 75, light || "255,220,170", 0.28);
    const robe = who === "dante" ? "#8e1a1f" : "#3c4558", hi = who === "dante" ? "#e0503f" : "#8f9cb8";
    const sw = Math.sin(ph) * 5;
    const draw = (col, dx, dy) => {
      c.fillStyle = col;
      c.beginPath(); c.moveTo(-9 + dx, -78 + dy);
      c.bezierCurveTo(-15 + dx, -50 + dy, -18 + sw * 0.4 + dx, -20 + dy, -20 + sw + dx, 0 + dy);
      c.lineTo(20 + sw + dx, 0 + dy);
      c.bezierCurveTo(18 + sw * 0.4 + dx, -20 + dy, 15 + dx, -50 + dy, 10 + dx, -78 + dy); c.closePath(); c.fill();
      c.beginPath(); c.ellipse(1 + dx, -86 + dy, 7, 8.5, 0, 0, TAU); c.fill();
      // рука вперёд
      c.strokeStyle = col; c.lineWidth = 6; c.lineCap = "round";
      c.beginPath(); c.moveTo(6 + dx, -70 + dy); c.lineTo(15 + dx, -52 + dy + sw * 0.3); c.stroke();
    };
    draw(hi, 0, -2.2); draw(robe, 0, 0);
    c.fillStyle = "#e3cdb2"; c.beginPath(); c.ellipse(4, -86, 4.2, 6, 0.1, 0, TAU); c.fill();
    if (who === "dante") { c.fillStyle = "#b02529"; c.beginPath(); c.moveTo(-8, -84); c.quadraticCurveTo(-4, -101, 8, -96); c.lineTo(10, -90); c.quadraticCurveTo(2, -94, -4, -76); c.closePath(); c.fill(); }
    else { c.strokeStyle = "#86b86b"; c.lineWidth = 2.2; c.beginPath(); c.arc(1, -88, 8.5, Math.PI * 1.0, Math.PI * 2.0); c.stroke(); }
    c.restore();
  }

  // ---------------- сцены ----------------
  // общий вид: init(r), draw(c, t, active)
  const RIM_FIRE = "rgba(255,150,70,0.95)";
  const SC = [];

  // I. ЛИМБ
  SC.push({
    num: "I", q: "sanza speme vivemo in disio", qru: "без надежды живём в желании", light: "255,236,200",
    init(r) { this.shades = Array.from({ length: 18 }, () => { const y = 610 + r() * 230; return { x: r() * 600 - 20, y, h: 24 + (y - 600) * 0.26, sp: (r() < 0.5 ? -1 : 1) * (2 + r() * 3), ph: r() * TAU }; }).sort((a, b) => a.y - b.y); this.motes = Array.from({ length: 40 }, () => ({ x: 120 + r() * 320, y: r(), s: r() })); },
    draw(c, t) {
      glow(c, 280, 468, 90 + 10 * Math.sin(t * 0.7), "255,236,200", 0.45);
      for (const m of this.motes) { const y = 560 - ((m.y + t * 0.01 * (1 + m.s)) % 1) * 300; glow(c, m.x + Math.sin(t * 0.5 + m.s * 9) * 10, y, 5 + m.s * 4, "255,240,210", 0.5 * Math.sin(((m.y + t * 0.01 * (1 + m.s)) % 1) * Math.PI)); }
      fogBand(c, 600, 120, t, 6, "150,160,170", 0.35, 0);
      for (const s of this.shades) {
        const x = ((s.x + t * s.sp) % 620 + 620) % 620 - 30, ph = t * 1.2 + s.ph;
        glow(c, x, s.y - s.h * 0.55, s.h * 0.9, "170,190,215", 0.14);
        const P = walkP(ph * 0.7, 0.12); P.head = 0.45; P.ul = 0.1; P.ur = -0.05; P.fl = 0.3; P.fr = 0.2;
        fig(c, x, s.y, s.h, P, { fill: "rgba(150,170,195,0.2)", rim: "rgba(220,230,245,0.16)", ry: -1, flip: s.sp < 0 });
        // вздох
        const sp = (t * 0.15 + s.ph) % 1;
        c.strokeStyle = `rgba(210,220,235,${0.35 * Math.sin(sp * Math.PI)})`; c.lineWidth = 1;
        c.beginPath(); c.arc(x + (s.sp < 0 ? -3 : 3), s.y - s.h - sp * 40, 2 + sp * 8, 0, TAU); c.stroke();
      }
      fogBand(c, 760, 160, t, 9, "120,130,140", 0.28, 400);
    },
  });

  // II. СЛАДОСТРАСТИЕ
  SC.push({
    num: "II", q: "Amor, ch'a nullo amato amar perdona", qru: "любовь, что любить велит любимым", light: "255,140,210",
    init(r) { this.souls = Array.from({ length: 40 }, () => ({ ph: r() * TAU, y: r(), sp: 0.5 + r() * 0.5, w: r() * TAU, h: 40 + r() * 26 })); this.streaks = Array.from({ length: 30 }, () => ({ ph: r() * TAU, y: r(), l: 0.4 + r() })); },
    fx(y) { return 280 + 22 * Math.sin(y / 140); },
    fr(y) { return 30 + Math.max(0, 880 - y) * 0.24 + 6 * Math.sin(y / 30); },
    draw(c, t) {
      // молния
      const L = noise1(t * 0.45 + 3);
      if (L > 0.86) {
        const a = (L - 0.86) * 7;
        c.fillStyle = `rgba(255,200,250,${a * 0.25})`; c.fillRect(0, 0, WIN_W, WIN_H);
        c.strokeStyle = `rgba(255,235,255,${a})`; c.lineWidth = 2; c.beginPath();
        let x = 120 + hash(Math.floor(t * 0.45)) * 320, y = 40; c.moveTo(x, y);
        for (let i = 0; i < 12; i++) { x += (hash(i + Math.floor(t * 0.45) * 13) - 0.5) * 40; y += 18; c.lineTo(x, y); }
        c.stroke(); glow(c, x, y - 100, 160, "255,170,240", a * 0.6);
      }
      const items = [];
      for (const s of this.souls) {
        const y = 880 - ((s.y + t * 0.012 * s.sp) % 1) * 720;
        const a = s.ph + t * (0.9 + 0.4 * s.sp) * (1 + (880 - y) / 900);
        items.push({ s, y, a, z: Math.sin(a) });
      }
      items.sort((p, q) => p.z - q.z);
      for (const st of this.streaks) {
        const y = 880 - ((st.y + t * 0.01) % 1) * 720, R = this.fr(y) + 24, a0 = st.ph + t * 1.1;
        c.strokeStyle = "rgba(255,170,230,0.12)"; c.lineWidth = 1.4; c.beginPath();
        c.ellipse(this.fx(y), y, R, R * 0.16, 0, a0, a0 + st.l); c.stroke();
      }
      for (const it of items) {
        const R = this.fr(it.y) + 12 + it.s.h * 0.3;
        const x = this.fx(it.y) + Math.cos(it.a) * R, y = it.y + Math.sin(it.a) * R * 0.16;
        const back = it.z < 0;
        const fl = Math.sin(t * 4 + it.s.w);
        const P = { lean: 0, head: 0.3 * fl, ul: Math.PI - 0.5 + fl * 0.5, fl: Math.PI - 0.2 + fl * 0.6, ur: -Math.PI + 0.7 - fl * 0.4, fr: -Math.PI + 0.3, tl: -0.3 + fl * 0.3, sl: -0.6, tr: 0.4 - fl * 0.2, sr: 0.1 };
        fig(c, x, y, it.s.h, P, { rot: -Math.sign(Math.sin(it.a)) * 0 + (Math.cos(it.a) > 0 ? -1.4 : 1.4) + fl * 0.2, fill: back ? "rgba(70,24,70,0.45)" : "#1c0a1c", rim: back ? null : "rgba(255,150,220,0.9)", rx: -Math.cos(it.a) * 0.6, ry: -0.8 });
      }
      // Паоло и Франческа
      const a = t * 0.35, y = 520 + Math.sin(t * 0.2) * 60, R = this.fr(y) + 60;
      const px = this.fx(y) + Math.cos(a) * R, py = y + Math.sin(a) * R * 0.16;
      glow(c, px, py - 20, 70, "255,130,190", 0.55);
      fig(c, px - 8, py, 50, { lean: 0.3, head: 0.3, ul: 1.6, fl: 2.4, ur: 1.2, fr: 1.9, tl: -0.4, sl: -0.9 }, { rot: -1.0, fill: "#2a0d24", rim: "rgba(255,200,230,0.95)" });
      fig(c, px + 8, py + 4, 47, { lean: -0.3, head: -0.3, ul: -1.4, fl: -2.2, ur: -1.8, fr: -2.5, tl: 0.3, sl: 0.7 }, { rot: -0.8, fill: "#2a0d24", rim: "rgba(255,200,230,0.95)" });
    },
  });

  // III. ЧРЕВОУГОДИЕ
  SC.push({
    num: "III", q: "Cerbero, fiera crudele e diversa", qru: "Цербер, зверь жестокий и чудовищный", light: "190,200,170",
    init(r) {
      this.mud = Array.from({ length: 16 }, () => { const y = 600 + r() * 250; return { x: r() * 560, y, h: 26 + (y - 560) * 0.22, ph: r() * TAU, d: r() < 0.5 ? 1 : -1 }; }).sort((a, b) => a.y - b.y);
      this.rain = Array.from({ length: 520 }, () => ({ x: r() * 700, y: r(), z: r() }));
      this.spl = Array.from({ length: 60 }, () => ({ x: r() * 560, y: 580 + r() * 290, ph: r() }));
    },
    cerberus(c, t) {
      const [cx, cy] = SPEC.gola.cerberus;
      const lunge = Math.max(0, Math.sin(t * 0.35)) ** 8;
      c.save(); c.translate(cx - 6 + lunge * -14, cy + 4); c.scale(1.3, 1.3);
      const draw = (col, dx, dy) => {
        c.fillStyle = c.strokeStyle = col; c.lineCap = "round";
        c.beginPath(); c.moveTo(60 + dx, -24 + dy); c.bezierCurveTo(70 + dx, -60 + dy, 0 + dx, -70 + dy, -40 + dx, -52 + dy);
        c.bezierCurveTo(-70 + dx, -44 + dy, -70 + dx, -6 + dy, -50 + dx, -2 + dy); c.lineTo(50 + dx, -2 + dy); c.closePath(); c.fill();
        c.lineWidth = 11; c.beginPath();
        for (const [lx, ph] of [[-46, 0], [-30, 2], [36, 1], [52, 3]]) { const s = Math.sin(t * 2 + ph) * 3; c.moveTo(lx + dx, -12 + dy); c.lineTo(lx + s + dx, 6 + dy); }
        c.stroke();
        c.lineWidth = 6; c.beginPath(); c.moveTo(60 + dx, -32 + dy); c.quadraticCurveTo(88 + dx, -50 + dy, 84 + dx, -76 + dy + Math.sin(t * 3) * 4); c.stroke();
        for (let i = 0; i < 3; i++) {
          const bob = Math.sin(t * 1.8 + i * 2.1) * 5, ang = -0.5 + i * 0.45;
          const hx = -50 - 28 * Math.cos(ang) - lunge * 10, hy = -60 + 34 * Math.sin(ang) + bob;
          c.lineWidth = 16; c.beginPath(); c.moveTo(-34 + dx, -48 + dy); c.quadraticCurveTo(-48 + dx, -64 + dy, hx + dx, hy + dy); c.stroke();
          c.beginPath(); c.ellipse(hx - 10 + dx, hy + 2 + dy, 18, 11, 0.25 - i * 0.12, 0, TAU); c.fill();
          const jaw = Math.max(0, Math.sin(t * 3.3 + i * 1.7)) * 8;
          c.beginPath(); c.moveTo(hx - 14 + dx, hy + 8 + dy); c.lineTo(hx - 36 + dx, hy + 6 + jaw + dy); c.lineTo(hx - 18 + dx, hy + 15 + jaw * 0.6 + dy); c.fill();
          c.beginPath(); c.moveTo(hx - 2 + dx, hy - 8 + dy); c.lineTo(hx + 4 + dx, hy - 20 + dy); c.lineTo(hx + 7 + dx, hy - 6 + dy); c.fill();
        }
      };
      draw("rgba(150,170,120,0.45)", 1.2, -1.8); draw("#0b0c08", 0, 0);
      for (let i = 0; i < 3; i++) {
        const bob = Math.sin(t * 1.8 + i * 2.1) * 5, ang = -0.5 + i * 0.45;
        const hx = -50 - 28 * Math.cos(ang) - lunge * 10, hy = -60 + 34 * Math.sin(ang) + bob;
        glow(c, hx - 16, hy - 2, 8, "255,40,10", 0.9);
        const br = (t * 0.6 + i * 0.33) % 1; glow(c, hx - 40 - br * 20, hy + 6 - br * 10, 12 + br * 14, "160,170,150", 0.25 * (1 - br));
      }
      c.restore();
    },
    draw(c, t) {
      for (const s of this.mud) {
        const w = Math.sin(t * 0.9 + s.ph);
        const P = { lean: 0, head: -0.6 + 0.3 * w, ul: Math.PI * 0.75 + 0.3 * w, fl: Math.PI * 0.9, ur: 0.6, fr: 1.4, tl: 0.1, sl: 0.4, tr: -0.1, sr: 0.2 };
        c.save(); c.beginPath(); c.rect(s.x - 70, 0, 140, s.y + 2); c.clip();
        fig(c, s.x, s.y + s.h * 0.12, s.h, P, { rot: s.d * 1.5, fill: "#0e0d08", rim: "rgba(200,210,175,0.85)", rx: -0.3, ry: -1 });
        c.restore();
      }
      this.cerberus(c, t);
      // дождь: три слоя глубины
      c.lineCap = "round";
      for (const layer of [[0.3, 0.12, 1, 10], [0.6, 0.2, 1.2, 18], [1, 0.32, 1.6, 30]]) {
        c.strokeStyle = `rgba(190,200,185,${layer[1]})`; c.lineWidth = layer[2]; c.beginPath();
        for (const d of this.rain) {
          if (d.z > layer[0] || d.z < layer[0] - 0.4) continue;
          const y = ((d.y + t * (0.8 + layer[0])) % 1) * 1000 - 40, x = d.x - y * 0.22 - 60;
          c.moveTo(x, y); c.lineTo(x - layer[3] * 0.22, y + layer[3]);
        }
        c.stroke();
      }
      for (const s of this.spl) {
        const p = (t * 1.6 + s.ph) % 1, sc = 0.4 + (s.y - 560) / 400;
        c.strokeStyle = `rgba(190,200,180,${0.35 * (1 - p)})`; c.lineWidth = 1;
        c.beginPath(); c.ellipse(s.x, s.y, 2 + p * 8 * sc, (1 + p * 2.5) * sc, 0, 0, TAU); c.stroke();
      }
      fogBand(c, 700, 200, t, 10, "120,130,110", 0.18, 100);
    },
  });

  // IV. СКУПОСТЬ
  SC.push({
    num: "IV", q: "mal dare e mal tener lo mondo pulcro ha tolto loro", qru: "худо давали и худо хранили — и потеряли прекрасный мир", light: "255,200,120",
    init(r) { this.rows = [[668, 0.85], [790, 1.25]].map(([y, s], i) => ({ y, s, off: i * 0.13 })); this.dust = Array.from({ length: 70 }, () => ({ x: r() * 560, y: r() * 900, s: r() })); this.burst = []; },
    draw(c, t) {
      for (const d of this.dust) { const y = ((d.y - t * 4 * (0.5 + d.s)) % 900 + 900) % 900; glow(c, d.x + Math.sin(t * 0.3 + d.s * 9) * 10, y, 3 + d.s * 3, "255,220,150", 0.3); }
      const P = 18;
      for (const row of this.rows) {
        const ph = (t / P + row.off) % 1;
        let k = ph < 0.42 ? smooth(ph / 0.42) : ph < 0.55 ? 1 : 1 - smooth((ph - 0.55) / 0.45);
        const push = ph < 0.5, hit = ph > 0.41 && ph < 0.5;
        const shake = hit ? Math.sin(t * 50) * 2 * row.s : 0;
        const br = 30 * row.s, h = 70 * row.s;
        for (const side of [-1, 1]) {
          for (let i = 0; i < 2; i++) {
            const near = 280 + side * (br + 2 + i * (br * 2 + 70 * row.s)), far = 280 + side * (190 + i * 110) * row.s;
            const bx = lerp(far, near, k) + shake * side, by = row.y - br;
            const rot = (bx / br);
            // валун-груз: металлический шар с бликом
            const g = c.createRadialGradient(bx - br * 0.35, by - br * 0.4, br * 0.1, bx, by, br);
            g.addColorStop(0, "#fff0b8"); g.addColorStop(0.25, "#d6a344"); g.addColorStop(0.7, "#6b4612"); g.addColorStop(1, "#24160a");
            c.fillStyle = g; c.beginPath(); c.arc(bx, by, br, 0, TAU); c.fill();
            c.strokeStyle = "rgba(60,36,10,0.6)"; c.lineWidth = 1.5 * row.s; c.beginPath(); c.arc(bx, by, br * 0.7, rot, rot + 2); c.stroke();
            const dir = push ? -side : side, px = bx + side * (br + 12 * row.s);
            const wp = walkP(t * (push ? 4 : 3) + i, 0);
            const pose = push ? Object.assign(wp, { lean: dir * 0.75, head: dir * -0.2, ul: dir * 1.7, fl: dir * 1.5, ur: dir * 1.5, fr: dir * 1.4 }) : Object.assign(wp, { lean: dir * 0.15 });
            fig(c, px, row.y, h, pose, { fill: "#1b1206", rim: "rgba(255,200,120,0.85)", rx: 0.2, ry: -1 });
          }
        }
        if (hit) {
          const a = 1 - Math.abs(ph - 0.455) / 0.045;
          glow(c, 280, row.y - br, 90 * row.s, "255,220,150", a * 0.8);
          for (let j = 0; j < 14; j++) { const an = j / 14 * TAU, d = (ph - 0.41) / 0.09 * 60 * row.s; glow(c, 280 + Math.cos(an) * d, row.y - br + Math.sin(an) * d * 0.5, 4 * row.s, "255,230,160", a); }
        }
        if (row === this.rows[1] && ph > 0.4 && ph < 0.62) {
          const a = Math.sin((ph - 0.4) / 0.22 * Math.PI);
          c.textAlign = "center"; c.font = "italic 19px 'Cormorant Garamond', Georgia, serif";
          c.fillStyle = `rgba(255,225,170,${a * 0.9})`;
          c.fillText("«Perché tieni?»", 150, 600); c.fillText("«Perché burli?»", 410, 600);
        }
      }
      fogBand(c, 560, 90, t, 7, "200,150,80", 0.22, 300);
    },
  });

  // V. ГНЕВ
  SC.push({
    num: "V", q: "Tristi fummo ne l'aere dolce che dal sol s'allegra", qru: "угрюмы были мы в сладком воздухе, что радуется солнцу", light: "255,140,70",
    init(r) { this.f = Array.from({ length: 14 }, () => { const y = 600 + r() * 240; return { x: r() * 560, y, h: 30 + (y - 556) * 0.28, ph: r() * TAU, d: r() < 0.5 ? 1 : -1 }; }).sort((a, b) => a.y - b.y); this.bub = Array.from({ length: 40 }, () => ({ x: r() * 560, y: 580 + r() * 280, ph: r() })); },
    boat(c, x, y, t, s) {
      c.save(); c.translate(x, y + Math.sin(t * 1.1) * 1.5); c.scale(s, s);
      glow(c, 48, -76, 40, "255,170,90", 0.6);
      c.fillStyle = "#070a09"; c.beginPath(); c.moveTo(-70, -10); c.quadraticCurveTo(0, 18, 72, -14); c.lineTo(64, -2); c.quadraticCurveTo(0, 10, -64, 0); c.closePath(); c.fill();
      c.strokeStyle = "rgba(255,150,80,0.6)"; c.lineWidth = 1.2; c.beginPath(); c.moveTo(-70, -10); c.quadraticCurveTo(0, 16, 72, -14); c.stroke();
      fig(c, 52, -6, 64, { lean: 0.15, ul: 2.6, fl: 2.8, ur: 2.4, fr: 2.6 }, { fill: "#050707", rim: "rgba(255,150,80,0.8)", rx: -0.5 });
      c.strokeStyle = "#050707"; c.lineWidth = 3; c.beginPath(); c.moveTo(70, -100); c.lineTo(40, 26); c.stroke();
      c.strokeStyle = "rgba(180,220,210,0.25)"; c.lineWidth = 1; c.beginPath(); c.ellipse(0, 4, 90, 6, 0, 0, TAU); c.stroke();
      c.restore();
    },
    draw(c, t, active) {
      const [bx, by] = SPEC.ira.beacon, fl = 0.6 + 0.4 * noise1(t * 4);
      glow(c, bx - 8, by - 6, 40 * fl, "255,140,50", 0.9); glow(c, bx + 8, by - 6, 40 * fl, "255,140,50", 0.9);
      const [fx, fy] = SPEC.ira.far, blink = Math.max(0, Math.sin(t * 0.8)) ** 4;
      glow(c, fx, fy, 22, "255,140,50", 0.4 + 0.6 * blink);
      // отражение огня мерцает
      for (let i = 0; i < 12; i++) { const y = 570 + i * 22, w = 4 + i * 2.2; glow(c, bx + Math.sin(t * 2 + i) * 6, y, w * 2, "255,130,50", 0.18 * fl * (1 - i / 12)); }
      for (const s of this.f) {
        const hit = Math.sin(t * 2.6 + s.ph), bob = Math.sin(t * 1.3 + s.ph) * 2, wl = s.y - s.h * 0.45 + bob;
        c.save(); c.beginPath(); c.rect(s.x - 60, 0, 120, wl); c.clip();
        fig(c, s.x, s.y + bob, s.h, { lean: s.d * hit * 0.25, head: s.d * 0.2, ul: s.d * (2.2 + hit), fl: s.d * (2.6 + hit * 0.6), ur: s.d * (1.6 - hit * 0.8), fr: s.d * 2.4 }, { fill: "#030807", rim: "rgba(255,150,80,0.8)", rx: 0.7, ry: -0.7 });
        c.restore();
        c.strokeStyle = "rgba(160,210,200,0.3)"; c.lineWidth = 1; c.beginPath(); c.ellipse(s.x, wl, s.h * 0.3 + Math.abs(hit) * 6, s.h * 0.05, 0, 0, TAU); c.stroke();
        if (Math.abs(hit) > 0.96) for (let j = 0; j < 5; j++) glow(c, s.x + (hash(j + s.ph) - 0.5) * 30, wl - hash(j * 3 + s.ph) * 16, 3, "200,230,220", 0.6);
      }
      for (const b of this.bub) { const p = (t * 0.3 + b.ph) % 1; c.strokeStyle = `rgba(160,210,200,${0.4 * (1 - p)})`; c.lineWidth = 1; c.beginPath(); c.ellipse(b.x, b.y, 2 + p * 9, 0.6 + p * 2.2, 0, 0, TAU); c.stroke(); }
      if (!active) this.boat(c, 90 + Math.sin(t * 0.1) * 20, 700, t, 0.85);
      fogBand(c, 600, 110, t, 8, "120,170,160", 0.25, 0); fogBand(c, 800, 150, t, 12, "70,110,100", 0.2, 500);
    },
    path(p) { return { x: -80 + p * (WIN_W + 160), y: 720, boat: true }; },
  });

  // VI. ЕРЕСЬ
  SC.push({
    num: "VI", q: "Qui son li eresiarche con lor seguaci", qru: "здесь ересиархи со своими последователями", light: "255,140,60",
    init(r) { this.emb = Array.from({ length: 120 }, () => ({ x: r() * 560, y: r(), s: r() })); this.souls = SPEC.eresia.tombs.map((tb, i) => ({ on: r() < 0.5, ph: r() * 20 })); },
    draw(c, t) {
      const tombs = SPEC.eresia.tombs;
      tombs.forEach(([x, y, sc], i) => {
        const h = 22 * sc, d = 14 * sc, top = y - h - d * 0.5;
        const so = this.souls[i];
        if (so.on || (i === 18)) {
          const isF = i === 18; // Фарината — «от пояса и выше»
          const rise = isF ? smooth(clamp(Math.sin(t * 0.12) * 1.6, 0, 1)) : (Math.sin(t * 0.35 + so.ph) * 0.5 + 0.5);
          const fh = 64 * sc * (isF ? 1.25 : 1);
          c.save(); c.beginPath(); c.rect(x - 60, 0, 120, top + 2); c.clip();
          fig(c, x, top + fh * (0.62 - rise * 0.3), fh, isF ? { ul: 0.3, fl: 0.6, ur: -0.2, fr: -0.4, head: -0.1 } : { ul: 2.7 + Math.sin(t * 2 + so.ph) * 0.3, fl: 3.0, ur: -2.5, fr: -2.9, head: -0.3 }, { fill: "#140504", rim: "rgba(255,190,110,0.95)", ry: 1, rx: 0 });
          c.restore();
        }
        fire(c, x - 16 * sc, top + 3 * sc, 36 * sc, 74 * sc, t, i * 3.1, 0.9);
        fire(c, x + 14 * sc, top + 3 * sc, 32 * sc, 62 * sc, t, i * 5.7 + 1, 0.8);
        glow(c, x, top - 10 * sc, 60 * sc, "255,110,30", 0.35 + 0.15 * noise1(t * 3 + i));
      });
      for (const e of this.emb) { const p = (e.y + t * 0.04 * (0.5 + e.s)) % 1, y = 860 - p * 700; glow(c, e.x + Math.sin(t + e.s * 20) * 14 * p, y, 2.5 + e.s * 2, "255,170,80", 0.8 * (1 - p)); }
      // фурии на башне
      for (let i = 0; i < 3; i++) {
        const x = 214 + i * 22, y = 326 + Math.sin(t * 1.5 + i) * 2, fl = Math.sin(t * 6 + i * 1.3);
        c.fillStyle = "#0a0202";
        for (const s of [-1, 1]) { c.beginPath(); c.moveTo(x, y - 18); c.quadraticCurveTo(x + s * 16, y - 36 - fl * 8, x + s * 26, y - 24 + fl * 10); c.quadraticCurveTo(x + s * 14, y - 18, x + s * 4, y - 10); c.fill(); }
        fig(c, x, y, 30, { ul: 2.6, ur: -2.4, fl: 2.9, fr: -2.8 }, { fill: "#0a0202", rim: "rgba(255,120,60,0.7)", ry: 1 });
      }
      fogBand(c, 560, 100, t, 6, "200,70,30", 0.22, 0);
    },
  });

  // VII. НАСИЛИЕ
  SC.push({
    num: "VII", q: "Uomini fummo, e or siam fatti sterpi", qru: "мы были людьми, а стали терновником", light: "255,120,60",
    init(r) {
      this.flakes = Array.from({ length: 140 }, () => ({ x: r() * 560, y: r(), s: r() }));
      this.boil = Array.from({ length: 12 }, () => ({ x: r() * 560, y: 770 + r() * 80, ph: r() * TAU, d: r() }));
      this.harp = Array.from({ length: 5 }, () => ({ ph: r() * TAU, y: 400 + r() * 200 }));
      this.drip = Array.from({ length: 10 }, (_, i) => ({ tr: SPEC.violenza.trees[(i * 3) % SPEC.violenza.trees.length], ph: r() }));
    },
    draw(c, t) {
      for (const f of this.flakes) { const p = (f.y + t * 0.03 * (0.6 + f.s)) % 1, y = 80 + p * 470, x = f.x + Math.sin(t * 0.6 + f.s * 10) * 12; glow(c, x, y, 5 + f.s * 6, "255,160,60", 0.75); }
      // кентавры вдоль дальнего берега
      for (let i = 0; i < 3; i++) {
        const x = ((t * 26 + i * 220) % 760) - 100, y = 740, g = Math.sin(t * 8 + i);
        c.save(); c.translate(x, y);
        const draw = (col, dx, dy) => {
          c.fillStyle = c.strokeStyle = col; c.lineCap = "round";
          c.beginPath(); c.ellipse(dx, -26 + dy, 26, 11, 0, 0, TAU); c.fill();
          c.lineWidth = 4.5; c.beginPath();
          c.moveTo(-18 + dx, -20 + dy); c.lineTo(-22 - g * 8 + dx, dy); c.moveTo(-12 + dx, -20 + dy); c.lineTo(-8 + g * 8 + dx, dy);
          c.moveTo(14 + dx, -20 + dy); c.lineTo(18 + g * 8 + dx, dy); c.moveTo(20 + dx, -20 + dy); c.lineTo(24 - g * 8 + dx, dy); c.stroke();
          c.lineWidth = 2.5; c.beginPath(); c.moveTo(-26 + dx, -28 + dy); c.quadraticCurveTo(-38 + dx, -24 + dy, -40 + dx, -12 + dy); c.stroke();
        };
        draw("rgba(255,110,60,0.8)", 0, -2); draw("#080202", 0, 0);
        fig(c, 22, -30, 42, { lean: 0.1, ul: 1.7, fl: 1.6, ur: 2.2, fr: 1.4, noLegs: true }, { fill: "#080202", rim: "rgba(255,110,60,0.8)" });
        c.strokeStyle = "#080202"; c.lineWidth = 2; c.beginPath(); c.arc(38, -62, 12, -1.3, 1.3); c.stroke();
        c.restore();
        const ap = (t * 0.7 + i * 0.37) % 1;
        if (ap < 0.5) { const ax = x + 40 + ap * 260, ay = y - 62 - Math.sin(ap / 0.5 * Math.PI) * 40 + ap * 120; c.strokeStyle = "rgba(255,210,160,0.9)"; c.lineWidth = 1.3; c.beginPath(); c.moveTo(ax, ay); c.lineTo(ax - 14, ay - 3); c.stroke(); }
      }
      // гарпии среди деревьев
      for (const h of this.harp) {
        const x = 280 + Math.sin(t * 0.11 + h.ph) * 240, y = h.y + Math.sin(t * 0.5 + h.ph * 3) * 40, fl = Math.sin(t * 6 + h.ph);
        c.fillStyle = "#050101";
        for (const s of [-1, 1]) { c.beginPath(); c.moveTo(x, y); c.quadraticCurveTo(x + s * 18, y - 22 - fl * 14, x + s * 36, y - 6 + fl * 16); c.quadraticCurveTo(x + s * 16, y - 2, x + s * 4, y + 8); c.fill(); }
        c.beginPath(); c.ellipse(x, y + 4, 6, 10, 0, 0, TAU); c.fill(); c.beginPath(); c.arc(x, y - 9, 4.5, 0, TAU); c.fill();
        glow(c, x - 2, y - 10, 3, "255,80,40", 0.8);
      }
      for (const d of this.drip) { const [tx, ty, sc] = d.tr, p = (t * 0.25 + d.ph) % 1; c.fillStyle = `rgba(200,10,10,${0.9 * (1 - p)})`; c.beginPath(); c.ellipse(tx + 12 * sc, ty - 60 * sc + p * 60 * sc, 1.6, 2.6, 0, 0, TAU); c.fill(); }
      // кипящая кровь
      for (const b of this.boil) {
        const bob = Math.sin(t * 1.2 + b.ph) * 3, h = 52 + (b.y - 742) * 0.3, wl = b.y - h * (0.3 + b.d * 0.35) + bob;
        c.save(); c.beginPath(); c.rect(b.x - 50, 0, 100, wl); c.clip();
        fig(c, b.x, b.y + bob, h, { ul: 2.5 + Math.sin(t * 2 + b.ph) * 0.4, fl: 2.9, ur: -2.6, fr: -2.9, head: -0.4 }, { fill: "#140202", rim: "rgba(255,120,90,0.85)", ry: 1 });
        c.restore();
        glow(c, b.x, wl, 18, "255,60,40", 0.4);
        c.strokeStyle = "rgba(255,120,100,0.4)"; c.lineWidth = 1; c.beginPath(); c.ellipse(b.x, wl, 14, 2.5, 0, 0, TAU); c.stroke();
      }
      fogBand(c, 760, 70, t, 9, "255,90,70", 0.25, 0);
    },
  });

  // VIII. ЗЛЫЕ ЩЕЛИ
  SC.push({
    num: "VIII", q: "Luogo è in inferno detto Malebolge", qru: "есть место в аду, зовущееся Злые Щели", light: "200,160,255",
    init(r) { this.rows = SPEC.malebolge.rows.filter((rw) => rw[0] > 330); this.items = this.rows.map((rw, i) => Array.from({ length: 6 }, () => ({ x: r() * 560, ph: r() * TAU, k: r() }))); this.dem = Array.from({ length: 3 }, () => ({ ph: r() * TAU, y: 150 + r() * 150 })); },
    draw(c, t) {
      const vpx = SPEC.malebolge.vpx;
      this.rows.forEach(([y, hgt, gi], ri) => {
        const sc = hgt / 85, base = y + hgt * 0.85, kind = ri % 5;
        this.items[ri].forEach((it, j) => {
          const dir = j % 2 ? 1 : -1;
          let x = ((it.x + t * (kind === 3 ? 3 : 9) * dir * sc) % 600 + 600) % 600 - 20;
          if (Math.abs(x - vpx) < (y - SPEC.malebolge.hor) * 0.16 + 10) return; // под мостом не видно
          if (kind === 0) { // огненные языки лукавых советчиков
            fire(c, x, base, 26 * sc, 70 * sc, t, ri * 7 + j, 0.95);
          } else if (kind === 1) { // процессия лицемеров в золочёных плащах
            const g = c.createLinearGradient(x, base - 60 * sc, x, base); g.addColorStop(0, "#ffe9a0"); g.addColorStop(0.5, "#a77a22"); g.addColorStop(1, "#2a1a06");
            c.fillStyle = g; c.beginPath(); c.moveTo(x, base - 62 * sc); c.quadraticCurveTo(x + 18 * sc, base - 46 * sc, x + 16 * sc, base); c.lineTo(x - 16 * sc, base); c.quadraticCurveTo(x - 18 * sc, base - 46 * sc, x, base - 62 * sc); c.fill();
          } else if (kind === 2) { // воры и змеи
            fig(c, x, base, 70 * sc, { ul: 2.6 + Math.sin(t * 3 + it.ph) * 0.4, fl: 2.9, ur: -2.4, fr: -2.8 }, { fill: "#06100a", rim: "rgba(90,240,140,0.8)" });
            c.strokeStyle = "rgba(80,230,120,0.9)"; c.lineWidth = 2.2 * sc; c.beginPath();
            for (let k = 0; k <= 18; k++) { const a = k / 18 * TAU * 2.2 + t * 2.5; const xx = x + Math.cos(a) * 9 * sc, yy = base - 6 * sc - k * 3.2 * sc; k ? c.lineTo(xx, yy) : c.moveTo(xx, yy); }
            c.stroke();
          } else if (kind === 3) { // смола и бесы с крючьями
            const up = Math.max(0, Math.sin(t * 0.8 + it.ph));
            fig(c, x, base + 40 * sc - up * 24 * sc, 60 * sc, { ul: 2.8, ur: -2.6, fl: 3, fr: -3 }, { fill: "#05030a", rim: "rgba(200,160,255,0.6)" });
            for (let k = 0; k < 2; k++) { const p = (t * 0.5 + it.k + k * 0.5) % 1; c.strokeStyle = `rgba(200,160,255,${0.5 * (1 - p)})`; c.lineWidth = 1; c.beginPath(); c.ellipse(x + 20 * sc, base, 3 + p * 10 * sc, 1 + p * 3 * sc, 0, 0, TAU); c.stroke(); }
          } else { // зачинщики раздора идут по кругу, бес с мечом
            fig(c, x, base, 70 * sc, walkP(t * 3 + it.ph), { fill: "#0c0306", rim: "rgba(255,110,90,0.85)", flip: dir < 0 });
          }
        });
        if (kind === 3) { // бес на краю рва
          const dx = 90 + (ri * 120) % 380, dy = y + 2, k = Math.sin(t * 1.4 + ri);
          fig(c, dx, dy, 90 * sc, { lean: 0.3, ul: 1.6 + k * 0.5, fl: 2.0, ur: 1.3, fr: 1.8 }, { fill: "#05020a", rim: "rgba(200,160,255,0.8)" });
          c.strokeStyle = "#05020a"; c.lineWidth = 2.5 * sc; c.beginPath(); c.moveTo(dx + 10 * sc, dy - 70 * sc); c.lineTo(dx + 50 * sc, dy - 30 * sc + k * 10 * sc); c.lineTo(dx + 44 * sc, dy - 22 * sc + k * 10 * sc); c.stroke();
        }
      });
      // злые бесы (Malebranche) кружат над рвами
      for (const d of this.dem) {
        const x = 280 + Math.sin(t * 0.17 + d.ph) * 230, y = d.y + Math.sin(t * 0.6 + d.ph) * 30, fl = Math.sin(t * 7 + d.ph);
        c.fillStyle = "#06030c";
        for (const s of [-1, 1]) { c.beginPath(); c.moveTo(x, y); c.lineTo(x + s * 14, y - 18 - fl * 10); c.lineTo(x + s * 30, y - 10 - fl * 14); c.lineTo(x + s * 22, y + 2); c.lineTo(x + s * 26, y + 6 + fl * 6); c.lineTo(x + s * 6, y + 6); c.fill(); }
        fig(c, x, y + 18, 34, { ul: 0.6, ur: -0.6, tl: -0.4, tr: 0.5 }, { fill: "#06030c" });
        c.beginPath(); c.moveTo(x - 3, y - 13); c.lineTo(x - 5, y - 20); c.lineTo(x - 1, y - 14); c.moveTo(x + 3, y - 13); c.lineTo(x + 5, y - 20); c.lineTo(x + 1, y - 14); c.fill();
      }
      fogBand(c, 300, 120, t, 5, "150,110,220", 0.2, 0);
    },
  });

  // IX. ПРЕДАТЕЛЬСТВО
  SC.push({
    num: "IX", q: "Lo 'mperador del doloroso regno", qru: "владыка скорбного царства", light: "170,215,255",
    init(r) { this.heads = Array.from({ length: 26 }, () => { const y = 640 + r() * 220; return { x: r() * 560, y, s: 0.5 + (y - 600) / 280, up: r() < 0.5, ph: r() * TAU }; }).sort((a, b) => a.y - b.y); this.snow = Array.from({ length: 260 }, () => ({ x: r(), y: r() * 930, s: r() })); },
    lucifer(c, t, mirror) {
      const flap = Math.sin(t * 0.55);
      c.save(); c.translate(280, 600); if (mirror) c.scale(1, -0.6);
      const dark = "#03070d", rim = "rgba(170,215,255,0.75)";
      const wing = (s, layer, col, dx, dy) => {
        const sp = 1 - layer * 0.16, a = flap * (0.22 + layer * 0.06), base = -300 + layer * 46;
        c.fillStyle = col; c.beginPath();
        c.moveTo(s * 40 + dx, base + 40 + dy);
        const tipx = s * 330 * sp, tipy = base - 120 * sp - a * 160;
        c.quadraticCurveTo(s * 150 * sp + dx, base - 140 * sp - a * 90 + dy, tipx + dx, tipy + dy);
        for (let k = 1; k <= 4; k++) { const fx = s * (330 - k * 66) * sp, fy = base + 70 + a * 60 * (1 - k / 5); c.quadraticCurveTo(fx + s * 34 * sp + dx, fy - 70 + dy, fx + dx, fy + dy); }
        c.closePath(); c.fill();
        c.strokeStyle = col; c.lineWidth = 3;
        for (let k = 0; k <= 4; k++) { const fx = s * (330 - k * 66) * sp, fy = base + 70 + a * 60 * (1 - k / 5); c.beginPath(); c.moveTo(s * 50 + dx, base + 30 + dy); c.lineTo((k ? fx : tipx) + dx, (k ? fy : tipy) + dy); c.stroke(); }
      };
      for (let layer = 2; layer >= 0; layer--) for (const s of [-1, 1]) { wing(s, layer, rim, 0, -2.5); wing(s, layer, ["#050b14", "#040910", dark][layer], 0, 0); }
      const torso = (col, dx, dy) => {
        c.fillStyle = col; c.beginPath(); c.moveTo(-110 + dx, 20 + dy); c.bezierCurveTo(-120 + dx, -120 + dy, -90 + dx, -230 + dy, -50 + dx, -268 + dy); c.lineTo(50 + dx, -268 + dy); c.bezierCurveTo(90 + dx, -230 + dy, 120 + dx, -120 + dy, 110 + dx, 20 + dy); c.fill();
        for (const [fx, fy, rot] of [[-52, -292, -0.35], [0, -306, 0], [52, -292, 0.35]]) {
          c.save(); c.translate(fx + dx, fy + dy); c.rotate(rot);
          c.beginPath(); c.ellipse(0, 0, 26, 32, 0, 0, TAU); c.fill();
          c.beginPath(); c.moveTo(-14, -22); c.quadraticCurveTo(-30, -50, -20, -66); c.quadraticCurveTo(-16, -44, -4, -28); c.fill();
          c.beginPath(); c.moveTo(14, -22); c.quadraticCurveTo(30, -50, 20, -66); c.quadraticCurveTo(16, -44, 4, -28); c.fill();
          c.restore();
        }
      };
      torso(rim, 0, -2.5); torso(dark, 0, 0);
      // три лица: глаза — красный, жёлто-белый, чёрный (тусклый)
      const eyes = [[-52, -292, -0.35, "255,230,150"], [0, -306, 0, "255,50,20"], [52, -292, 0.35, "120,140,170"]];
      for (const [fx, fy, rot, col] of eyes) {
        for (const ex of [-9, 9]) glow(c, fx + Math.cos(rot) * ex, fy - 6 + Math.sin(rot) * ex, 7, col, 0.95);
        const chew = Math.abs(Math.sin(t * 1.6 + fx)) * 8;
        c.fillStyle = "#000"; c.beginPath(); c.ellipse(fx, fy + 14, 11, 3 + chew * 0.4, rot, 0, TAU); c.fill();
        const tear = (t * 0.4 + fx * 0.01) % 1; glow(c, fx - 10, fy - 2 + tear * 30, 3, "180,220,255", 0.8 * (1 - tear));
      }
      // Иуда: ноги бьются из средней пасти; Брут и Кассий — из боковых
      const kk = Math.sin(t * 3) * 0.4;
      c.strokeStyle = "#0b1420"; c.lineCap = "round";
      c.lineWidth = 7; c.beginPath(); c.moveTo(-4, -292); c.lineTo(-12 - kk * 14, -248); c.lineTo(-10 - kk * 20, -222); c.moveTo(4, -292); c.lineTo(14 + kk * 14, -250); c.lineTo(10 + kk * 22, -226); c.stroke();
      c.lineWidth = 6; c.beginPath(); c.moveTo(-58, -278); c.lineTo(-84, -246 + kk * 10); c.moveTo(58, -278); c.lineTo(84, -246 - kk * 10); c.stroke();
      c.restore();
    },
    draw(c, t, active, front) {
      if (!front) {
        glow(c, 280, 360, 260, "120,170,230", 0.25);
        this.lucifer(c, t, false);
        return;
      }
      // после льда: отражение Люцифера, головы во льду, позёмка
      c.save(); c.globalAlpha = 0.18; c.beginPath(); c.rect(0, 598, WIN_W, 200); c.clip(); c.translate(0, 1196); this.lucifer(c, t, true); c.restore();
      for (const h of this.heads) {
        const sh = Math.sin(t * 9 + h.ph) * 0.5 * h.s, r = 9 * h.s;
        c.fillStyle = "#081420"; c.beginPath(); c.ellipse(h.x + sh, h.y - r * 0.7, r * 0.85, r, h.up ? -0.4 : 0.3, 0, TAU); c.fill();
        c.strokeStyle = "rgba(200,235,255,0.7)"; c.lineWidth = 1.2 * h.s; c.beginPath(); c.ellipse(h.x + sh, h.y - r * 0.7, r * 0.85, r, h.up ? -0.4 : 0.3, Math.PI * 1.1, Math.PI * 1.9); c.stroke();
        c.fillStyle = "rgba(220,240,255,0.55)"; c.beginPath(); c.ellipse(h.x, h.y, r * 1.6, r * 0.35, 0, 0, TAU); c.fill();
        if (h.up) glow(c, h.x + sh - r * 0.3, h.y - r * 1.0, 3 * h.s, "200,240,255", 0.7);
      }
      // Уголино грызёт голову Руджери
      const ux = 140, uy = 760, g = Math.abs(Math.sin(t * 2.2)) * 3;
      c.fillStyle = "#081420"; c.beginPath(); c.ellipse(ux, uy - 8, 9, 11, 0.4, 0, TAU); c.fill(); c.beginPath(); c.ellipse(ux + 14 - g, uy - 12 + g * 0.3, 9, 11, -0.6, 0, TAU); c.fill();
      c.strokeStyle = "rgba(200,235,255,0.7)"; c.lineWidth = 1.2; c.beginPath(); c.ellipse(ux + 14 - g, uy - 12 + g * 0.3, 9, 11, -0.6, Math.PI, Math.PI * 1.8); c.stroke();
      glow(c, ux + 6, uy - 6, 6, "200,30,30", 0.5);
      // ледяной ветер от крыльев
      const wind = 0.6 + 0.4 * Math.sin(t * 0.55 + 1);
      c.strokeStyle = `rgba(210,235,255,${0.25 * wind})`; c.lineWidth = 1; c.beginPath();
      for (const s of this.snow) { const x = ((s.x + t * 0.05 * (1 + s.s) * wind) % 1) * 640 - 40, y = s.y + Math.sin(t + s.s * 20) * 8; c.moveTo(x, y); c.lineTo(x + 6 + s.s * 18 * wind, y + 1); }
      c.stroke();
      fogBand(c, 600, 80, t, 14, "190,225,245", 0.22, 0);
    },
  });

  // ======================================================================
  const cv = document.getElementById("inferno"), ctx = cv.getContext("2d");
  const IM = {};
  let DPR = 1, CW = 0, CH = 0, panels = [], mode = String(cfg.screen), ready = false;

  function loadImages() {
    const names = [];
    for (let i = 1; i <= 9; i++) names.push("plate_" + i);
    names.push("front_9", "frame_1", "frame_2", "frame_3");
    return Promise.all(names.map((n) => new Promise((res) => { const im = new Image(); im.onload = () => { IM[n] = im; res(); }; im.onerror = () => res(); im.src = BASE + n + ".webp"; })));
  }

  function archPath(c, i) {
    const x0 = GAP + i * (WIN_W + GAP), w = WIN_W, r = 0.62 * WIN_W;
    const h = Math.sqrt(r * r - (r - w / 2) ** 2), ys = TOP + h;
    c.beginPath(); c.moveTo(x0, TOP + WIN_H);
    for (let k = 0; k <= 40; k++) { const x = x0 + (k / 40) * w / 2; c.lineTo(x, ys - Math.sqrt(Math.max(0, r * r - (x - (x0 + r)) ** 2))); }
    for (let k = 0; k <= 40; k++) { const x = x0 + w / 2 + (k / 40) * w / 2; c.lineTo(x, ys - Math.sqrt(Math.max(0, r * r - (x - (x0 + w - r)) ** 2))); }
    c.lineTo(x0 + w, TOP + WIN_H); c.closePath();
  }

  function layout() {
    DPR = Math.min(2, window.devicePixelRatio || 1);
    CW = window.innerWidth; CH = window.innerHeight;
    cv.width = Math.round(CW * DPR); cv.height = Math.round(CH * DPR);
    cv.style.width = CW + "px"; cv.style.height = CH + "px";
    panels = [];
    const wide = mode === "all" || (mode === "auto" && CW / CH > 4);
    const n = wide ? 3 : 1, pw = CW / n;
    for (let g = 0; g < n; g++) {
      const s = Math.min(pw / 1920, CH / 1080);
      panels.push({ ox: g * pw + (pw - 1920 * s) / 2, oy: (CH - 1080 * s) / 2, s, group: wide ? g : mode === "auto" ? -1 : clamp((+mode || 1) - 1, 0, 2) });
    }
  }

  function clock() {
    const now = cfg.t !== undefined ? +cfg.t + performance.now() / 1000 : Date.now() / 1000;
    const p = ((now % cfg.cycle) + cfg.cycle) % cfg.cycle, seg = (cfg.cycle - OUTRO) / 9;
    const ci = Math.min(8, Math.floor(p / seg));
    return { now, ci, prog: p < cfg.cycle - OUTRO ? (p - ci * seg) / seg : 1, outro: p >= cfg.cycle - OUTRO ? (p - (cfg.cycle - OUTRO)) / OUTRO : -1 };
  }

  function drawWindow(i, idx, t, active, prog, outro) {
    const sc = SC[idx], x0 = GAP + i * (WIN_W + GAP);
    ctx.save(); archPath(ctx, i); ctx.clip();
    ctx.translate(x0, TOP);
    const plate = IM["plate_" + (idx + 1)];
    if (plate) ctx.drawImage(plate, 0, 0, WIN_W, WIN_H);
    if (idx === 8) sc.draw(ctx, t, active, false); else sc.draw(ctx, t, active);
    if (idx === 8 && IM.front_9) { ctx.drawImage(IM.front_9, 0, 0, WIN_W, WIN_H); sc.draw(ctx, t, active, true); }
    if (active) {
      const pos = sc.path ? sc.path(prog) : { x: -50 + prog * (WIN_W + 100), y: PATH_Y };
      const ph = t * 4.2;
      if (pos.boat) { SC[4].boat(ctx, pos.x, pos.y, t, 0.85); poet(ctx, pos.x - 4, pos.y - 6, 64, 0, "virgil", sc.light); poet(ctx, pos.x - 34, pos.y - 6, 64, 0, "dante", sc.light); }
      else if (idx === 8 && prog > 0.72) { const x = lerp(-50 + 0.72 * (WIN_W + 100), 200, smooth((prog - 0.72) / 0.28)); poet(ctx, x, PATH_Y, 72, ph * (prog < 0.98 ? 1 : 0), "virgil", sc.light); poet(ctx, x - 34, PATH_Y, 72, ph + 1.4, "dante", sc.light); }
      else { poet(ctx, pos.x, pos.y, 72, ph, "virgil", sc.light); poet(ctx, pos.x - 34, pos.y, 72, ph + 1.4, "dante", sc.light); }
      if (cfg.quotes) {
        const a = smooth(clamp(prog * 7, 0, 1)) * smooth(clamp((1 - prog) * 7, 0, 1));
        if (a > 0) {
          ctx.save(); ctx.globalAlpha = a; ctx.textAlign = "center";
          const g = ctx.createLinearGradient(0, 360, 0, 470); g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(0.5, "rgba(0,0,0,0.35)"); g.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = g; ctx.fillRect(0, 360, WIN_W, 110);
          ctx.shadowColor = "rgba(0,0,0,0.9)"; ctx.shadowBlur = 8;
          ctx.fillStyle = "rgba(255,244,228,0.95)"; ctx.font = "italic 25px 'Cormorant Garamond', Georgia, serif";
          wrap(ctx, "«" + sc.q + "»", WIN_W / 2, 408, 470, 28);
          ctx.fillStyle = "rgba(230,214,200,0.85)"; ctx.font = "16px 'Cormorant Garamond', Georgia, serif";
          ctx.fillText(sc.qru, WIN_W / 2, 452);
          ctx.restore();
        }
      }
    }
    if (outro >= 0) stars(ctx, outro, t, i);
    ctx.restore();
  }

  function wrap(c, text, x, y, maxW, lh) {
    const words = text.split(" "); let line = "", lines = [];
    for (const w of words) { const test = line ? line + " " + w : w; if (c.measureText(test).width > maxW && line) { lines.push(line); line = w; } else line = test; }
    lines.push(line);
    lines.forEach((l, k) => c.fillText(l, x, y + (k - (lines.length - 1) / 2) * lh));
  }

  function stars(c, o, t, i) {
    const a = smooth(clamp(o * 4, 0, 1)) * smooth(clamp((1 - o) * 3, 0, 1));
    c.save(); c.globalAlpha = a;
    const g = c.createLinearGradient(0, 0, 0, WIN_H); g.addColorStop(0, "#02040c"); g.addColorStop(1, "#0b1530");
    c.fillStyle = g; c.fillRect(0, 0, WIN_W, WIN_H);
    const r = rngf(9 + i);
    for (let k = 0; k < 260; k++) { const x = r() * WIN_W, y = r() * WIN_H, s = r() * r() * 2.2 + 0.4; c.fillStyle = `rgba(255,250,235,${0.4 + 0.6 * r() * (0.6 + 0.4 * Math.sin(t * 2 + k))})`; c.fillRect(x, y, s, s); }
    if (i === 1) {
      for (const [sx, sy] of [[-40, -70], [12, 34], [-64, -6], [44, -22]]) glow(c, 280 + sx, 330 + sy, 26, "255,252,235", 1);
      c.textAlign = "center"; c.fillStyle = "rgba(240,240,255,0.95)"; c.font = "italic 30px 'Cormorant Garamond', Georgia, serif";
      c.fillText("e quindi uscimmo", 280, 560); c.fillText("a riveder le stelle", 280, 598);
      c.fillStyle = "rgba(200,210,235,0.8)"; c.font = "17px 'Cormorant Garamond', Georgia, serif";
      c.fillText("И здесь мы вышли вновь узреть светила.", 280, 640);
    }
    c.restore();
  }

  let last = 0;
  function frame(ts) {
    requestAnimationFrame(frame);
    if (!ready || ts - last < 1000 / cfg.fps - 2) return;
    last = ts;
    const { now, ci, prog, outro } = clock();
    const t = now % 100000;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = "#070605"; ctx.fillRect(0, 0, cv.width, cv.height);
    for (const P of panels) {
      const group = P.group >= 0 ? P.group : Math.floor(ci / 3);
      ctx.setTransform(DPR * P.s, 0, 0, DPR * P.s, DPR * P.ox, DPR * P.oy);
      for (let i = 0; i < 3; i++) { const idx = group * 3 + i; drawWindow(i, idx, t, idx === ci && outro < 0, prog, outro); }
      const fr = IM["frame_" + (group + 1)];
      if (fr) ctx.drawImage(fr, 0, 0, 1920, 1080);
      // активная табличка светится
      if (outro < 0 && Math.floor(ci / 3) === group) {
        const i = ci % 3, cx = GAP + i * (WIN_W + GAP) + WIN_W / 2;
        glow(ctx, cx, 1000, 120, "255,190,110", 0.22 + 0.06 * Math.sin(t * 2));
        ctx.strokeStyle = "rgba(255,200,120,0.55)"; ctx.lineWidth = 1.5; ctx.save(); archPath(ctx, i); ctx.stroke(); ctx.restore();
      }
    }
  }

  function setProp(name, val) {
    if (name === "screen") { mode = typeof val === "number" ? ["1", "2", "3", "all", "auto"][val] || "auto" : String(val); layout(); }
    if (name === "cycle") cfg.cycle = Math.min(1200, Math.max(120, +val * 60 || 540));
    if (name === "quotes") cfg.quotes = !!val;
    if (name === "fps") cfg.fps = +val || 30;
  }
  window.livelyPropertyListener = setProp;
  window.wallpaperPropertyListener = { applyUserProperties(p) { for (const k in p) if (p[k] && "value" in p[k]) setProp(k, p[k].value); } };

  makeFlames(); makeFog();
  const R = rngf(2024); SC.forEach((s) => s.init(R));
  window.addEventListener("resize", layout);
  layout();
  loadImages().then(() => { ready = true; });
  requestAnimationFrame(frame);
})();
