#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py
Panel web para ejecutar y monitorear el pipeline de DataOps en Render (plan free).

Que hace:
  - Sirve un dashboard HTML en el puerto $PORT (Render) o 10000 por defecto.
  - Permite ejecutar el pipeline completo o etapa por etapa (equivalente a
    `docker compose up` / `docker compose run --rm <etapa>`).
  - Transmite los logs en vivo y muestra los KPIs y el estado de Supabase.

No agrega dependencias nuevas: usa solo la libreria estandar de Python
(+ psycopg2, que ya esta en requirements.txt, para leer conteos de Supabase).

Variables de entorno usadas por el pipeline (configurarlas en Render):
  - FERNET_KEY     clave de cifrado Fernet.
  - DATABASE_URL   cadena de conexion a Supabase (PostgreSQL).
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
KPIS_FILE = ROOT / "data" / "reports" / "kpis_latest.json"

# Etapas disponibles (nombre -> script). El orden refleja el flujo del pipeline.
ETAPAS = {
    "ingesta": "src/ingesta.py",
    "limpieza": "src/limpieza.py",
    "validacion": "src/validacion.py",
    "carga": "src/carga.py",
    "kpis": "src/kpis.py",
}

# Carpetas que el pipeline espera que existan (en Render el FS arranca limpio).
DIRS_NECESARIOS = [
    "data/source", "data/raw", "data/processed",
    "data/validated", "data/rejected", "data/reports", "logs",
]


def asegurar_dirs():
    for d in DIRS_NECESARIOS:
        (ROOT / d).mkdir(parents=True, exist_ok=True)


class EstadoEjecucion:
    """Guarda el estado de la corrida actual y el buffer de logs en memoria."""

    def __init__(self):
        self.lock = threading.Lock()
        self.estado = "inactivo"   # inactivo | ejecutando | exito | error
        self.objetivo = None       # "completo" o nombre de etapa
        self.inicio = None
        self.fin = None
        self.exit_code = None
        self.lineas = []           # buffer de logs (lista de str)

    def reset(self, objetivo):
        with self.lock:
            self.estado = "ejecutando"
            self.objetivo = objetivo
            self.inicio = time.time()
            self.fin = None
            self.exit_code = None
            self.lineas = []

    def log(self, linea):
        with self.lock:
            self.lineas.append(linea)

    def terminar(self, code):
        with self.lock:
            self.exit_code = code
            self.fin = time.time()
            self.estado = "exito" if code == 0 else "error"

    def snapshot(self):
        with self.lock:
            dur = None
            if self.inicio:
                fin = self.fin or time.time()
                dur = round(fin - self.inicio, 1)
            return {
                "estado": self.estado,
                "objetivo": self.objetivo,
                "inicio": self.inicio,
                "fin": self.fin,
                "duracion": dur,
                "exit_code": self.exit_code,
                "n_lineas": len(self.lineas),
            }

    def logs_desde(self, offset):
        with self.lock:
            offset = max(0, min(offset, len(self.lineas)))
            return self.lineas[offset:], len(self.lineas)


ESTADO = EstadoEjecucion()


def _comando(objetivo):
    if objetivo == "completo":
        return [sys.executable, "-u", "pipeline.py"]
    script = ETAPAS.get(objetivo)
    if not script:
        return None
    return [sys.executable, "-u", script]


def ejecutar(objetivo):
    """Corre el pipeline (o una etapa) en un proceso aparte y captura su salida."""
    cmd = _comando(objetivo)
    if cmd is None:
        return
    ESTADO.reset(objetivo)
    asegurar_dirs()
    etiqueta = "pipeline completo" if objetivo == "completo" else f"etapa: {objetivo}"
    ESTADO.log(f"$ {' '.join(cmd)}")
    ESTADO.log(f"# Iniciando {etiqueta}  -  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    ESTADO.log("")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        for linea in proc.stdout:
            ESTADO.log(linea.rstrip("\n"))
        proc.wait()
        ESTADO.log("")
        if proc.returncode == 0:
            ESTADO.log(f"# Finalizado OK (exit {proc.returncode})")
        else:
            ESTADO.log(f"# Finalizado con error (exit {proc.returncode})")
        ESTADO.terminar(proc.returncode)
    except Exception as e:  # pragma: no cover - defensivo
        ESTADO.log(f"# ERROR al ejecutar: {e}")
        ESTADO.terminar(1)


def lanzar(objetivo):
    """Lanza una corrida si no hay otra activa. Devuelve True si arranco."""
    with ESTADO.lock:
        if ESTADO.estado == "ejecutando":
            return False
    threading.Thread(target=ejecutar, args=(objetivo,), daemon=True).start()
    return True


def leer_kpis():
    try:
        with open(KPIS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def contar_supabase():
    """Conteos de filas en Supabase (si DATABASE_URL esta definida)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return {"disponible": False, "motivo": "DATABASE_URL no definida"}
    try:
        import psycopg2
        con = psycopg2.connect(url, connect_timeout=10)
        conteos = {}
        cur = con.cursor()
        for tabla in ("notificaciones", "rechazados", "load_audit"):
            try:
                cur.execute(f"select count(*) from {tabla}")
                conteos[tabla] = cur.fetchone()[0]
            except Exception:
                conteos[tabla] = None
        cur.close()
        con.close()
        return {"disponible": True, "conteos": conteos}
    except Exception as e:
        return {"disponible": False, "motivo": str(e)}


# --------------------------------------------------------------------------- #
#  Frontend (HTML + CSS + JS en un solo archivo, servido como pagina estatica)
# --------------------------------------------------------------------------- #
PAGINA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motor de Notificaciones - DataOps</title>
<style>
  :root{
    --bg:#eef1f7; --card:#ffffff; --ink:#0f172a; --muted:#64748b;
    --line:#e2e8f0; --accent:#4f46e5; --accent-soft:#eef2ff;
    --ok:#16a34a; --ok-soft:#dcfce7; --warn:#d97706; --warn-soft:#fef3c7;
    --err:#dc2626; --err-soft:#fee2e2; --console:#0b1220;
  }
  *{box-sizing:border-box}
  body{
    margin:0; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.5;
  }
  .wrap{max-width:1080px; margin:0 auto; padding:24px 20px 56px;}
  header.top{display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-bottom:6px;}
  .logo{
    width:42px; height:42px; border-radius:11px; flex:none;
    background:linear-gradient(135deg,#6366f1,#4f46e5); color:#fff;
    display:grid; place-items:center; font-weight:700; font-size:20px;
    box-shadow:0 4px 14px rgba(79,70,229,.35);
  }
  h1{font-size:20px; margin:0; letter-spacing:-.01em;}
  .sub{color:var(--muted); font-size:13.5px; margin:2px 0 0;}
  .badge{
    margin-left:auto; display:inline-flex; align-items:center; gap:7px;
    padding:7px 14px; border-radius:999px; font-weight:600; font-size:13px;
    background:#e2e8f0; color:#334155;
  }
  .dot{width:9px; height:9px; border-radius:50%; background:currentColor;}
  .badge.ejecutando{background:var(--warn-soft); color:#b45309;}
  .badge.ejecutando .dot{animation:pulse 1s infinite;}
  .badge.exito{background:var(--ok-soft); color:#15803d;}
  .badge.error{background:var(--err-soft); color:#b91c1c;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}

  .grid{display:grid; gap:16px; margin-top:18px;}
  @media(min-width:780px){ .cols{grid-template-columns:1.15fr .85fr;} }
  .card{
    background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:18px; box-shadow:0 1px 2px rgba(15,23,42,.04);
  }
  .card h2{font-size:13px; text-transform:uppercase; letter-spacing:.06em;
    color:var(--muted); margin:0 0 14px;}

  .btn{
    appearance:none; border:1px solid transparent; cursor:pointer;
    font-size:14px; font-weight:600; border-radius:10px; padding:11px 16px;
    transition:.15s; font-family:inherit;
  }
  .btn:disabled{opacity:.5; cursor:not-allowed;}
  .btn-main{background:var(--accent); color:#fff; width:100%;
    box-shadow:0 4px 14px rgba(79,70,229,.30);}
  .btn-main:not(:disabled):hover{background:#4338ca;}
  .stages{display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;}
  .chip{
    background:#f8fafc; border:1px solid var(--line); color:#334155;
    border-radius:9px; padding:8px 12px; font-size:13px; font-weight:600; cursor:pointer;
  }
  .chip:not(:disabled):hover{border-color:var(--accent); color:var(--accent); background:var(--accent-soft);}
  .chip:disabled{opacity:.5; cursor:not-allowed;}
  .hint{color:var(--muted); font-size:12px; margin-top:12px;}

  .cfg{display:flex; gap:10px; flex-wrap:wrap; margin:0 0 4px;}
  .pill{display:inline-flex; align-items:center; gap:7px; font-size:12.5px;
    font-weight:600; padding:6px 11px; border-radius:999px; border:1px solid var(--line);}
  .pill.on{background:var(--ok-soft); color:#15803d; border-color:#bbf7d0;}
  .pill.off{background:var(--err-soft); color:#b91c1c; border-color:#fecaca;}

  .stat-row{display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px dashed var(--line); font-size:14px;}
  .stat-row:last-child{border-bottom:0;}
  .stat-row span:first-child{color:var(--muted);}
  .stat-row b{font-variant-numeric:tabular-nums;}

  .kpis{display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px;}
  .kpi{border:1px solid var(--line); border-radius:12px; padding:13px; background:#fbfcfe;}
  .kpi .lbl{font-size:12px; color:var(--muted); min-height:30px;}
  .kpi .val{font-size:23px; font-weight:700; margin-top:6px; font-variant-numeric:tabular-nums;}
  .kpi .meta{font-size:11.5px; color:var(--muted); margin-top:3px;}
  .kpi .tag{display:inline-block; margin-top:9px; font-size:11px; font-weight:700;
    padding:3px 9px; border-radius:999px;}
  .kpi.ok .tag{background:var(--ok-soft); color:#15803d;}
  .kpi.no .tag{background:var(--err-soft); color:#b91c1c;}
  .empty{color:var(--muted); font-size:13.5px; padding:6px 0;}

  .console{
    background:var(--console); border-radius:12px; padding:14px 16px;
    height:340px; overflow:auto; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    font-size:12.5px; line-height:1.55; color:#cbd5e1; white-space:pre-wrap; word-break:break-word;
  }
  .console .l-cmd{color:#7dd3fc;}
  .console .l-meta{color:#94a3b8;}
  .console .l-ok{color:#86efac;}
  .console .l-err{color:#fca5a5;}
  .console .l-warn{color:#fcd34d;}
  .console-bar{display:flex; align-items:center; gap:12px; margin-bottom:10px;}
  .console-bar label{font-size:12.5px; color:var(--muted); display:flex; align-items:center; gap:6px;}
  .lnk{margin-left:auto; font-size:12.5px; color:var(--accent); background:none; border:0; cursor:pointer; font-weight:600;}
  footer{color:var(--muted); font-size:12px; text-align:center; margin-top:26px;}
  a{color:var(--accent);}
</style>
</head>
<body>
<div class="wrap">

  <header class="top">
    <div class="logo">DO</div>
    <div>
      <h1>Motor de Notificaciones &middot; DataOps</h1>
      <p class="sub">Pipeline de ingesta, limpieza, validacion, carga y KPIs &rarr; Supabase</p>
    </div>
    <span id="badge" class="badge"><span class="dot"></span><span id="badge-txt">Inactivo</span></span>
  </header>

  <div class="cfg" id="cfg"></div>

  <div class="grid cols">
    <!-- Panel de control -->
    <div class="card">
      <h2>Ejecucion</h2>
      <button id="run-full" class="btn btn-main">&#9654;&nbsp; Ejecutar pipeline completo</button>
      <div class="stages">
        <button class="chip" data-stage="ingesta">1 &middot; Ingesta</button>
        <button class="chip" data-stage="limpieza">2 &middot; Limpieza</button>
        <button class="chip" data-stage="validacion">3 &middot; Validacion</button>
        <button class="chip" data-stage="carga">4 &middot; Carga</button>
        <button class="chip" data-stage="kpis">5 &middot; KPIs</button>
      </div>
      <p class="hint">El pipeline completo corre las 5 etapas en orden (equivale a <code>docker compose up</code>).
      Las etapas individuales equivalen a <code>docker compose run --rm &lt;etapa&gt;</code> y deben correrse en orden.</p>
    </div>

    <!-- Resumen -->
    <div class="card">
      <h2>Resumen de la corrida</h2>
      <div class="stat-row"><span>Objetivo</span><b id="s-obj">&mdash;</b></div>
      <div class="stat-row"><span>Duracion</span><b id="s-dur">&mdash;</b></div>
      <div class="stat-row"><span>Codigo de salida</span><b id="s-exit">&mdash;</b></div>
      <hr style="border:0;border-top:1px solid var(--line);margin:12px 0 6px">
      <div class="stat-row"><span>notificaciones</span><b id="db-notif">&mdash;</b></div>
      <div class="stat-row"><span>rechazados</span><b id="db-rech">&mdash;</b></div>
      <div class="stat-row"><span>load_audit</span><b id="db-audit">&mdash;</b></div>
    </div>
  </div>

  <!-- KPIs -->
  <div class="card" style="margin-top:16px">
    <h2>Indicadores (KPIs)</h2>
    <div id="kpis" class="kpis"><p class="empty">Aun no hay KPIs. Ejecuta el pipeline para generarlos.</p></div>
  </div>

  <!-- Logs -->
  <div class="card" style="margin-top:16px">
    <h2>Logs en vivo</h2>
    <div class="console-bar">
      <label><input type="checkbox" id="autoscroll" checked> Auto-scroll</label>
      <button class="lnk" id="clear">Limpiar vista</button>
    </div>
    <div id="console" class="console"></div>
  </div>

  <footer>Panel de despliegue &middot; corre en Render (plan free) &middot; datos hacia Supabase</footer>
</div>

<script>
const $ = (id) => document.getElementById(id);
let offset = 0;
let corriendo = false;

const KPI_LABELS = {
  completitud_pct: "Completitud de datos (%)",
  tasa_rechazo_pct: "Tasa de rechazo (%)",
  cumplimiento_sla_pct: "Cumplimiento SLA (%)",
  latencia_promedio_ms: "Latencia promedio (ms)",
  latencia_p95_ms: "Latencia P95 (ms)",
};

function setBusy(b){
  corriendo = b;
  $("run-full").disabled = b;
  document.querySelectorAll(".chip").forEach(c => c.disabled = b);
}

function badge(estado){
  const map = {inactivo:["", "Inactivo"], ejecutando:["ejecutando","Ejecutando..."],
               exito:["exito","Exito"], error:["error","Error"]};
  const [cls, txt] = map[estado] || ["","Inactivo"];
  $("badge").className = "badge " + cls;
  $("badge-txt").textContent = txt;
}

function fmtDur(d){ return d == null ? "—" : d + " s"; }

function renderCfg(cfg){
  const el = $("cfg");
  el.innerHTML = "";
  const items = [["FERNET_KEY", cfg.fernet], ["DATABASE_URL", cfg.database]];
  for(const [k,v] of items){
    const p = document.createElement("span");
    p.className = "pill " + (v ? "on" : "off");
    p.innerHTML = (v ? "&#10003; " : "&#10007; ") + k + (v ? " configurada" : " falta");
    el.appendChild(p);
  }
}

function renderKpis(kpis){
  const box = $("kpis");
  if(!kpis || !kpis.kpis){ return; }
  box.innerHTML = "";
  for(const [k, info] of Object.entries(kpis.kpis)){
    const cumple = !!info.cumple;
    const div = document.createElement("div");
    div.className = "kpi " + (cumple ? "ok" : "no");
    div.innerHTML =
      '<div class="lbl">'+(KPI_LABELS[k]||k)+'</div>'+
      '<div class="val">'+(info.valor ?? "—")+'</div>'+
      '<div class="meta">Meta: '+(info.slo ?? "—")+'</div>'+
      '<span class="tag">'+(cumple ? "Cumple" : "Alerta")+'</span>';
    box.appendChild(div);
  }
}

function lineClass(t){
  if(t.startsWith("$")) return "l-cmd";
  if(t.startsWith("#")) return "l-meta";
  if(/ERROR|ALERTA|FALL|Traceback|Error/.test(t)) return "l-err";
  if(/\[OK\]|CORRECTAMENTE|OK \(exit 0\)|Ingesta OK/.test(t)) return "l-ok";
  if(/WARN/.test(t)) return "l-warn";
  return "";
}

function appendLogs(lineas){
  const c = $("console");
  for(const t of lineas){
    const div = document.createElement("div");
    const cls = lineClass(t);
    if(cls) div.className = cls;
    div.textContent = t === "" ? " " : t;
    c.appendChild(div);
  }
  if($("autoscroll").checked) c.scrollTop = c.scrollHeight;
}

async function tickLogs(){
  try{
    const r = await fetch("/api/logs?offset=" + offset);
    const d = await r.json();
    if(d.lineas && d.lineas.length){ appendLogs(d.lineas); }
    offset = d.offset;
  }catch(e){}
}

async function tickStatus(){
  try{
    const r = await fetch("/api/status");
    const s = await r.json();
    badge(s.estado);
    if(s.config) renderCfg(s.config);
    $("s-obj").textContent = s.objetivo ? (s.objetivo === "completo" ? "Pipeline completo" : s.objetivo) : "—";
    $("s-dur").textContent = fmtDur(s.duracion);
    $("s-exit").textContent = s.exit_code == null ? "—" : s.exit_code;
    if(s.kpis) renderKpis(s.kpis);
    const debeCorrer = s.estado === "ejecutando";
    if(debeCorrer !== corriendo){
      setBusy(debeCorrer);
      if(!debeCorrer) refreshDb();   // recien termino: refresca Supabase
    }
  }catch(e){}
}

async function refreshDb(){
  try{
    const r = await fetch("/api/db");
    const d = await r.json();
    const set = (id,v)=> $(id).textContent = (v==null? "—" : v);
    if(d.disponible && d.conteos){
      set("db-notif", d.conteos.notificaciones);
      set("db-rech", d.conteos.rechazados);
      set("db-audit", d.conteos.load_audit);
    }else{
      ["db-notif","db-rech","db-audit"].forEach(id=> $(id).textContent="—");
    }
  }catch(e){}
}

async function run(objetivo){
  if(corriendo) return;
  $("console").innerHTML = ""; offset = 0;
  setBusy(true); badge("ejecutando");
  try{
    const r = await fetch("/api/run", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({objetivo})
    });
    if(r.status === 409){ alert("Ya hay una ejecucion en curso."); }
  }catch(e){ alert("No se pudo iniciar: " + e); setBusy(false); }
}

$("run-full").addEventListener("click", ()=> run("completo"));
document.querySelectorAll(".chip").forEach(c=>
  c.addEventListener("click", ()=> run(c.dataset.stage)));
$("clear").addEventListener("click", ()=> $("console").innerHTML = "");

// Bucle de refresco
tickStatus(); refreshDb();
setInterval(tickStatus, 1500);
setInterval(tickLogs, 1200);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):  # silencia el log por request de la stdlib
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        ruta = parsed.path
        if ruta in ("/", "/index.html"):
            return self._send(200, PAGINA, "text/html; charset=utf-8")
        if ruta == "/healthz":
            return self._send(200, "ok", "text/plain; charset=utf-8")
        if ruta == "/api/status":
            snap = ESTADO.snapshot()
            snap["config"] = {
                "fernet": bool(os.getenv("FERNET_KEY")),
                "database": bool(os.getenv("DATABASE_URL")),
            }
            snap["kpis"] = leer_kpis()
            return self._send(200, json.dumps(snap))
        if ruta == "/api/logs":
            q = parse_qs(parsed.query)
            try:
                offset = int((q.get("offset", ["0"])[0]) or 0)
            except ValueError:
                offset = 0
            lineas, total = ESTADO.logs_desde(offset)
            return self._send(200, json.dumps({"lineas": lineas, "offset": total}))
        if ruta == "/api/db":
            return self._send(200, json.dumps(contar_supabase()))
        return self._send(404, json.dumps({"error": "no encontrado"}))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/run":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                body = {}
            objetivo = body.get("objetivo", "completo")
            if objetivo != "completo" and objetivo not in ETAPAS:
                return self._send(400, json.dumps({"error": "objetivo invalido"}))
            if not lanzar(objetivo):
                return self._send(409, json.dumps({"error": "ya hay una ejecucion en curso"}))
            return self._send(202, json.dumps({"ok": True, "objetivo": objetivo}))
        return self._send(404, json.dumps({"error": "no encontrado"}))


def main():
    asegurar_dirs()
    port = int(os.environ.get("PORT", "10000"))
    servidor = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Panel DataOps escuchando en http://0.0.0.0:{port}")
    servidor.serve_forever()


if __name__ == "__main__":
    main()
