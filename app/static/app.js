/* Golf Campestre — web app instalable (sin frameworks). */
"use strict";

// ------------------------------------------------------------ utilidades
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const app = $("#app");
let timerRefresco = null;

function toast(msg, ms = 2200) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("ver");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("ver"), ms);
}

function vsPar(n) {
  if (n === 0) return "E";
  return n > 0 ? `+${n}` : `${n}`;
}
const clsPar = (n) => (n < 0 ? "bajo" : "");
const dinero = (n) => {
  const v = Number(n || 0);
  return `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString("es-MX", { maximumFractionDigits: 2 })}`;
};
const fechaCorta = (s) => {
  if (!s) return "";
  const [y, m, d] = s.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};
const hoyISO = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

const store = {
  get: (k, def = null) => { try { const v = localStorage.getItem(k); return v === null ? def : JSON.parse(v); } catch { return def; } },
  set: (k, v) => localStorage.setItem(k, JSON.stringify(v)),
  del: (k) => localStorage.removeItem(k),
};

class ApiError extends Error {
  constructor(status, msg) { super(msg); this.status = status; }
}

async function api(path, { method = "GET", body, token } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let r;
  try {
    r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Sin conexión. Revisa tu señal.");
  }
  let data = null;
  try { data = await r.json(); } catch { /* sin cuerpo */ }
  if (!r.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((e) => e.msg).join(". ");
    throw new ApiError(r.status, msg || `Error ${r.status}`);
  }
  return data;
}

const adminToken = () => store.get("admin_token");
const adminApi = async (path, opts = {}) => {
  try {
    return await api(`/api/admin${path}`, { ...opts, token: adminToken() });
  } catch (e) {
    if (e.status === 401) { store.del("admin_token"); location.hash = "#/admin"; }
    throw e;
  }
};

function render(html) { app.innerHTML = html; window.scrollTo(0, 0); }
function errorHTML(e) { return `<div class="error-box">${esc(e.message || e)}</div>`; }

function titulo(texto, atras = null) {
  $("#titulo").textContent = texto;
  const b = $("#atras");
  b.hidden = !atras;
  b.onclick = () => { location.hash = atras; };
}

function tabActiva(tab) {
  $$("#nav a").forEach((a) => a.classList.toggle("activo", a.dataset.tab === tab));
}

function estadoRed(texto, tipo = "") {
  const p = $("#estado-red");
  p.hidden = !texto;
  p.textContent = texto || "";
  p.className = `pill ${tipo}`;
}

// ------------------------------------------------------------ router
const rutas = [
  [/^#?\/?$/, vistaTorneos],
  [/^#\/t\/(\d+)$/, vistaTorneo],
  [/^#\/t\/(\d+)\/capturar$/, vistaCaptura],
  [/^#\/t\/(\d+)\/g\/(\d+)\/apuestas$/, vistaApuestas],
  [/^#\/jugadores$/, vistaJugadores],
  [/^#\/j\/(\d+)$/, vistaJugador],
  [/^#\/admin$/, vistaAdmin],
  [/^#\/admin\/recorridos$/, vistaAdminRecorridos],
  [/^#\/admin\/r\/(\d+)$/, vistaAdminRecorrido],
  [/^#\/admin\/jugadores$/, vistaAdminJugadores],
  [/^#\/admin\/torneos$/, vistaAdminTorneos],
  [/^#\/admin\/t\/(\d+)$/, vistaAdminTorneo],
  [/^#\/admin\/t\/(\d+)\/g\/(\d+)$/, vistaAdminCaptura],
];

async function ruta() {
  clearInterval(timerRefresco);
  timerRefresco = null;
  estadoRed("");
  const h = location.hash || "#/";
  for (const [re, fn] of rutas) {
    const m = h.match(re);
    if (m) {
      try { await fn(...m.slice(1).map(Number)); } catch (e) { render(errorHTML(e)); }
      return;
    }
  }
  location.hash = "#/";
}
window.addEventListener("hashchange", ruta);

// ------------------------------------------------------------ torneos
async function vistaTorneos() {
  titulo("Golf Campestre");
  tabActiva("torneos");
  render(`<div class="cargando">Cargando torneos…</div>`);
  const ts = await api("/api/torneos");
  if (!ts.length) {
    render(`<div class="vacio">Aún no hay torneos.<br><br><a class="btn" href="#/admin">Crear uno en Admin</a></div>`);
    return;
  }
  render(ts.map((t) => `
    <a class="card" href="#/t/${t.id}">
      <div class="fila">
        <div class="crece"><h3>${esc(t.nombre)}</h3>
          <div class="muted">${fechaCorta(t.fecha)} · ${esc(t.recorrido)} · ${t.jugadores} jugadores</div></div>
        <span class="pill ${t.estado === "cerrado" ? "cerrado" : ""}">${t.estado === "cerrado" ? "Final" : "En juego"}</span>
      </div>
    </a>`).join(""));
}

const NOMBRE_FMT = { gross: "Gross", neto: "Neto", stableford: "Stableford" };

async function vistaTorneo(tid) {
  tabActiva("torneos");
  titulo("Torneo", "#/");
  render(`<div class="cargando">Cargando…</div>`);
  const tr = await api(`/api/torneos/${tid}`);
  titulo(tr.nombre, "#/");
  let formato = store.get(`fmt:${tid}`, tr.formato);
  let pestaña = "lb";
  const abiertos = new Set();

  async function dibujar() {
    let cuerpo = "";
    if (pestaña === "lb") {
      const lb = await api(`/api/torneos/${tid}/leaderboard?formato=${formato}`);
      cuerpo = leaderboardHTML(lb, formato, abiertos);
    } else {
      cuerpo = tr.grupos.length ? tr.grupos.map((g) => {
        const js = tr.participantes.filter((p) => p.grupo_id === g.id);
        return `<div class="card"><div class="fila"><div class="crece"><h3>${esc(g.nombre)}</h3>
          <div class="muted">Sale del hoyo ${g.hoyo_salida}${g.hora_salida ? " · " + esc(g.hora_salida) : ""}</div></div>
          ${g.apuestas ? `<a class="btn chico sec" href="#/t/${tid}/g/${g.id}/apuestas">💰 Apuestas</a>` : ""}</div>
          <div class="muted" style="margin-top:6px">${js.map((p) => esc(p.nombre)).join(" · ") || "Sin jugadores"}</div></div>`;
      }).join("") : `<div class="vacio">Sin grupos todavía.</div>`;
    }
    render(`
      <div class="card fila"><div class="crece">
        <div class="muted">${fechaCorta(tr.fecha)} · ${esc(tr.recorrido)} · Hcp ${tr.pct_handicap}%</div></div>
        <span class="pill ${tr.estado === "cerrado" ? "cerrado" : ""}">${tr.estado === "cerrado" ? "Final" : "En juego"}</span></div>
      ${tr.estado === "abierto" ? `<a class="btn bloque" href="#/t/${tid}/capturar" style="margin-bottom:12px">✏️ Capturar score de mi grupo</a>` : ""}
      <div class="tabs"><button data-p="lb" class="${pestaña === "lb" ? "activo" : ""}">Leaderboard</button>
        <button data-p="gr" class="${pestaña === "gr" ? "activo" : ""}">Grupos y apuestas</button></div>
      ${pestaña === "lb" ? `<div class="tabs">${["gross", "neto", "stableford"].map((f) =>
        `<button data-f="${f}" class="${f === formato ? "activo" : ""}">${NOMBRE_FMT[f]}</button>`).join("")}</div>` : ""}
      ${cuerpo}
      <p class="muted" style="text-align:center">Se actualiza solo cada 20 segundos</p>`);
    $$("[data-p]").forEach((b) => (b.onclick = () => { pestaña = b.dataset.p; dibujar(); }));
    $$("[data-f]").forEach((b) => (b.onclick = () => { formato = b.dataset.f; store.set(`fmt:${tid}`, formato); dibujar(); }));
    $$("tr[data-pid]").forEach((row) => (row.onclick = () => {
      const id = Number(row.dataset.pid);
      abiertos.has(id) ? abiertos.delete(id) : abiertos.add(id);
      dibujar();
    }));
  }
  await dibujar();
  timerRefresco = setInterval(() => {
    if (document.visibilityState === "visible" && pestaña === "lb") dibujar().catch(() => {});
  }, 20000);
}

function leaderboardHTML(lb, formato, abiertos) {
  if (!lb.filas.length) return `<div class="vacio">Aún no hay jugadores inscritos.</div>`;
  const filas = lb.filas.map((f) => {
    const thru = f.jugados === 18 ? "F" : f.jugados || "—";
    const principal = formato === "stableford" ? `<td class="principal">${f.jugados ? f.stableford : "—"}</td>`
      : formato === "gross" ? `<td class="principal ${clsPar(f.gross_vs_par)}">${f.jugados ? vsPar(f.gross_vs_par) : "—"}</td>`
        : `<td class="principal ${clsPar(f.neto_vs_par)}">${f.jugados ? vsPar(f.neto_vs_par) : "—"}</td>`;
    const det = abiertos.has(f.id) ? `<tr class="det"><td colspan="5">${tarjetaHTML(lb.hoyos, [f])}</td></tr>` : "";
    return `<tr data-pid="${f.id}" style="cursor:pointer">
      <td class="pos">${esc(f.posicion)}</td>
      <td class="nom"><span class="tee-dot" style="background:${esc(f.tee_color)}"></span><b>${esc(f.nombre)}</b>
        <div class="muted">Hcp ${f.hcp_juego}${f.grupo ? " · " + esc(f.grupo) : ""}</div></td>
      <td>${thru}</td>${principal}
      <td class="muted">${f.jugados ? (formato === "gross" ? f.neto : f.gross) : ""}</td></tr>${det}`;
  }).join("");
  const sec = formato === "gross" ? "Neto" : "Gross";
  return `<div class="card" style="padding:4px 8px"><table class="lb">
    <tr><th></th><th class="nom">Jugador</th><th>Hoyo</th><th>${NOMBRE_FMT[formato]}</th><th>${sec}</th></tr>${filas}</table></div>
    <p class="muted" style="text-align:center">Toca un jugador para ver su tarjeta</p>`;
}

function claseScore(g, par) {
  if (g == null) return "";
  const d = g - par;
  return d <= -2 ? "s-eagle" : d === -1 ? "s-birdie" : d === 1 ? "s-bogey" : d >= 2 ? "s-doble" : "";
}

/** Tarjeta clásica por hoyos. jugadores: [{nombre, hoyos:[{hoyo, golpes, neto, recibe, stableford}]}] */
function tarjetaHTML(hoyos, jugadores) {
  const mitad = (desde, hasta, etiqueta) => {
    const hs = hoyos.filter((h) => h.numero >= desde && h.numero <= hasta);
    const sum = (arr) => arr.reduce((a, b) => a + (b || 0), 0);
    let html = `<tr><th>Hoyo</th>${hs.map((h) => `<th>${h.numero}</th>`).join("")}<th class="tot">${etiqueta}</th></tr>`;
    html += `<tr><td>Par</td>${hs.map((h) => `<td>${h.par}</td>`).join("")}<td class="tot">${sum(hs.map((h) => h.par))}</td></tr>`;
    html += `<tr><td class="muted">Hcp</td>${hs.map((h) => `<td class="muted">${h.handicap}</td>`).join("")}<td class="tot"></td></tr>`;
    for (const j of jugadores) {
      const det = Object.fromEntries((j.hoyos || []).map((x) => [x.hoyo, x]));
      const gs = hs.map((h) => det[h.numero]?.golpes);
      html += `<tr><td><b>${esc(j.nombre.split(" ")[0])}</b></td>${hs.map((h, i) =>
        `<td class="${claseScore(gs[i], h.par)}">${gs[i] ?? ""}${det[h.numero]?.recibe > 0 ? "<sup>•</sup>" : ""}</td>`).join("")}
        <td class="tot">${sum(gs) || ""}</td></tr>`;
      const ns = hs.map((h) => det[h.numero]?.neto);
      html += `<tr><td class="muted">Neto</td>${ns.map((n) => `<td class="muted">${n ?? ""}</td>`).join("")}<td class="tot muted">${sum(ns) || ""}</td></tr>`;
      const ps = hs.map((h) => det[h.numero]?.stableford);
      html += `<tr><td class="muted">Stb</td>${ps.map((n) => `<td class="muted">${n ?? ""}</td>`).join("")}<td class="tot muted">${sum(ps) || ""}</td></tr>`;
    }
    return html;
  };
  return `<div class="tarjeta"><table>${mitad(1, 9, "Ida")}</table></div>
          <div class="tarjeta" style="margin-top:6px"><table>${mitad(10, 18, "Vuelta")}</table></div>
          <div class="muted" style="margin-top:4px">• = recibe golpe en ese hoyo</div>`;
}

// ------------------------------------------------------------ captura
async function vistaCaptura(tid) {
  tabActiva("torneos");
  titulo("Capturar score", `#/t/${tid}`);
  const clave = `grupo_token:${tid}`;
  if (!store.get(clave)) return pantallaPin(tid, clave);
  await capturador({
    tid,
    volver: `#/t/${tid}`,
    colaKey: `cola:${tid}`,
    cacheKey: `tarjeta:${tid}`,
    cargar: () => api("/api/grupo", { token: store.get(clave) }),
    guardar: (lista) => api("/api/grupo/scores", { method: "PUT", body: lista, token: store.get(clave) }),
    alExpirar: () => { store.del(clave); pantallaPin(tid, clave); },
  });
}

function pantallaPin(tid, clave) {
  let pin = "";
  const dibujar = (error = "") => {
    render(`<div class="card" style="text-align:center">
      <h2>PIN de tu grupo</h2><div class="muted">Pídelo al organizador del torneo (6 dígitos)</div>
      <div class="pin-dots">${[0, 1, 2, 3, 4, 5].map((i) => `<i class="${i < pin.length ? "lleno" : ""}"></i>`).join("")}</div>
      ${error ? `<div class="error-box">${esc(error)}</div>` : ""}
      <div class="teclado">${[1, 2, 3, 4, 5, 6, 7, 8, 9, "", 0, "⌫"].map((k) =>
        k === "" ? "<span></span>" : `<button data-k="${k}">${k}</button>`).join("")}</div></div>`);
    $$("[data-k]").forEach((b) => (b.onclick = async () => {
      const k = b.dataset.k;
      if (k === "⌫") pin = pin.slice(0, -1);
      else if (pin.length < 6) pin += k;
      if (pin.length < 6) return dibujar();
      dibujar();
      try {
        const r = await api(`/api/torneos/${tid}/acceso`, { method: "POST", body: { pin } });
        store.set(clave, r.token);
        toast(`Entraste a ${r.grupo}`);
        vistaCaptura(tid);
      } catch (e) {
        pin = "";
        dibujar(e.message);
      }
    }));
  };
  dibujar();
}

/** Pantalla de captura hoyo por hoyo, con cola sin señal. */
async function capturador(ctx) {
  let data;
  try {
    data = await ctx.cargar();
    store.set(ctx.cacheKey, data);
  } catch (e) {
    if (e.status === 401) return ctx.alExpirar();
    data = store.get(ctx.cacheKey);
    if (!data) throw e;
    toast("Sin señal: mostrando lo último guardado en el teléfono");
  }
  titulo(data.grupo.nombre, ctx.volver);
  const hoyos = Object.fromEntries(data.hoyos.map((h) => [h.numero, h]));
  const orden = Array.from({ length: 18 }, (_, i) => ((data.grupo.hoyo_salida - 1 + i) % 18) + 1);
  const jugadores = data.participantes;
  const cerrado = data.torneo.estado !== "abierto";

  // scores locales = servidor + cola pendiente
  const sc = {};
  for (const p of jugadores) {
    sc[p.id] = {};
    for (const [h, s] of Object.entries(p.scores || {})) sc[p.id][h] = { ...s };
  }
  let cola = store.get(ctx.colaKey, []);
  for (const c of cola) {
    if (!sc[c.participante_id]) continue;
    if (c.golpes == null) delete sc[c.participante_id][c.hoyo];
    else sc[c.participante_id][c.hoyo] = { golpes: c.golpes, putts: c.putts, fairway: c.fairway };
  }
  const completo = (h) => jugadores.every((p) => sc[p.id][h]?.golpes);
  let actual = Number(store.get(`${ctx.colaKey}:hoyo`)) || orden.find((h) => !completo(h)) || orden[0];
  let verStats = store.get("ver_stats", false);

  function pintarRed() {
    if (cola.length) estadoRed(navigator.onLine ? `⏳ ${cola.length} por enviar` : `Sin señal · ${cola.length}`, "alerta");
    else estadoRed("✓ Guardado");
  }

  let enviando = false;
  let timerEnvio = null;
  async function enviar() {
    if (enviando || !cola.length) return pintarRed();
    enviando = true;
    const lote = cola.slice();
    try {
      await ctx.guardar(lote);
      // quita solo lo enviado (si no cambió mientras tanto)
      cola = store.get(ctx.colaKey, []).filter((c) => !lote.some((l) => JSON.stringify(l) === JSON.stringify(c)));
      store.set(ctx.colaKey, cola);
    } catch (e) {
      if (e.status === 401) { enviando = false; return ctx.alExpirar(); }
      if (e.status && e.status !== 0) {
        toast(e.message, 4000);
        if (e.status === 409 || e.status === 403 || e.status === 422) { cola = []; store.set(ctx.colaKey, cola); }
      }
    }
    enviando = false;
    pintarRed();
  }
  const programarEnvio = () => { clearTimeout(timerEnvio); timerEnvio = setTimeout(enviar, 700); pintarRed(); };
  window.addEventListener("online", enviar, { once: true });
  timerRefresco = setInterval(enviar, 15000);

  function cambiar(pid, cambio) {
    const h = actual;
    const prev = sc[pid][h] || { golpes: null, putts: null, fairway: null };
    const nuevo = { ...prev, ...cambio };
    if (nuevo.golpes == null) delete sc[pid][h];
    else sc[pid][h] = nuevo;
    cola = cola.filter((c) => !(c.participante_id === pid && c.hoyo === h));
    cola.push({ participante_id: pid, hoyo: h, golpes: nuevo.golpes ?? null,
      putts: nuevo.golpes == null ? null : nuevo.putts ?? null, fairway: nuevo.golpes == null ? null : nuevo.fairway ?? null });
    store.set(ctx.colaKey, cola);
    programarEnvio();
    dibujar();
  }

  function totales(p) {
    let g = 0, par = 0, n = 0;
    for (const [h, s] of Object.entries(sc[p.id])) { g += s.golpes; par += hoyos[h].par; n++; }
    return { g, vs: g - par, n };
  }

  function dibujar() {
    const h = hoyos[actual];
    store.set(`${ctx.colaKey}:hoyo`, actual);
    const idx = orden.indexOf(actual);
    render(`
      ${cerrado ? `<div class="aviso">El torneo está cerrado; ya no se pueden cambiar scores.</div>` : ""}
      <div class="hoyos-chips">${orden.map((n) =>
        `<button data-h="${n}" class="${n === actual ? "actual" : completo(n) ? "hecho" : ""}">${n}</button>`).join("")}</div>
      <div class="hoyo-info">
        <div><div class="num">${actual}</div><span style="font-size:12px;opacity:.85">HOYO</span></div>
        <div class="dato"><b>${h.par}</b><span>PAR</span></div>
        <div class="dato"><b>${h.handicap}</b><span>HCP</span></div>
        <div class="dato"><button class="toggle" id="ver-stats" style="background:transparent;color:#fff;border-color:rgba(255,255,255,.5)">
          ${verStats ? "Ocultar" : "Putts y"}<br>${verStats ? "stats" : "fairways"}</button></div>
      </div>
      ${jugadores.map((p) => {
        const s = sc[p.id][actual];
        const recibe = p.recibe?.[actual] ?? 0;
        const t = totales(p);
        const yd = p.yardas?.[actual];
        return `<div class="card">
          <div class="jug">
            <div class="nombre"><b>${esc(p.nombre)}</b>
              <div class="muted"><span class="tee-dot" style="background:${esc(p.tee_color)}"></span>${yd ? yd + " yd · " : ""}Hcp ${p.hcp_juego}
                ${recibe > 0 ? `· <span class="puntos">${"●".repeat(recibe)}</span>` : recibe < 0 ? "· da 1" : ""}</div>
              <div class="muted">${t.n ? `Total ${t.g} (<span class="${clsPar(t.vs)}">${vsPar(t.vs)}</span>) en ${t.n}` : "Sin scores"}</div>
            </div>
            <div class="stepper">
              <button data-pid="${p.id}" data-d="-1" ${cerrado ? "disabled" : ""}>−</button>
              <div class="valor ${s ? claseScore(s.golpes, h.par) : "vacio"}">${s ? s.golpes : "–"}</div>
              <button data-pid="${p.id}" data-d="1" ${cerrado ? "disabled" : ""}>+</button>
            </div>
          </div>
          ${verStats && s ? `<div class="extra">
            <span>Putts</span>
            <div class="stepper"><button data-pid="${p.id}" data-putt="-1">−</button>
              <div class="valor">${s.putts ?? "–"}</div><button data-pid="${p.id}" data-putt="1">+</button></div>
            ${h.par >= 4 ? `<button class="toggle ${s.fairway === true ? "si" : s.fairway === false ? "no" : ""}" data-fw="${p.id}">
              Fairway ${s.fairway === true ? "✓" : s.fairway === false ? "✗" : "?"}</button>` : ""}
            <button class="toggle" data-borrar="${p.id}">Borrar</button></div>` : ""}
        </div>`;
      }).join("")}
      <div class="nav-hoyo">
        <button class="btn sec" id="ant" ${idx === 0 ? "disabled" : ""}>‹ Hoyo ${orden[idx - 1] ?? ""}</button>
        <button class="btn" id="sig" ${idx === 17 ? "disabled" : ""}>Hoyo ${orden[idx + 1] ?? ""} ›</button>
      </div>
      <div class="fila" style="margin-top:14px;gap:8px">
        <a class="btn sec chico crece" href="#/t/${ctx.tid}">🏆 Leaderboard</a>
        <a class="btn sec chico crece" href="#/t/${ctx.tid}/g/${data.grupo.id}/apuestas">💰 Apuestas</a>
      </div>`);
    pintarRed();
    $$("[data-h]").forEach((b) => (b.onclick = () => { actual = Number(b.dataset.h); dibujar(); }));
    $("#ant").onclick = () => { actual = orden[idx - 1]; dibujar(); };
    $("#sig").onclick = () => { actual = orden[idx + 1]; dibujar(); };
    $("#ver-stats").onclick = () => { verStats = !verStats; store.set("ver_stats", verStats); dibujar(); };
    $$("[data-d]").forEach((b) => (b.onclick = () => {
      const pid = Number(b.dataset.pid), d = Number(b.dataset.d);
      const s = sc[pid][actual];
      let g = s ? s.golpes + d : (d > 0 ? h.par : h.par - 1);
      g = Math.max(1, Math.min(20, g));
      cambiar(pid, { golpes: g });
    }));
    $$("[data-putt]").forEach((b) => (b.onclick = () => {
      const pid = Number(b.dataset.pid), s = sc[pid][actual];
      const v = s.putts == null ? (Number(b.dataset.putt) > 0 ? 2 : 1) : s.putts + Number(b.dataset.putt);
      cambiar(pid, { putts: Math.max(0, Math.min(10, Math.min(v, s.golpes))) });
    }));
    $$("[data-fw]").forEach((b) => (b.onclick = () => {
      const pid = Number(b.dataset.fw), f = sc[pid][actual].fairway;
      cambiar(pid, { fairway: f === null || f === undefined ? true : f === true ? false : null });
    }));
    $$("[data-borrar]").forEach((b) => (b.onclick = () => cambiar(Number(b.dataset.borrar), { golpes: null })));
  }
  dibujar();
  enviar();
}

// ------------------------------------------------------------ apuestas
async function vistaApuestas(tid, gid) {
  tabActiva("torneos");
  titulo("Apuestas", `#/t/${tid}`);
  render(`<div class="cargando">Calculando…</div>`);
  const as = await api(`/api/torneos/${tid}/grupos/${gid}/apuestas`);
  if (!as.length) return render(`<div class="vacio">Este grupo no tiene apuestas.</div>`);
  const lado = (ns) => ns.map(esc).join(" / ");
  const matchTxt = (r, a) => {
    if (!r || !r.jugados) return `<span class="muted">Sin hoyos jugados</span>`;
    const lider = r.diferencia > 0 ? lado(a.nombres_a) : r.diferencia < 0 ? lado(a.nombres_b) : "";
    const fin = r.cerrado ? (r.ganador === "=" ? "Empate" : `Gana ${r.ganador === "A" ? lado(a.nombres_a) : lado(a.nombres_b)}`) : "";
    return `<b>${esc(r.texto)}</b> ${lider && !r.cerrado ? "· va arriba " + lider : ""} ${fin ? `· <b>${fin}</b>` : ""}`;
  };
  render(as.map((a) => {
    const cab = `<div class="fila"><h3 class="crece">${a.tipo === "skins" ? "Skins" : a.tipo === "nassau" ? "Nassau" : "Match"}
      <span class="muted">· ${a.neto ? "neto" : "gross"} · ${dinero(a.monto)}</span></h3></div>`;
    if (a.tipo === "skins") {
      const r = a.resultado;
      if (!r) return `<div class="card">${cab}<div class="muted">Faltan jugadores</div></div>`;
      return `<div class="card">${cab}
        ${a.lado_a.map((pid) => `<div class="lista-item"><div class="crece">${esc(a.nombres[pid])}</div>
          <div>${r.ganados[pid]} skin(s)</div><b class="${r.balance[pid] < 0 ? "bajo" : ""}" style="min-width:70px;text-align:right">${dinero(r.balance[pid])}</b></div>`).join("")}
        ${r.acumulado ? `<div class="muted">Acumulados sin ganador: ${r.acumulado}</div>` : ""}</div>`;
    }
    const titulo2 = `<div class="muted" style="margin-bottom:6px">${lado(a.nombres_a)} <b>vs</b> ${lado(a.nombres_b)}</div>`;
    if (a.tipo === "nassau") {
      const r = a.resultado;
      return `<div class="card">${cab}${titulo2}
        ${["ida", "vuelta", "total"].map((k) => `<div class="lista-item"><span style="width:60px;font-weight:600">${k[0].toUpperCase() + k.slice(1)}</span>
          <div class="crece">${matchTxt(r?.[k], a)}</div></div>`).join("")}</div>`;
    }
    return `<div class="card">${cab}${titulo2}${matchTxt(a.resultado, a)}</div>`;
  }).join("") + `<p class="muted" style="text-align:center">Neto: golpes "del más bajo" (el de menor handicap juega a 0)</p>`);
}

// ------------------------------------------------------------ jugadores
async function vistaJugadores() {
  titulo("Jugadores");
  tabActiva("jugadores");
  const js = await api("/api/jugadores");
  const dibujar = (f = "") => {
    const lista = js.filter((j) => j.nombre.toLowerCase().includes(f.toLowerCase()));
    $("#lista").innerHTML = lista.map((j) => `<a class="lista-item" href="#/j/${j.id}" style="color:inherit;text-decoration:none">
      <div class="crece"><b>${esc(j.nombre)}</b></div><span class="muted">Index ${j.handicap_index}</span> ›</a>`).join("")
      || `<div class="vacio">Sin jugadores</div>`;
  };
  render(`<label class="campo"><input id="buscar" placeholder="Buscar jugador…" autocomplete="off"></label>
    <div class="card" id="lista"></div>`);
  $("#buscar").oninput = (e) => dibujar(e.target.value);
  dibujar();
}

async function vistaJugador(jid) {
  tabActiva("jugadores");
  titulo("Jugador", "#/jugadores");
  const d = await api(`/api/jugadores/${jid}`);
  titulo(d.jugador.nombre, "#/jugadores");
  const e = d.estadisticas;
  const val = (v, suf = "") => (v === null || v === undefined ? "—" : `${v}${suf}`);
  const dist = e.distribucion;
  const totalHoyos = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
  const nombres = { eagle_o_mejor: "Eagle o mejor", birdie: "Birdie", par: "Par", bogey: "Bogey", doble_o_peor: "Doble o peor" };
  render(`
    <div class="card"><div class="muted">Handicap index</div><h2>${d.jugador.handicap_index}</h2></div>
    <div class="stats" style="margin-bottom:12px">
      <div class="stat"><b>${e.rondas}</b><span>Rondas</span></div>
      <div class="stat"><b>${val(e.promedio_18)}</b><span>Promedio 18</span></div>
      <div class="stat"><b>${val(e.mejor_18)}</b><span>Mejor ronda</span></div>
      <div class="stat"><b>${val(e.putts_por_hoyo)}</b><span>Putts/hoyo</span></div>
      <div class="stat"><b>${val(e.fairways_pct, "%")}</b><span>Fairways</span></div>
      <div class="stat"><b>${val(e.greens_regulacion_pct, "%")}</b><span>Greens en reg.</span></div>
    </div>
    <div class="card"><h3>Distribución de scores</h3>
      ${Object.entries(dist).map(([k, v]) => `<div class="fila" style="margin:6px 0"><span style="width:110px" class="muted">${nombres[k]}</span>
        <div class="crece"><div class="barra" style="width:${(100 * v) / totalHoyos}%;min-width:${v ? 4 : 0}px"></div></div><b style="width:30px;text-align:right">${v}</b></div>`).join("")}
    </div>
    <div class="card"><h3>Rondas</h3>
      ${d.rondas.map((r) => `<a class="lista-item" href="#/t/${r.torneo_id}" style="color:inherit;text-decoration:none">
        <div class="crece"><b>${esc(r.torneo)}</b><div class="muted">${fechaCorta(r.fecha)} · ${esc(r.recorrido)} · ${esc(r.tee)} · ${r.jugados} hoyos</div></div>
        <div style="text-align:right"><b>${r.gross}</b><div class="muted">Neto ${r.neto} · ${r.stableford} pts</div></div></a>`).join("") || `<div class="muted">Sin rondas todavía</div>`}
    </div>
    <p class="muted" style="text-align:center">Putts, fairways y greens solo cuentan los hoyos donde se capturaron.</p>`);
}

// ------------------------------------------------------------ administración
async function vistaAdmin() {
  titulo("Administración");
  tabActiva("admin");
  if (!adminToken()) {
    render(`<div class="card"><h2>Entrar como administrador</h2>
      <form id="login"><label class="campo">Contraseña<input type="password" id="pw" autocomplete="current-password" required></label>
      <button class="btn bloque">Entrar</button></form><div id="err"></div></div>`);
    $("#login").onsubmit = async (ev) => {
      ev.preventDefault();
      try {
        const r = await api("/api/admin/login", { method: "POST", body: { password: $("#pw").value } });
        store.set("admin_token", r.token);
        vistaAdmin();
      } catch (e) { $("#err").innerHTML = errorHTML(e); }
    };
    return;
  }
  render(`
    <a class="card" href="#/admin/torneos"><h3>🏆 Torneos</h3><div class="muted">Crear torneos, grupos, PINs, inscribir jugadores y apuestas</div></a>
    <a class="card" href="#/admin/jugadores"><h3>👤 Jugadores</h3><div class="muted">Alta de jugadores y su handicap index</div></a>
    <a class="card" href="#/admin/recorridos"><h3>⛳ Recorridos</h3><div class="muted">Par, handicap y yardas por hoyo; rating y slope de cada salida</div></a>
    <button class="btn sec bloque" id="salir">Cerrar sesión</button>`);
  $("#salir").onclick = () => { store.del("admin_token"); vistaAdmin(); };
}

async function vistaAdminRecorridos() {
  titulo("Recorridos", "#/admin");
  tabActiva("admin");
  const rs = await api("/api/recorridos");
  render(rs.map((r) => `<a class="card fila" href="#/admin/r/${r.id}"><div class="crece"><h3>${esc(r.nombre)}</h3>
    <div class="muted">${r.completo ? `Par ${r.par}` : "Faltan datos de los hoyos"}</div></div>
    <span class="pill ${r.completo ? "" : "alerta"}">${r.completo ? "Listo" : "Incompleto"}</span></a>`).join(""));
}

async function vistaAdminRecorrido(rid) {
  titulo("Recorrido", "#/admin/recorridos");
  tabActiva("admin");
  const r = await api(`/api/recorridos/${rid}`);
  titulo(r.nombre, "#/admin/recorridos");
  const num = (v) => (v === "" || v == null ? null : Number(v));
  render(`
    ${r.completo ? "" : `<div class="aviso">Captura el <b>par</b> y el <b>handicap</b> (1 a 18, sin repetir) de cada hoyo con la tarjeta oficial del club. Sin esto no se pueden crear torneos en este recorrido.</div>`}
    <div class="card"><h3>Hoyos</h3>
      <table class="edit"><tr><th>Hoyo</th><th>Par</th><th>Handicap</th></tr>
      ${r.hoyos.map((h) => `<tr><td><b>${h.numero}</b></td>
        <td><input inputmode="numeric" data-par="${h.numero}" value="${h.par ?? ""}"></td>
        <td><input inputmode="numeric" data-hcp="${h.numero}" value="${h.handicap ?? ""}"></td></tr>`).join("")}
      </table>
      <div class="muted" id="par-total" style="margin:8px 0"></div>
      <button class="btn bloque" id="guardar-hoyos">Guardar hoyos</button></div>
    <h3>Salidas (tees)</h3>
    ${r.tees.map((t) => teeForm(t)).join("")}
    <details class="card"><summary><b>+ Agregar salida</b></summary>${teeForm({ id: "nuevo", nombre: "", color: "#888888", yardas: Array(18).fill(null) })}</details>
    <p class="muted">Rating y slope precargados de internet (GolfPass): verifícalos con la tarjeta del club.</p>`);
  const sumaPar = () => {
    const t = $$("[data-par]").reduce((a, i) => a + (Number(i.value) || 0), 0);
    $("#par-total").textContent = `Par total: ${t}`;
  };
  $$("[data-par]").forEach((i) => (i.oninput = sumaPar));
  sumaPar();
  $("#guardar-hoyos").onclick = async () => {
    const hoyos = r.hoyos.map((h) => ({ numero: h.numero, par: num($(`[data-par="${h.numero}"]`).value), handicap: num($(`[data-hcp="${h.numero}"]`).value) }));
    try {
      const res = await adminApi(`/recorridos/${rid}/hoyos`, { method: "PUT", body: hoyos });
      toast(res.completo ? `Guardado · Par ${res.par} · listo para torneos` : "Guardado (todavía incompleto)");
    } catch (e) { toast(e.message, 4000); }
  };
  $$("form[data-tee]").forEach((f) => (f.onsubmit = async (ev) => {
    ev.preventDefault();
    const v = (n) => f.elements[n].value;
    const body = {
      nombre: v("nombre"), color: v("color"), orden: Number(v("orden") || 0),
      rating_h: num(v("rating_h")), slope_h: num(v("slope_h")), rating_m: num(v("rating_m")), slope_m: num(v("slope_m")),
      yardas: Array.from({ length: 18 }, (_, i) => num(f.elements[`y${i + 1}`].value)),
    };
    try {
      if (f.dataset.tee === "nuevo") await adminApi(`/recorridos/${rid}/tees`, { method: "POST", body });
      else await adminApi(`/tees/${f.dataset.tee}`, { method: "PUT", body });
      toast("Salida guardada");
      if (f.dataset.tee === "nuevo") vistaAdminRecorrido(rid);
    } catch (e) { toast(e.message, 4000); }
  }));
}

function teeForm(t) {
  return `<form class="card" data-tee="${t.id}">
    <div class="fila"><span class="tee-dot" style="background:${esc(t.color)};width:18px;height:18px"></span><h3 class="crece" style="margin:0">${esc(t.nombre) || "Nueva salida"}</h3></div>
    <div class="grid3" style="margin-top:10px">
      <label class="campo">Nombre<input name="nombre" value="${esc(t.nombre)}" required></label>
      <label class="campo">Color<input name="color" type="color" value="${esc(t.color)}"></label>
      <label class="campo">Orden<input name="orden" inputmode="numeric" value="${t.orden ?? 0}"></label>
      <label class="campo">Rating H<input name="rating_h" inputmode="decimal" value="${t.rating_h ?? ""}"></label>
      <label class="campo">Slope H<input name="slope_h" inputmode="numeric" value="${t.slope_h ?? ""}"></label>
      <span></span>
      <label class="campo">Rating M<input name="rating_m" inputmode="decimal" value="${t.rating_m ?? ""}"></label>
      <label class="campo">Slope M<input name="slope_m" inputmode="numeric" value="${t.slope_m ?? ""}"></label>
    </div>
    <details><summary class="muted">Yardas por hoyo (opcional)</summary>
      <div class="grid3" style="margin-top:8px">${(t.yardas || Array(18).fill(null)).map((y, i) =>
        `<label class="campo">Hoyo ${i + 1}<input name="y${i + 1}" inputmode="numeric" value="${y ?? ""}"></label>`).join("")}</div>
    </details>
    <button class="btn bloque" style="margin-top:10px">Guardar salida</button></form>`;
}

async function vistaAdminJugadores() {
  titulo("Jugadores", "#/admin");
  tabActiva("admin");
  const js = await api("/api/jugadores");
  let editando = null;
  const dibujar = () => {
    const j = editando || { nombre: "", genero: "H", handicap_index: "" };
    render(`<form class="card" id="f"><h3>${editando ? "Editar jugador" : "Nuevo jugador"}</h3>
      <label class="campo">Nombre<input name="nombre" value="${esc(j.nombre)}" required maxlength="80"></label>
      <div class="grid2"><label class="campo">Género<select name="genero">
        <option value="H" ${j.genero === "H" ? "selected" : ""}>Caballero</option><option value="M" ${j.genero === "M" ? "selected" : ""}>Dama</option></select></label>
        <label class="campo">Handicap index<input name="idx" inputmode="decimal" value="${j.handicap_index}" required></label></div>
      <button class="btn bloque">${editando ? "Guardar cambios" : "Agregar"}</button>
      ${editando ? `<button type="button" class="btn sec bloque" id="cancelar" style="margin-top:8px">Cancelar</button>` : ""}</form>
      <div class="card">${js.map((x) => `<div class="lista-item"><div class="crece"><b>${esc(x.nombre)}</b>
        <div class="muted">${x.genero === "M" ? "Dama" : "Caballero"} · Index ${x.handicap_index}</div></div>
        <button class="btn chico sec" data-ed="${x.id}">Editar</button><button class="btn chico peligro" data-baja="${x.id}">Baja</button></div>`).join("") || `<div class="muted">Sin jugadores</div>`}</div>`);
    $("#f").onsubmit = async (ev) => {
      ev.preventDefault();
      const f = ev.target;
      const body = { nombre: f.nombre.value, genero: f.genero.value, handicap_index: Number(String(f.idx.value).replace(",", ".")) };
      try {
        if (editando) await adminApi(`/jugadores/${editando.id}`, { method: "PUT", body });
        else await adminApi("/jugadores", { method: "POST", body });
        toast("Guardado");
        vistaAdminJugadores();
      } catch (e) { toast(e.message, 4000); }
    };
    if ($("#cancelar")) $("#cancelar").onclick = () => { editando = null; dibujar(); };
    $$("[data-ed]").forEach((b) => (b.onclick = () => { editando = js.find((x) => x.id === Number(b.dataset.ed)); dibujar(); }));
    $$("[data-baja]").forEach((b) => (b.onclick = async () => {
      if (!confirm("¿Dar de baja a este jugador? Su historial se conserva.")) return;
      await adminApi(`/jugadores/${b.dataset.baja}`, { method: "DELETE" });
      vistaAdminJugadores();
    }));
  };
  dibujar();
}

async function vistaAdminTorneos() {
  titulo("Torneos", "#/admin");
  tabActiva("admin");
  const [rs, ts] = await Promise.all([api("/api/recorridos"), api("/api/torneos")]);
  render(`<form class="card" id="f"><h3>Nuevo torneo</h3>
      <label class="campo">Nombre<input name="nombre" required maxlength="100" placeholder="Ej. Torneo de los jueves"></label>
      <div class="grid2"><label class="campo">Fecha<input name="fecha" type="date" value="${hoyISO()}" required></label>
        <label class="campo">Recorrido<select name="rec" required>${rs.map((r) =>
          `<option value="${r.id}" ${r.completo ? "" : "disabled"}>${esc(r.nombre)}${r.completo ? "" : " (incompleto)"}</option>`).join("")}</select></label>
        <label class="campo">Formato<select name="fmt"><option value="neto">Neto (medal)</option><option value="gross">Gross</option><option value="stableford">Stableford</option></select></label>
        <label class="campo">% de handicap<input name="pct" inputmode="numeric" value="100"></label></div>
      ${rs.some((r) => r.completo) ? "" : `<div class="aviso">Primero completa los hoyos de un recorrido en <a href="#/admin/recorridos">Recorridos</a>.</div>`}
      <button class="btn bloque">Crear torneo</button></form>
    ${ts.map((t) => `<a class="card fila" href="#/admin/t/${t.id}"><div class="crece"><h3>${esc(t.nombre)}</h3>
      <div class="muted">${fechaCorta(t.fecha)} · ${esc(t.recorrido)} · ${t.jugadores} jugadores</div></div>
      <span class="pill ${t.estado === "cerrado" ? "cerrado" : ""}">${esc(t.estado)}</span></a>`).join("")}`);
  $("#f").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    try {
      const r = await adminApi("/torneos", { method: "POST", body: {
        nombre: f.nombre.value, fecha: f.fecha.value, recorrido_id: Number(f.rec.value), formato: f.fmt.value, pct_handicap: Number(f.pct.value) } });
      location.hash = `#/admin/t/${r.id}`;
    } catch (e) { toast(e.message, 4000); }
  };
}

async function vistaAdminTorneo(tid) {
  titulo("Torneo", "#/admin/torneos");
  tabActiva("admin");
  const [tr, js] = await Promise.all([adminApi(`/torneos/${tid}`), api("/api/jugadores")]);
  titulo(tr.nombre, "#/admin/torneos");
  const inscritos = new Set(tr.participantes.map((p) => p.jugador_id));
  const libres = js.filter((j) => !inscritos.has(j.id));
  const opt = (arr, sel, vacio) => (vacio ? `<option value="">${vacio}</option>` : "") +
    arr.map((x) => `<option value="${x.id}" ${x.id === sel ? "selected" : ""}>${esc(x.nombre)}</option>`).join("");
  const recargar = () => vistaAdminTorneo(tid);
  const intenta = async (fn, ok) => { try { await fn(); if (ok) toast(ok); recargar(); } catch (e) { toast(e.message, 4000); } };

  render(`
    <div class="card"><div class="fila"><div class="crece"><div class="muted">${fechaCorta(tr.fecha)} · ${esc(tr.recorrido)}</div>
      <div class="muted">${NOMBRE_FMT[tr.formato]} · Hcp ${tr.pct_handicap}%</div></div>
      <span class="pill ${tr.estado === "cerrado" ? "cerrado" : ""}">${esc(tr.estado)}</span></div>
      <div class="fila" style="margin-top:10px;gap:8px">
        <a class="btn chico sec crece" href="#/t/${tid}">Ver leaderboard</a>
        <button class="btn chico ${tr.estado === "abierto" ? "peligro" : ""} crece" id="estado">${tr.estado === "abierto" ? "Cerrar torneo" : "Reabrir"}</button></div></div>

    <div class="card"><h3>Grupos</h3>
      ${tr.grupos.map((g) => {
        const ps = tr.participantes.filter((p) => p.grupo_id === g.id);
        return `<div class="lista-item" style="align-items:flex-start"><div class="crece"><b>${esc(g.nombre)}</b>
          <div class="muted">Hoyo ${g.hoyo_salida}${g.hora_salida ? " · " + esc(g.hora_salida) : ""} · ${ps.map((p) => esc(p.nombre)).join(", ") || "sin jugadores"}</div>
          <div>PIN: <span class="pin">${esc(g.pin)}</span></div></div>
          <div style="display:flex;flex-direction:column;gap:6px"><a class="btn chico sec" href="#/admin/t/${tid}/g/${g.id}">Scores</a>
          <button class="btn chico peligro" data-borrar-g="${g.id}">Borrar</button></div></div>`;
      }).join("") || `<div class="muted">Sin grupos</div>`}
      <form id="fg" class="grid3" style="margin-top:10px;align-items:end">
        <label class="campo">Nombre<input name="nombre" required value="Grupo ${tr.grupos.length + 1}"></label>
        <label class="campo">Hoyo salida<input name="hoyo" inputmode="numeric" value="1"></label>
        <label class="campo">Hora<input name="hora" placeholder="8:30"></label>
        <button class="btn" style="grid-column:1/-1">+ Crear grupo (genera PIN)</button></form></div>

    <div class="card"><h3>Jugadores inscritos (${tr.participantes.length})</h3>
      ${tr.participantes.map((p) => `<form class="lista-item" data-p="${p.id}" data-j="${p.jugador_id}" style="flex-wrap:wrap">
        <div class="crece" style="min-width:140px"><b>${esc(p.nombre)}</b><div class="muted">Index ${p.handicap_index}</div></div>
        <select name="tee" style="max-width:100px">${opt(tr.tees, p.tee_id)}</select>
        <select name="grupo" style="max-width:110px">${opt(tr.grupos, p.grupo_id, "Sin grupo")}</select>
        <input name="hcp" inputmode="numeric" value="${p.hcp_juego}" style="width:52px;text-align:center" title="Handicap de juego">
        <button class="btn chico sec">✓</button><button type="button" class="btn chico peligro" data-quitar="${p.id}">✕</button></form>`).join("")
        || `<div class="muted">Nadie inscrito</div>`}
      <form id="fp" style="margin-top:12px">
        <label class="campo">Jugador<select name="jug" required>${opt(libres, null, libres.length ? "Elige…" : "Todos inscritos (agrega en Jugadores)")}</select></label>
        <div class="grid2"><label class="campo">Salida<select name="tee">${opt(tr.tees, tr.tees[0]?.id)}</select></label>
          <label class="campo">Grupo<select name="grupo">${opt(tr.grupos, tr.grupos[0]?.id, "Sin grupo")}</select></label></div>
        <button class="btn bloque">Inscribir (calcula su handicap)</button></form></div>

    <div class="card"><h3>Apuestas</h3>
      ${tr.apuestas.map((a) => {
        const g = tr.grupos.find((x) => x.id === a.grupo_id);
        const nom = (csv) => (csv || "").split(",").filter(Boolean).map((id) => esc(tr.participantes.find((p) => p.id === Number(id))?.nombre || "?")).join(" / ");
        return `<div class="lista-item"><div class="crece"><b>${esc(a.tipo)}</b> · ${esc(g?.nombre)} · ${dinero(a.monto)} · ${a.neto ? "neto" : "gross"}
          <div class="muted">${nom(a.lado_a)}${a.lado_b ? " vs " + nom(a.lado_b) : ""}</div></div>
          <a class="btn chico sec" href="#/t/${tid}/g/${a.grupo_id}/apuestas">Ver</a>
          <button class="btn chico peligro" data-borrar-a="${a.id}">✕</button></div>`;
      }).join("") || `<div class="muted">Sin apuestas</div>`}
      ${tr.grupos.length ? `<form id="fa" style="margin-top:12px">
        <div class="grid2"><label class="campo">Grupo<select name="grupo">${opt(tr.grupos, tr.grupos[0]?.id)}</select></label>
          <label class="campo">Tipo<select name="tipo"><option value="match">Match</option><option value="nassau">Nassau</option><option value="skins">Skins</option></select></label>
          <label class="campo">Monto ($)<input name="monto" inputmode="decimal" value="100"></label>
          <label class="campo">Modo<select name="neto"><option value="1">Neto</option><option value="0">Gross</option></select></label></div>
        <div class="muted" id="ayuda-lados" style="margin-bottom:6px"></div>
        <div class="chips" id="chips"></div>
        <button class="btn bloque" style="margin-top:10px">Crear apuesta</button></form>` : `<div class="muted">Crea grupos primero</div>`}
    </div>`);

  $("#estado").onclick = () => intenta(() => adminApi(`/torneos/${tid}/estado/${tr.estado === "abierto" ? "cerrado" : "abierto"}`, { method: "POST" }), "Listo");
  $("#fg").onsubmit = (ev) => {
    ev.preventDefault();
    const f = ev.target;
    intenta(async () => {
      const r = await adminApi(`/torneos/${tid}/grupos`, { method: "POST", body: { nombre: f.nombre.value, hoyo_salida: Number(f.hoyo.value) || 1, hora_salida: f.hora.value || null } });
      toast(`Grupo creado · PIN ${r.pin}`, 5000);
    });
  };
  $$("[data-borrar-g]").forEach((b) => (b.onclick = () => {
    if (confirm("¿Borrar el grupo? Sus jugadores quedan sin grupo y se borran sus apuestas.")) intenta(() => adminApi(`/torneos/${tid}/grupos/${b.dataset.borrarG}`, { method: "DELETE" }), "Grupo borrado");
  }));
  $("#fp").onsubmit = (ev) => {
    ev.preventDefault();
    const f = ev.target;
    if (!f.jug.value) return;
    intenta(() => adminApi(`/torneos/${tid}/participantes`, { method: "POST", body: { jugador_id: Number(f.jug.value), tee_id: Number(f.tee.value), grupo_id: f.grupo.value ? Number(f.grupo.value) : null } }), "Inscrito");
  };
  $$("form[data-p]").forEach((f) => (f.onsubmit = (ev) => {
    ev.preventDefault();
    intenta(() => adminApi(`/torneos/${tid}/participantes/${f.dataset.p}`, { method: "PUT", body: {
      jugador_id: Number(f.dataset.j), tee_id: Number(f.tee.value), grupo_id: f.grupo.value ? Number(f.grupo.value) : null,
      hcp_juego: f.hcp.value === "" ? null : Number(f.hcp.value) } }), "Actualizado");
  }));
  $$("[data-quitar]").forEach((b) => (b.onclick = () => {
    if (confirm("¿Quitar a este jugador del torneo? Se borran sus scores.")) intenta(() => adminApi(`/torneos/${tid}/participantes/${b.dataset.quitar}`, { method: "DELETE" }), "Quitado");
  }));
  $$("[data-borrar-a]").forEach((b) => (b.onclick = () => intenta(() => adminApi(`/torneos/${tid}/apuestas/${b.dataset.borrarA}`, { method: "DELETE" }), "Apuesta borrada")));

  const fa = $("#fa");
  if (fa) {
    let lados = {};
    const pintarChips = () => {
      const gid = Number(fa.grupo.value), skins = fa.tipo.value === "skins";
      const ps = tr.participantes.filter((p) => p.grupo_id === gid);
      $("#ayuda-lados").textContent = skins ? "Toca a los jugadores que entran a los skins:" : "Toca para elegir lado: azul = lado A, rojo = lado B (1 o 2 por lado).";
      $("#chips").innerHTML = ps.map((p) => `<button type="button" class="chip ${lados[p.id] || ""}" data-c="${p.id}">${esc(p.nombre)}</button>`).join("") || `<span class="muted">Este grupo no tiene jugadores</span>`;
      $$("[data-c]").forEach((c) => (c.onclick = () => {
        const id = Number(c.dataset.c), v = lados[id];
        lados[id] = skins ? (v ? undefined : "a") : (!v ? "a" : v === "a" ? "b" : undefined);
        pintarChips();
      }));
    };
    fa.grupo.onchange = () => { lados = {}; pintarChips(); };
    fa.tipo.onchange = () => { lados = {}; pintarChips(); };
    pintarChips();
    fa.onsubmit = (ev) => {
      ev.preventDefault();
      const ids = (l) => Object.entries(lados).filter(([, v]) => v === l).map(([k]) => Number(k));
      intenta(() => adminApi(`/torneos/${tid}/apuestas`, { method: "POST", body: {
        grupo_id: Number(fa.grupo.value), tipo: fa.tipo.value, monto: Number(String(fa.monto.value).replace(",", ".")) || 0,
        neto: fa.neto.value === "1", lado_a: ids("a"), lado_b: ids("b") } }), "Apuesta creada");
    };
  }
}

async function vistaAdminCaptura(tid, gid) {
  tabActiva("admin");
  if (!adminToken()) { location.hash = "#/admin"; return; }
  titulo("Scores", `#/admin/t/${tid}`);
  await capturador({
    tid,
    volver: `#/admin/t/${tid}`,
    colaKey: `cola-admin:${tid}:${gid}`,
    cacheKey: `tarjeta-admin:${tid}:${gid}`,
    cargar: () => adminApi(`/torneos/${tid}/grupos/${gid}/tarjeta`),
    guardar: (lista) => adminApi(`/torneos/${tid}/scores`, { method: "PUT", body: lista }),
    alExpirar: () => { store.del("admin_token"); location.hash = "#/admin"; },
  });
}

// ------------------------------------------------------------ arranque
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
ruta();
