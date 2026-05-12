import asyncio

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>i4z-terminal-mcp</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css">
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--fg:#c9d1d9;--sidebar:#161b22;--panel:#11151b;
  --border:#30363d;--accent:#58a6ff;--accent-strong:#1f6feb;
  --muted:#8b949e;--muted-2:#484f58;--hover:#1f2937;--input:#0d1117;
  --button:#21262d;--button-hover:#30363d;--success:#3fb950;--danger:#f85149;
  --warning:#d29922;--tab-active:#161b22;--tab-bg:#0d1117;
  --sidebar-w:240px;--right-w:300px;--hdr-h:48px;
}
body[data-theme="light"]{
  --bg:#f6f8fa;--fg:#24292f;--sidebar:#ffffff;--panel:#ffffff;
  --border:#d0d7de;--accent:#0969da;--accent-strong:#0969da;
  --muted:#6e7781;--muted-2:#8c959f;--hover:#eaeef2;--input:#ffffff;
  --button:#f6f8fa;--button-hover:#eaeef2;--success:#1a7f37;--danger:#cf222e;
  --tab-active:#ffffff;--tab-bg:#f6f8fa;
}
html,body{height:100%;overflow:hidden}
body{display:flex;flex-direction:column;font-family:monospace;background:var(--bg);color:var(--fg)}

/* ── Header ── */
#header{height:var(--hdr-h);flex-shrink:0;display:flex;align-items:center;gap:8px;padding:0 12px;border-bottom:1px solid var(--border);background:var(--sidebar)}
#header .brand{font-size:13px;font-weight:bold;color:var(--accent);flex-shrink:0;margin-right:4px}
#health-dot{width:8px;height:8px;border-radius:50%;background:var(--muted-2);flex-shrink:0;cursor:help}
#health-dot.ok{background:var(--success)}
#health-dot.warn{background:var(--warning)}
#health-dot.bad{background:var(--danger)}
#health-text{font-size:10px;color:var(--muted);flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;min-width:0}
.hdr-btn{background:var(--button);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:11px;padding:5px 9px;border-radius:4px;cursor:pointer;white-space:nowrap;flex-shrink:0;min-height:30px;touch-action:manipulation}
.hdr-btn:hover{background:var(--button-hover)}
.hdr-btn.active{background:var(--accent-strong);color:#fff;border-color:var(--accent-strong)}
#hamburger-btn{font-size:16px;padding:5px 9px;display:none}

/* ── App body ── */
#app-body{flex:1;display:flex;overflow:hidden;min-height:0}

/* ── Resize handles ── */
.resize-handle{width:4px;background:var(--border);cursor:col-resize;flex-shrink:0;transition:background .12s;position:relative;touch-action:none}
.resize-handle::after{content:'';position:absolute;inset:0 -4px}
.resize-handle:hover,.resize-handle.dragging{background:var(--accent)}

/* ── Sidebar ── */
#sidebar{width:var(--sidebar-w);flex-shrink:0;background:var(--sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;transition:transform .25s ease}
#sidebar h2{padding:12px 14px;font-size:11px;color:var(--accent);border-bottom:1px solid var(--border);flex-shrink:0;letter-spacing:.06em;text-transform:uppercase}
#new-term-bar{display:flex;gap:6px;padding:8px 10px;border-bottom:1px solid var(--border);flex-shrink:0}
#new-term-name{flex:1;background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:12px;padding:7px 8px;border-radius:4px;outline:none;min-width:0;touch-action:manipulation}
#new-term-name:focus{border-color:var(--accent)}
#new-term-btn{background:var(--accent-strong);border:none;color:#fff;font-family:monospace;font-size:16px;min-width:32px;border-radius:4px;cursor:pointer;flex-shrink:0;touch-action:manipulation}
#new-term-btn:hover{filter:brightness(1.15)}
#term-list{flex:1;overflow-y:auto;padding:6px;-webkit-overflow-scrolling:touch}
.term-item{padding:10px 10px;cursor:pointer;border-radius:5px;font-size:12px;margin:2px 0;display:flex;align-items:center;gap:8px;min-height:44px;touch-action:manipulation}
.term-item:hover{background:var(--hover)}
.term-item.active{background:var(--accent-strong);color:#fff}
.term-item.in-tab{background:var(--hover)}
.sdot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.sdot.on{background:var(--success)}
.sdot.off{background:var(--danger)}
.term-label{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.term-info{flex:1;min-width:0}
.rename-input{flex:1;background:var(--input);border:1px solid var(--accent);color:var(--fg);font-family:monospace;font-size:12px;padding:2px 6px;border-radius:3px;outline:none;min-width:0}
#sidebar-footer{padding:6px 10px;border-top:1px solid var(--border);font-size:10px;color:var(--muted-2);flex-shrink:0}

/* ── Center ── */
#center{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
#tab-bar{display:flex;align-items:stretch;background:var(--tab-bg);border-bottom:1px solid var(--border);flex-shrink:0;min-height:38px;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch}
#tab-bar::-webkit-scrollbar{height:3px}
#tab-bar::-webkit-scrollbar-thumb{background:var(--border)}
.tab{display:flex;align-items:center;gap:6px;padding:0 12px;cursor:pointer;border-right:1px solid var(--border);font-size:12px;white-space:nowrap;background:var(--tab-bg);color:var(--muted);min-height:38px;flex-shrink:0;border-bottom:2px solid transparent;touch-action:manipulation}
.tab:hover{background:var(--hover);color:var(--fg)}
.tab.active{background:var(--tab-active);color:var(--fg);border-bottom-color:var(--accent)}
.tab .tab-dot{width:6px;height:6px;border-radius:50%;background:var(--success);flex-shrink:0}
.tab .tab-dot.off{background:var(--danger)}
.tab-close{background:none;border:none;color:inherit;cursor:pointer;padding:4px;border-radius:3px;font-size:13px;opacity:.5;line-height:1;touch-action:manipulation;min-width:24px;min-height:24px}
.tab-close:hover{opacity:1;background:var(--button)}
.term-del{background:none;border:none;color:inherit;cursor:pointer;padding:3px 5px;border-radius:3px;font-size:12px;opacity:0;margin-left:auto;touch-action:manipulation;line-height:1;flex-shrink:0}
.term-item:hover .term-del{opacity:.4}
.term-del:hover{opacity:1!important;color:var(--danger)}
#tab-placeholder{display:flex;align-items:center;padding:0 14px;font-size:12px;color:var(--muted-2)}
#terminals-wrap{flex:1;display:flex;overflow:hidden;position:relative}
.term-pane{flex:1;display:none;flex-direction:column;overflow:hidden;min-width:0}
.term-pane.visible{display:flex}
.term-pane.split{flex:none;width:50%}
.term-pane+.term-pane.split{border-left:1px solid var(--border)}
.xterm-container{flex:1;overflow:hidden;padding:4px}
.xterm-container .xterm{height:100%}
#empty-state{flex:1;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;color:var(--muted-2)}
#empty-state h3{font-size:16px;color:var(--muted)}
#empty-state p{font-size:12px}
#cmd-bar{display:none;padding:6px 10px;border-top:1px solid var(--border);background:var(--sidebar);flex-shrink:0;gap:6px;align-items:center;flex-wrap:wrap}
#cmd-bar.visible{display:flex}
#cmd-prompt{color:var(--accent);font-size:13px;flex-shrink:0}
#cmd-input{flex:1;min-width:120px;background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:16px;padding:8px 10px;border-radius:4px;outline:none;touch-action:manipulation}
#cmd-input:focus{border-color:var(--accent)}
.ctrl-btn{background:var(--button);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:11px;padding:7px 9px;border-radius:4px;cursor:pointer;flex-shrink:0;min-height:36px;touch-action:manipulation}
.ctrl-btn:hover{background:var(--button-hover)}

/* ── Right panel ── */
#right-panel{width:var(--right-w);flex-shrink:0;background:var(--sidebar);border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;transition:transform .25s ease}
body.panel-hidden #right-panel{display:none}
body.panel-hidden #resize-right-handle{display:none}
#panel-tabs{display:flex;border-bottom:1px solid var(--border);background:var(--bg);flex-shrink:0;overflow-x:auto}
#panel-tabs::-webkit-scrollbar{height:0}
.ptab{background:none;border:none;border-bottom:2px solid transparent;color:var(--muted);font-family:monospace;font-size:11px;padding:9px 10px;cursor:pointer;white-space:nowrap;flex-shrink:0;min-height:38px;touch-action:manipulation}
.ptab:hover{color:var(--fg)}
.ptab.active{color:var(--accent);border-bottom-color:var(--accent)}
#panel-body{flex:1;overflow-y:auto;padding:10px;-webkit-overflow-scrolling:touch}
.panel-section{display:none}
.panel-section.active{display:block}
.section-title{font-size:11px;color:var(--accent);font-weight:bold;letter-spacing:.05em;text-transform:uppercase;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid var(--border)}
.field-row{display:flex;gap:6px;margin-bottom:6px;align-items:center;flex-wrap:wrap}
.field-row label{font-size:11px;color:var(--muted);flex-shrink:0}
.p-input{background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:11px;padding:6px 7px;border-radius:4px;outline:none;flex:1;min-width:0;min-height:32px;touch-action:manipulation}
.p-input:focus{border-color:var(--accent)}
.p-textarea{background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:11px;padding:6px 7px;border-radius:4px;outline:none;width:100%;resize:vertical;min-height:52px}
.p-textarea:focus{border-color:var(--accent)}
.p-btn{background:var(--button);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:11px;padding:6px 8px;border-radius:4px;cursor:pointer;flex-shrink:0;min-height:32px;touch-action:manipulation}
.p-btn:hover{background:var(--button-hover)}
.p-btn:disabled{opacity:.5;cursor:not-allowed}
.p-pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:6px;font-size:10px;max-height:110px;overflow:auto;margin-top:4px;color:var(--fg)}
.list-box{display:flex;flex-direction:column;gap:3px;max-height:130px;overflow-y:auto;margin-top:4px}
.list-row{display:flex;justify-content:space-between;align-items:center;gap:6px;border:1px solid var(--border);border-radius:4px;padding:5px 7px;font-size:10px}
.list-row .lname{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.list-row button{background:none;border:1px solid var(--border);color:var(--danger);font-family:monospace;font-size:9px;padding:3px 6px;border-radius:3px;cursor:pointer;touch-action:manipulation}
.list-row button:hover{background:var(--danger);color:#fff}
.muted{color:var(--muted-2);font-size:10px;padding:4px 0}
.alert-badge{background:var(--danger);color:#fff;border-radius:10px;font-size:9px;padding:1px 5px;margin-left:4px}
.subsection{margin-top:10px}
.subsection .section-title{margin-top:0}

/* ── Overlay (mobile drawer backdrop) ── */
#overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.48);z-index:150;touch-action:manipulation}
#overlay.visible{display:block}

/* ── Responsive: Tablet (640–1023px) ── */
@media(max-width:1023px){
  #right-panel{
    position:fixed;right:0;top:var(--hdr-h);bottom:0;
    width:min(var(--right-w),85vw);
    z-index:200;
    transform:translateX(calc(min(var(--right-w),85vw) + 4px));
    box-shadow:-4px 0 20px rgba(0,0,0,.35);
    border-left:1px solid var(--border);
  }
  body.panel-hidden #right-panel{display:flex;transform:translateX(calc(min(var(--right-w),85vw) + 4px))}
  #right-panel.drawer-open{transform:translateX(0)!important}
  #resize-right-handle{display:none}
}

/* ── Responsive: Mobile (<640px) ── */
@media(max-width:639px){
  :root{--sidebar-w:82vw;--right-w:100vw}
  #hamburger-btn{display:flex;align-items:center;justify-content:center}
  #health-text{display:none}
  #sidebar{
    position:fixed;left:0;top:var(--hdr-h);bottom:0;
    width:var(--sidebar-w);
    z-index:200;
    transform:translateX(calc(-1 * var(--sidebar-w) - 4px));
    box-shadow:4px 0 20px rgba(0,0,0,.35);
  }
  #sidebar.drawer-open{transform:translateX(0)}
  #resize-sidebar-handle{display:none}
  #right-panel{
    position:fixed;left:0;right:0;bottom:0;
    width:100%!important;height:56vh;
    border-left:none;border-top:1px solid var(--border);
    transform:translateY(calc(56vh + 4px));
    box-shadow:0 -4px 20px rgba(0,0,0,.35);
  }
  body.panel-hidden #right-panel{display:flex;transform:translateY(calc(56vh + 4px))}
  #right-panel.drawer-open{transform:translateY(0)!important}
  #resize-right-handle{display:none}
  #cmd-bar{flex-wrap:wrap;padding:6px 8px;gap:4px}
  #cmd-input{font-size:16px;min-width:0}
  .hdr-btn:not(#hamburger-btn):not(#theme-btn){display:none}
  #theme-btn{font-size:10px;padding:5px 7px}
  .tab-close{min-width:28px;min-height:28px;font-size:14px}
  .term-item{min-height:48px;padding:10px 12px}
}

/* scrollbars */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-track{background:transparent}
.xterm-viewport{overflow-y:auto!important}
</style>
</head>
<body>

<!-- ── Header ── -->
<header id="header">
  <button class="hdr-btn" id="hamburger-btn" title="Toggle sidebar" aria-label="Toggle sidebar">&#9776;</button>
  <span class="brand">i4z-terminal-mcp</span>
  <span id="server-version" style="font-size:10px;color:var(--muted-2);margin-left:2px"></span>
  <span id="health-dot" title="Health"></span>
  <span id="health-text">loading...</span>
  <button class="hdr-btn" id="split-btn" title="Toggle split view">Split</button>
  <button class="hdr-btn" id="notify-btn" title="Enable browser notifications">Notify</button>
  <button class="hdr-btn" id="panel-toggle-btn" title="Toggle management panel">Panel</button>
  <button class="hdr-btn" id="theme-btn">Theme</button>
</header>

<div id="app-body">

<!-- ── Sidebar ── -->
<nav id="sidebar">
  <h2>Terminals</h2>
  <div id="new-term-bar">
    <input id="new-term-name" placeholder="Session name..." maxlength="80">
    <button id="new-term-btn" title="Create terminal">+</button>
  </div>
  <div id="term-list"></div>
  <div id="sidebar-footer"></div>
</nav>

<div id="resize-sidebar-handle" class="resize-handle" title="Drag to resize"></div>

<!-- ── Center ── -->
<main id="center">
  <div id="tab-bar">
    <div id="tab-placeholder">Open a terminal from the sidebar</div>
  </div>
  <div id="terminals-wrap">
    <div id="empty-state">
      <h3>No terminal selected</h3>
      <p>Create or select a terminal from the sidebar.</p>
    </div>
  </div>
  <div id="cmd-bar">
    <span id="cmd-prompt">$</span>
    <input id="cmd-input" placeholder="Send command (Enter to run)..." autocomplete="off">
    <button class="ctrl-btn" id="sigint-btn" title="Send Ctrl+C">Ctrl+C</button>
    <button class="ctrl-btn" id="sigterm-btn" title="Send SIGTERM">Term</button>
    <button class="ctrl-btn" id="clear-btn" title="Clear terminal (ctrl+l)">Clear</button>
  </div>
</main>

<div id="resize-right-handle" class="resize-handle" title="Drag to resize"></div>

<!-- ── Right panel ── -->
<aside id="right-panel">
  <div id="panel-tabs">
    <button class="ptab active" data-panel="profile">Profile</button>
    <button class="ptab" data-panel="workspace">Workspace</button>
    <button class="ptab" data-panel="alerts">Alerts <span id="alert-count-badge" class="alert-badge" style="display:none"></span></button>
    <button class="ptab" data-panel="checkpoints">Checkpoints</button>
    <button class="ptab" data-panel="snapshots">Snapshots</button>
  </div>
  <div id="panel-body">

    <!-- Profile panel -->
    <div class="panel-section active" id="section-profile">
      <div class="section-title">Session Profile</div>
      <div class="field-row">
        <input class="p-input" id="prof-key" placeholder="ENV_KEY" style="max-width:110px">
        <input class="p-input" id="prof-val" placeholder="value">
      </div>
      <div class="field-row">
        <button class="p-btn" id="prof-set-btn">Set env</button>
        <button class="p-btn" id="prof-unset-btn">Unset env</button>
      </div>
      <div class="field-row" style="margin-top:6px">
        <label>Startup commands</label>
      </div>
      <textarea class="p-textarea" id="prof-startup" placeholder="one command per line" rows="3"></textarea>
      <div class="field-row" style="margin-top:4px">
        <label><input type="checkbox" id="prof-run-now"> run now</label>
        <button class="p-btn" id="prof-save-btn">Save startup</button>
      </div>
      <div class="p-pre" id="prof-view" style="margin-top:6px">Select a terminal</div>
    </div>

    <!-- Workspace panel -->
    <div class="panel-section" id="section-workspace">
      <div class="section-title">Workspaces</div>
      <div class="field-row">
        <input class="p-input" id="ws-id-input" placeholder="workspace id">
        <button class="p-btn" id="ws-create-btn">Create</button>
      </div>
      <div class="field-row">
        <select class="p-input" id="ws-select" style="flex:1"></select>
        <button class="p-btn" id="ws-refresh-btn">↻</button>
      </div>
      <textarea class="p-textarea" id="ws-env-json" placeholder='env JSON {"KEY":"val"}' rows="2"></textarea>
      <textarea class="p-textarea" id="ws-startup" placeholder="startup commands" rows="2"></textarea>
      <div class="field-row" style="margin-top:4px">
        <button class="p-btn" id="ws-save-btn">Save &amp; Apply</button>
        <button class="p-btn" id="ws-add-member-btn">Add current</button>
        <button class="p-btn" id="ws-rm-member-btn">Remove current</button>
      </div>
      <div class="p-pre" id="ws-view">No workspace selected</div>
    </div>

    <!-- Alerts panel -->
    <div class="panel-section" id="section-alerts">
      <div class="section-title">Output Alerts</div>
      <div class="field-row">
        <select class="p-input" id="alert-scope" style="max-width:90px">
          <option value="session">session</option>
          <option value="global">global</option>
        </select>
        <input class="p-input" id="alert-pattern" placeholder="pattern">
      </div>
      <div class="field-row">
        <input class="p-input" id="alert-label" placeholder="label (optional)">
        <button class="p-btn" id="alert-add-btn">Add</button>
        <button class="p-btn" id="alert-refresh-btn">↻</button>
      </div>
      <div class="list-box" id="alert-list"></div>
      <div class="subsection">
        <div class="section-title">Recent Events</div>
        <div class="list-box" id="alert-events-list"></div>
      </div>
    </div>

    <!-- Checkpoints panel -->
    <div class="panel-section" id="section-checkpoints">
      <div class="section-title">Checkpoints</div>
      <div class="field-row">
        <input class="p-input" id="cp-label" placeholder="label">
        <input class="p-input" id="cp-note" placeholder="note">
      </div>
      <div class="field-row">
        <button class="p-btn" id="cp-add-btn">Add checkpoint</button>
        <button class="p-btn" id="cp-refresh-btn">↻</button>
      </div>
      <div class="list-box" id="cp-list"></div>
    </div>

    <!-- Snapshots panel -->
    <div class="panel-section" id="section-snapshots">
      <div class="section-title">Snapshots</div>
      <div class="field-row">
        <button class="p-btn" id="snap-export-btn">Export selected</button>
        <button class="p-btn" id="snap-import-btn">Import JSON</button>
      </div>
      <textarea class="p-textarea" id="snap-json" placeholder="Exported JSON (or paste to import)" rows="6"></textarea>
      <div class="p-pre" id="snap-status">No snapshot loaded</div>
    </div>

  </div>
</aside>

</div><!-- #app-body -->
<div id="overlay"></div>

<script>
// ════════════════════════════════════════════════════════
//  Utilities
// ════════════════════════════════════════════════════════
const $=id=>document.getElementById(id);
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
async function api(url,opts={}){
  const r=await fetch(url,opts);
  const d=await r.json();
  if(!r.ok)throw new Error(d.error||'request failed');
  return d;
}
function notify(title,body){
  if(Notification.permission==='granted'){
    new Notification(title,{body,icon:''});
  }
}

// ════════════════════════════════════════════════════════
//  App state
// ════════════════════════════════════════════════════════
let theme = localStorage.getItem('i4z-theme') ||
  ((window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark');

// Map of terminal_id -> TerminalState
const terms = new Map();

// Currently visible tab ids
let primaryTab = null;   // main active tab
let splitTab   = null;   // split-view second tab
let splitMode  = false;

// Right panel
let panelVisible = true;
let activePanel  = 'profile';

// Command history per terminal_id in sessionStorage
function getCmdHistory(id){try{return JSON.parse(sessionStorage.getItem('hist:'+id)||'[]')}catch{return[]}}
function pushCmdHistory(id,cmd){
  const h=getCmdHistory(id);
  if(h[h.length-1]===cmd)return;
  h.push(cmd);
  if(h.length>200)h.shift();
  sessionStorage.setItem('hist:'+id,JSON.stringify(h));
}
let cmdHistIdx = -1;

// Alert event tracking
let lastAlertEventId = 0;

// ════════════════════════════════════════════════════════
//  Terminal state object
// ════════════════════════════════════════════════════════
class TerminalState {
  constructor(id){
    this.id      = id;
    this.xterm   = null;
    this.fit     = null;
    this.ws      = null;
    this.alive   = false;
    this.pane    = null;   // .term-pane DOM element
    this.xtEl    = null;   // .xterm-container DOM element
    this.cursor  = 0;
    this.reconnect = true;
  }
}

// ════════════════════════════════════════════════════════
//  xterm.js helpers
// ════════════════════════════════════════════════════════
function xtermTheme(){
  if(theme==='dark') return {
    background:'#0d1117',foreground:'#c9d1d9',cursor:'#58a6ff',
    black:'#484f58',red:'#ff7b72',green:'#3fb950',yellow:'#d29922',
    blue:'#58a6ff',magenta:'#bc8cff',cyan:'#39c5cf',white:'#b1bac4',
    brightBlack:'#6e7681',brightRed:'#ffa198',brightGreen:'#56d364',
    brightYellow:'#e3b341',brightBlue:'#79c0ff',brightMagenta:'#d2a8ff',
    brightCyan:'#56d4dd',brightWhite:'#f0f6fc'
  };
  return {
    background:'#f6f8fa',foreground:'#24292f',cursor:'#0969da',
    black:'#24292f',red:'#cf222e',green:'#1a7f37',yellow:'#9a6700',
    blue:'#0969da',magenta:'#8250df',cyan:'#0550ae',white:'#6e7781',
    brightBlack:'#57606a',brightRed:'#a40e26',brightGreen:'#116329',
    brightYellow:'#7d4e00',brightBlue:'#0550ae',brightMagenta:'#6639ba',
    brightCyan:'#0969da',brightWhite:'#8c959f'
  };
}

function buildXterm(state){
  const FitAddonClass = (window.FitAddon && window.FitAddon.FitAddon) ? window.FitAddon.FitAddon : window.FitAddon;
  const term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: '"Cascadia Code","Fira Code","JetBrains Mono",monospace',
    theme: xtermTheme(),
    scrollback: 5000,
    convertEol: false,
    allowProposedApi: true,
  });
  let fit = null;
  if(FitAddonClass){
    fit = new FitAddonClass();
    term.loadAddon(fit);
  }
  state.xterm = term;
  state.fit   = fit;
  term.open(state.xtEl);
  if(fit) fit.fit();

  // Keyboard → PTY raw
  term.onData(data => {
    if(state.ws && state.ws.readyState === 1){
      state.ws.send(JSON.stringify({type:'input',text:data}));
    }
  });
  // Resize → PTY
  term.onResize(({rows,cols}) => {
    if(state.ws && state.ws.readyState === 1){
      state.ws.send(JSON.stringify({type:'resize',rows,cols}));
    }
  });
  // Observe container resize
  const ro = new ResizeObserver(() => { if(fit && state.pane.classList.contains('visible')) fit.fit(); });
  ro.observe(state.xtEl);
  return term;
}

// ════════════════════════════════════════════════════════
//  WebSocket connection per terminal
// ════════════════════════════════════════════════════════
function connectWS(state){
  if(state.ws){ try{state.ws.close()}catch{} }
  state.reconnect = true;
  const proto = location.protocol==='https:'?'wss:':'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/${encodeURIComponent(state.id)}?since=0`);
  state.ws = ws;
  ws.onmessage = ev => {
    let msg;
    try{ msg=JSON.parse(ev.data) }catch{ return }
    if(msg.type==='history'){
      const events = msg.events||[];
      if(state.xterm){
        for(const e of events){
          if(e.type==='output') state.xterm.write(e.text);
          else if(e.type==='input'){
            // show user input hint in muted colour
            state.xterm.write('\\x1b[2m'+e.text+'\\x1b[0m');
          }
        }
        if(state.fit) state.fit.fit();
      }
      state.cursor = msg.cursor||0;
    } else if(msg.type==='output'){
      if(state.xterm) state.xterm.write(msg.text||'');
      state.cursor = msg.cursor||state.cursor;
    } else if(msg.type==='status'){
      const s=msg.status||{};
      state.alive = !!s.alive;
      updateTabDot(state.id, state.alive);
      updateSidebarDot(state.id, state.alive);
      if(primaryTab===state.id) updateCmdBar();
      if(!state.alive) state.reconnect=false;
    }
  };
  ws.onclose = () => {
    if(state.reconnect && state.alive){
      setTimeout(()=>connectWS(state), 1500);
    } else if(!state.reconnect){
      updateTabDot(state.id, false);
      updateSidebarDot(state.id, false);
    }
  };
  ws.onerror = () => {};
}

// ════════════════════════════════════════════════════════
//  Tab management
// ════════════════════════════════════════════════════════
function openTab(id){
  if(!id || id==='undefined') return;
  // On mobile, close sidebar drawer when a terminal is selected
  if(isMobile()) closeDrawers();
  if(primaryTab===id) return;
  if(terms.has(id)){
    primaryTab = id;
    renderTabs();
    showPanes();
    updateCmdBar();
    cmdHistIdx = -1;
    loadProfile();
    loadAlerts();
    loadCheckpoints();
    loadWorkspaces();
    return;
  }
  // Create new pane and state
  const state = new TerminalState(id);
  terms.set(id, state);

  const pane = document.createElement('div');
  pane.className = 'term-pane';
  pane.dataset.id = id;
  const xtEl = document.createElement('div');
  xtEl.className = 'xterm-container';
  pane.appendChild(xtEl);
  $('terminals-wrap').appendChild(pane);
  state.pane = pane;
  state.xtEl = xtEl;

  buildXterm(state);
  connectWS(state);
  primaryTab = id;
  renderTabs();
  showPanes();
  updateCmdBar();
  cmdHistIdx = -1;
  loadProfile();
  loadAlerts();
  loadCheckpoints();
  loadWorkspaces();
}

function closeTab(id){
  const state = terms.get(id);
  if(state){
    state.reconnect = false;
    if(state.ws) try{state.ws.close()}catch{}
    if(state.xterm) state.xterm.dispose();
    if(state.pane) state.pane.remove();
    terms.delete(id);
  }
  if(primaryTab===id){
    primaryTab = terms.size ? [...terms.keys()][0] : null;
  }
  if(splitTab===id) splitTab=null;
  renderTabs();
  showPanes();
  updateCmdBar();
}

function renderTabs(){
  const bar = $('tab-bar');
  // Remove only tab elements — never touch #tab-placeholder so it stays in the DOM
  bar.querySelectorAll('.tab').forEach(el => el.remove());
  const placeholder = bar.querySelector('#tab-placeholder');
  if(terms.size===0){
    if(placeholder) placeholder.style.display='flex';
    return;
  }
  if(placeholder) placeholder.style.display='none';
  for(const [id,state] of terms){
    const tab = document.createElement('div');
    tab.className = 'tab'+(id===primaryTab?' active':'');
    tab.dataset.id = id;
    const dot = document.createElement('span');
    dot.className = 'tab-dot'+(state.alive?'':' off');
    dot.dataset.dot = id;
    const label = document.createElement('span');
    label.textContent = id;
    const close = document.createElement('button');
    close.className='tab-close';
    close.title='Close tab (does not kill terminal)';
    close.textContent='×';
    close.onclick=e=>{e.stopPropagation();closeTab(id)};
    tab.appendChild(dot);
    tab.appendChild(label);
    tab.appendChild(close);
    tab.onclick=()=>openTab(id);
    bar.appendChild(tab);
  }
}

function showPanes(){
  // Hide all panes first
  for(const state of terms.values()){
    state.pane.classList.remove('visible','split');
  }
  $('empty-state').style.display='none';

  if(!primaryTab){
    $('empty-state').style.display='flex';
    return;
  }

  const primary = terms.get(primaryTab);
  if(!primary){ $('empty-state').style.display='flex'; return; }

  if(splitMode && splitTab && terms.has(splitTab) && splitTab!==primaryTab){
    primary.pane.classList.add('visible','split');
    const sec = terms.get(splitTab);
    sec.pane.classList.add('visible','split');
    if(primary.fit) primary.fit.fit();
    if(sec.fit) sec.fit.fit();
  } else {
    primary.pane.classList.add('visible');
    if(primary.fit) primary.fit.fit();
  }
}

function updateTabDot(id, alive){
  const dot = document.querySelector(`.tab-dot[data-dot="${CSS.escape(id)}"]`);
  if(dot){ dot.className='tab-dot'+(alive?'':' off') }
}

function updateSidebarDot(id, alive){
  const el = document.querySelector(`.sdot[data-dot="${CSS.escape(id)}"]`);
  if(el){ el.className='sdot '+(alive?'on':'off') }
}

function updateCmdBar(){
  const bar = $('cmd-bar');
  if(primaryTab && terms.has(primaryTab)){
    bar.className='visible';
    const state = terms.get(primaryTab);
    $('cmd-input').disabled = !state.alive;
  } else {
    bar.className='';
  }
}

// ════════════════════════════════════════════════════════
//  Sidebar – terminal list
// ════════════════════════════════════════════════════════
let allTerminals = [];

async function refreshSidebar(){
  try{
    const data = await api('/api/terminals');
    allTerminals = data;
    $('sidebar-footer').textContent = data.length ? data.length+' terminal(s)' : '';
    // Update alive state for open tabs
    for(const t of data){
      const state = terms.get(t.id);
      if(state && state.alive !== t.alive){
        // state is updated via WS, just sync dot
        updateSidebarDot(t.id, state.alive);
      }
    }
    renderSidebar(data);
  }catch{}
}

function renderSidebar(data){
  const list = $('term-list');
  if(!data.length){
    list.innerHTML='<div style="color:var(--muted-2);padding:12px;font-size:12px">No terminals</div>';
    return;
  }
  list.innerHTML='';
  for(const t of data){
    const item = document.createElement('div');
    const state = terms.get(t.id);
    const alive = state ? state.alive : t.alive;
    const isActive = primaryTab===t.id;
    const inTab = terms.has(t.id);
    item.className='term-item'+(isActive?' active':inTab?' in-tab':'');
    item.dataset.id=t.id;
    const dot = document.createElement('span');
    dot.className='sdot '+(alive?'on':'off');
    dot.dataset.dot=t.id;
    const info = document.createElement('div');
    info.className='term-info';
    const label = document.createElement('div');
    label.className='term-label';
    label.textContent=t.id;
    info.appendChild(label);
    const del = document.createElement('button');
    del.className='term-del';
    del.title='Delete terminal and all history';
    del.textContent='×';
    del.onclick=e=>{e.stopPropagation();deleteTerminal(t.id)};
    item.appendChild(dot);
    item.appendChild(info);
    item.appendChild(del);
    item.onclick=()=>openTab(t.id);
    item.ondblclick=e=>{e.stopPropagation();startRename(item,t.id)};
    list.appendChild(item);
  }
}

function startRename(item, id){
  const info = item.querySelector('.term-info');
  const old = info.querySelector('.term-label');
  const inp = document.createElement('input');
  inp.className='rename-input';
  inp.value=id;
  info.replaceChild(inp,old);
  inp.focus();
  inp.select();
  item.onclick=null;
  async function commit(){
    const newId = inp.value.trim();
    if(newId && newId!==id){
      try{
        await api('/api/rename/'+encodeURIComponent(id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_id:newId})});
        // Update local state
        if(terms.has(id)){
          const state = terms.get(id);
          state.id=newId;
          terms.delete(id);
          terms.set(newId,state);
          if(primaryTab===id) primaryTab=newId;
          if(splitTab===id) splitTab=newId;
          renderTabs();
        }
      }catch(e){ alert(e.message||'rename failed') }
    }
    refreshSidebar();
  }
  inp.onblur=commit;
  inp.onkeydown=e=>{
    if(e.key==='Enter'){e.preventDefault();inp.blur()}
    if(e.key==='Escape'){inp.value=id;inp.blur()}
  };
}

async function deleteTerminal(id){
  if(!confirm(`Delete terminal "${id}" and all its history? This cannot be undone.`)) return;
  try{
    await api('/api/terminals/'+encodeURIComponent(id),{method:'DELETE'});
    if(terms.has(id)) closeTab(id);
    await refreshSidebar();
  }catch(e){ alert(e.message||'delete failed') }
}

// ════════════════════════════════════════════════════════
//  Create terminal
// ════════════════════════════════════════════════════════
async function createTerminal(){
  const inp=$('new-term-name');
  const name=inp.value.trim();
  if(!name)return;
  try{
    const d=await api('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,interactive:true})});
    inp.value='';
    await refreshSidebar();
    openTab(d.terminal_id);
  }catch(e){ alert(e.message||'create failed') }
}

// ════════════════════════════════════════════════════════
//  Command bar
// ════════════════════════════════════════════════════════
async function sendCommand(){
  const inp=$('cmd-input');
  const text=inp.value;
  if(!text||!primaryTab)return;
  const state=terms.get(primaryTab);
  if(!state||!state.alive)return;
  inp.value='';
  cmdHistIdx=-1;
  pushCmdHistory(primaryTab,text);
  try{
    await api('/api/send/'+encodeURIComponent(primaryTab),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text+'\\n'})});
  }catch{}
}

$('cmd-input').onkeydown=function(e){
  if(e.key==='Enter'){e.preventDefault();sendCommand();return}
  const h=getCmdHistory(primaryTab||'');
  if(e.key==='ArrowUp'){
    e.preventDefault();
    if(cmdHistIdx===-1) cmdHistIdx=h.length-1;
    else if(cmdHistIdx>0) cmdHistIdx--;
    if(h[cmdHistIdx]!==undefined) this.value=h[cmdHistIdx];
    return;
  }
  if(e.key==='ArrowDown'){
    e.preventDefault();
    if(cmdHistIdx<h.length-1){ cmdHistIdx++; this.value=h[cmdHistIdx]||'' }
    else{ cmdHistIdx=-1; this.value='' }
    return;
  }
  cmdHistIdx=-1;
};

// Ctrl+C / SIGTERM / Clear
$('sigint-btn').onclick=async()=>{
  if(!primaryTab)return;
  try{ await api('/api/signal/'+encodeURIComponent(primaryTab),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({signal:'SIGINT'})}) }catch{}
};
$('sigterm-btn').onclick=async()=>{
  if(!primaryTab)return;
  try{ await api('/api/signal/'+encodeURIComponent(primaryTab),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({signal:'SIGTERM'})}) }catch{}
};
$('clear-btn').onclick=()=>{
  const state=terms.get(primaryTab||'');
  if(state && state.xterm) state.xterm.clear();
  if(primaryTab){
    const s=terms.get(primaryTab);
    if(s&&s.ws&&s.ws.readyState===1) s.ws.send(JSON.stringify({type:'input',text:'\\x0c'}));
  }
};

// ════════════════════════════════════════════════════════
//  Drawer helpers (mobile/tablet)
// ════════════════════════════════════════════════════════
function isMobile(){ return window.innerWidth < 640 }
function isTablet(){ return window.innerWidth >= 640 && window.innerWidth < 1024 }
function isSmallScreen(){ return window.innerWidth < 1024 }

function closeDrawers(){
  $('sidebar').classList.remove('drawer-open');
  $('right-panel').classList.remove('drawer-open');
  $('overlay').classList.remove('visible');
}

function openSidebarDrawer(){
  $('sidebar').classList.add('drawer-open');
  $('right-panel').classList.remove('drawer-open');
  $('overlay').classList.add('visible');
}

function openRightDrawer(){
  $('right-panel').classList.add('drawer-open');
  $('sidebar').classList.remove('drawer-open');
  $('overlay').classList.add('visible');
  // ensure panel is not hidden by desktop class
  $('right-panel').style.display='flex';
}

$('overlay').onclick = closeDrawers;

// ════════════════════════════════════════════════════════
//  Header controls
// ════════════════════════════════════════════════════════
$('new-term-btn').onclick=createTerminal;
$('new-term-name').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();createTerminal()}};

$('hamburger-btn').onclick=function(){
  if($('sidebar').classList.contains('drawer-open')) closeDrawers();
  else openSidebarDrawer();
};

$('split-btn').onclick=function(){
  splitMode=!splitMode;
  this.classList.toggle('active',splitMode);
  if(splitMode){
    const ids=[...terms.keys()];
    const other=ids.find(id=>id!==primaryTab);
    if(other) splitTab=other;
    else{ splitMode=false; this.classList.remove('active'); alert('Open another terminal tab first'); return }
  }
  showPanes();
};

$('notify-btn').onclick=async function(){
  if(Notification.permission==='granted'){ this.textContent='Notify ✓'; return }
  const p=await Notification.requestPermission();
  if(p==='granted'){ this.textContent='Notify ✓'; this.classList.add('active') }
};

$('panel-toggle-btn').onclick=function(){
  if(isSmallScreen()){
    // Mobile/tablet: slide drawer from edge
    if($('right-panel').classList.contains('drawer-open')) closeDrawers();
    else openRightDrawer();
  } else {
    // Desktop: inline show/hide
    panelVisible=!panelVisible;
    document.body.classList.toggle('panel-hidden',!panelVisible);
    this.classList.toggle('active',panelVisible);
    setTimeout(()=>{ for(const s of terms.values()) if(s.fit) s.fit.fit() },60);
  }
};

$('theme-btn').onclick=function(){
  theme=theme==='dark'?'light':'dark';
  applyTheme();
};

// ════════════════════════════════════════════════════════
//  Drag-to-resize panels (desktop only)
// ════════════════════════════════════════════════════════
function setupResize(handleId, cssVar, getSide){
  const handle = $(handleId);
  if(!handle) return;
  handle.addEventListener('pointerdown', e=>{
    if(isSmallScreen()) return;
    const startX = e.clientX;
    const sideEl = getSide();
    const startW = sideEl.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.body.style.cursor='col-resize';
    document.body.style.userSelect='none';
    e.preventDefault();
    function onMove(e){
      const delta = cssVar==='--sidebar-w' ? e.clientX-startX : startX-e.clientX;
      const newW = Math.max(160, Math.min(560, startW+delta));
      document.documentElement.style.setProperty(cssVar, newW+'px');
      localStorage.setItem('resize-'+cssVar, String(newW));
      for(const s of terms.values()) if(s.fit) s.fit.fit();
    }
    function onUp(){
      handle.classList.remove('dragging');
      document.body.style.cursor='';
      document.body.style.userSelect='';
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
    }
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onUp);
  });
}
setupResize('resize-sidebar-handle','--sidebar-w',()=>$('sidebar'));
setupResize('resize-right-handle','--right-w',()=>$('right-panel'));

// Restore saved widths (desktop only)
if(!isSmallScreen()){
  const sw=localStorage.getItem('resize---sidebar-w');
  if(sw) document.documentElement.style.setProperty('--sidebar-w',sw+'px');
  const rw=localStorage.getItem('resize---right-w');
  if(rw) document.documentElement.style.setProperty('--right-w',rw+'px');
}

// Re-fit terminals on window resize
window.addEventListener('resize',()=>{
  for(const s of terms.values()) if(s.fit && s.pane.classList.contains('visible')) s.fit.fit();
});

function applyTheme(){
  document.body.dataset.theme=theme;
  localStorage.setItem('i4z-theme',theme);
  $('theme-btn').textContent='Theme: '+theme;
  for(const s of terms.values()){
    if(s.xterm) s.xterm.options.theme=xtermTheme();
  }
}

// ════════════════════════════════════════════════════════
//  Right panel tabs
// ════════════════════════════════════════════════════════
document.querySelectorAll('.ptab').forEach(btn=>{
  btn.onclick=()=>{
    activePanel=btn.dataset.panel;
    document.querySelectorAll('.ptab').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.panel-section').forEach(s=>s.classList.remove('active'));
    btn.classList.add('active');
    $('section-'+activePanel).classList.add('active');
    // Refresh panel content
    if(activePanel==='profile') loadProfile();
    else if(activePanel==='workspace') loadWorkspaces();
    else if(activePanel==='alerts'){ loadAlerts(); loadAlertEvents(); }
    else if(activePanel==='checkpoints') loadCheckpoints();
  };
});

// ════════════════════════════════════════════════════════
//  Profile panel
// ════════════════════════════════════════════════════════
async function loadProfile(){
  if(!primaryTab){ $('prof-view').textContent='Select a terminal'; $('prof-startup').value=''; return }
  try{
    const d=await api('/api/profile/'+encodeURIComponent(primaryTab));
    $('prof-view').textContent=JSON.stringify(d,null,2);
    $('prof-startup').value=(d.startup_commands||[]).join('\\n');
  }catch(e){ $('prof-view').textContent=e.message||'unavailable' }
}
$('prof-set-btn').onclick=async()=>{
  if(!primaryTab) return;
  const key=$('prof-key').value.trim(), val=$('prof-val').value;
  if(!key)return;
  try{ await api('/api/profile/'+encodeURIComponent(primaryTab),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({set_env:{[key]:val}})}); loadProfile() }catch(e){alert(e.message)}
};
$('prof-unset-btn').onclick=async()=>{
  if(!primaryTab) return;
  const key=$('prof-key').value.trim();
  if(!key)return;
  try{ await api('/api/profile/'+encodeURIComponent(primaryTab),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({unset_env:[key]})}); loadProfile() }catch(e){alert(e.message)}
};
$('prof-save-btn').onclick=async()=>{
  if(!primaryTab) return;
  const startup_commands=$('prof-startup').value.split('\\n').map(s=>s.trim()).filter(Boolean);
  const run_startup_commands=$('prof-run-now').checked;
  try{ await api('/api/profile/'+encodeURIComponent(primaryTab),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({startup_commands,run_startup_commands})}); loadProfile() }catch(e){alert(e.message)}
};

// ════════════════════════════════════════════════════════
//  Workspace panel
// ════════════════════════════════════════════════════════
async function loadWorkspaces(){
  try{
    const items=await api('/api/workspaces');
    const sel=$('ws-select');
    const cur=sel.value;
    sel.innerHTML=items.map(w=>`<option value="${esc(w.id)}">${esc(w.id)} (${w.member_count||0})</option>`).join('');
    if(cur&&items.find(w=>w.id===cur)) sel.value=cur;
    else if(items.length) sel.value=items[0].id;
    loadWorkspaceDetail();
  }catch{}
}
async function loadWorkspaceDetail(){
  const id=$('ws-select').value;
  if(!id){ $('ws-view').textContent='No workspace selected'; return }
  try{
    const d=await api('/api/workspaces/'+encodeURIComponent(id));
    $('ws-view').textContent=JSON.stringify(d,null,2);
    $('ws-env-json').value=JSON.stringify(d.env||{},null,2);
    $('ws-startup').value=(d.startup_commands||[]).join('\\n');
  }catch(e){ $('ws-view').textContent=e.message }
}
$('ws-select').onchange=loadWorkspaceDetail;
$('ws-refresh-btn').onclick=loadWorkspaces;
$('ws-create-btn').onclick=async()=>{
  const workspace_id=$('ws-id-input').value.trim();
  if(!workspace_id)return;
  try{
    let env={};
    const raw=$('ws-env-json').value.trim();
    if(raw) env=JSON.parse(raw);
    const startup_commands=$('ws-startup').value.split('\\n').map(s=>s.trim()).filter(Boolean);
    await api('/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id,env,startup_commands})});
    $('ws-id-input').value='';
    loadWorkspaces();
  }catch(e){alert(e.message)}
};
$('ws-save-btn').onclick=async()=>{
  const id=$('ws-select').value;
  if(!id)return;
  try{
    let set_env={};
    const raw=$('ws-env-json').value.trim();
    if(raw) set_env=JSON.parse(raw);
    const startup_commands=$('ws-startup').value.split('\\n').map(s=>s.trim()).filter(Boolean);
    await api('/api/workspaces/'+encodeURIComponent(id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({set_env,startup_commands,apply_to_members:true})});
    loadWorkspaceDetail(); loadProfile();
  }catch(e){alert(e.message)}
};
$('ws-add-member-btn').onclick=async()=>{
  const id=$('ws-select').value;
  if(!id||!primaryTab)return;
  try{ await api('/api/workspaces/'+encodeURIComponent(id)+'/members',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({terminal_id:primaryTab})}); loadWorkspaceDetail() }catch(e){alert(e.message)}
};
$('ws-rm-member-btn').onclick=async()=>{
  const id=$('ws-select').value;
  if(!id||!primaryTab)return;
  try{ await api('/api/workspaces/'+encodeURIComponent(id)+'/members/'+encodeURIComponent(primaryTab),{method:'DELETE'}); loadWorkspaceDetail() }catch(e){alert(e.message)}
};

// ════════════════════════════════════════════════════════
//  Alerts panel
// ════════════════════════════════════════════════════════
async function loadAlerts(){
  try{
    const qs=primaryTab?'?terminal_id='+encodeURIComponent(primaryTab):'';
    const items=await api('/api/alerts'+qs);
    const list=$('alert-list');
    list.innerHTML=items.length
      ?items.map(a=>`<div class="list-row"><span class="lname">${esc(a.scope)} ${esc(a.pattern)}${a.terminal_id?' @ '+esc(a.terminal_id):''}</span><button data-id="${esc(a.id)}">✕</button></div>`).join('')
      :'<div class="muted">No alerts</div>';
    list.querySelectorAll('button[data-id]').forEach(b=>b.onclick=()=>removeAlert(b.dataset.id));
  }catch{}
}
async function loadAlertEvents(){
  try{
    const qs='?since='+lastAlertEventId+(primaryTab?'&terminal_id='+encodeURIComponent(primaryTab):'');
    const items=await api('/api/alert-events'+qs);
    if(items.length){
      lastAlertEventId=items[items.length-1].id||lastAlertEventId;
      const list=$('alert-events-list');
      for(const e of items){
        const row=document.createElement('div');
        row.className='list-row';
        row.innerHTML=`<span class="lname">${esc(e.terminal_id)}: ${esc(e.pattern)} → ${esc((e.matched_text||'').slice(0,60))}</span>`;
        list.prepend(row);
        // Browser notification
        notify('Alert: '+e.pattern,'Terminal: '+e.terminal_id+'\\n'+e.matched_text);
      }
      // Badge
      const badge=$('alert-count-badge');
      badge.style.display='inline';
      badge.textContent='+'+items.length;
    }
  }catch{}
}
async function removeAlert(id){
  try{ await api('/api/alerts/'+encodeURIComponent(id),{method:'DELETE'}); loadAlerts() }catch(e){alert(e.message)}
}
$('alert-add-btn').onclick=async()=>{
  const scope=$('alert-scope').value;
  const pattern=$('alert-pattern').value.trim();
  const label=$('alert-label').value.trim()||undefined;
  if(!pattern)return;
  try{
    await api('/api/alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,pattern,label,terminal_id:scope==='session'?primaryTab:null})});
    $('alert-pattern').value=''; $('alert-label').value='';
    loadAlerts();
  }catch(e){alert(e.message)}
};
$('alert-refresh-btn').onclick=()=>{ loadAlerts(); loadAlertEvents() };

// ════════════════════════════════════════════════════════
//  Checkpoints panel
// ════════════════════════════════════════════════════════
async function loadCheckpoints(){
  try{
    const qs=primaryTab?'?terminal_id='+encodeURIComponent(primaryTab):'';
    const items=await api('/api/checkpoints'+qs);
    $('cp-list').innerHTML=items.length
      ?items.map(c=>`<div class="list-row"><span class="lname">${esc(c.label)}${c.note?' — '+esc(c.note):''}</span><button data-id="${esc(c.id)}">✕</button></div>`).join('')
      :'<div class="muted">No checkpoints</div>';
    $('cp-list').querySelectorAll('button[data-id]').forEach(b=>b.onclick=async()=>{
      try{ await api('/api/checkpoints/'+encodeURIComponent(b.dataset.id),{method:'DELETE'}); loadCheckpoints() }catch(e){alert(e.message)}
    });
  }catch{}
}
$('cp-add-btn').onclick=async()=>{
  if(!primaryTab){ alert('Select a terminal first'); return }
  const label=$('cp-label').value.trim(), note=$('cp-note').value.trim()||undefined;
  if(!label)return;
  try{ await api('/api/checkpoints',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({terminal_id:primaryTab,label,note})}); $('cp-label').value=''; $('cp-note').value=''; loadCheckpoints() }catch(e){alert(e.message)}
};
$('cp-refresh-btn').onclick=loadCheckpoints;

// ════════════════════════════════════════════════════════
//  Snapshots panel
// ════════════════════════════════════════════════════════
$('snap-export-btn').onclick=async()=>{
  if(!primaryTab){ alert('Select a terminal first'); return }
  try{ const d=await api('/api/export/'+encodeURIComponent(primaryTab)); $('snap-json').value=JSON.stringify(d,null,2); $('snap-status').textContent='Exported '+primaryTab }catch(e){alert(e.message)}
};
$('snap-import-btn').onclick=async()=>{
  const raw=$('snap-json').value.trim();
  if(!raw){ alert('Paste a snapshot JSON first'); return }
  try{ const snapshot=JSON.parse(raw); const d=await api('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({snapshot})}); $('snap-status').textContent='Imported '+d.terminal_id; refreshSidebar() }catch(e){alert(e.message)}
};

// ════════════════════════════════════════════════════════
//  Health
// ════════════════════════════════════════════════════════
async function loadHealth(){
  try{
    const d=await api('/api/health');
    const ok=d.db&&d.db.ok;
    const counts=d.counts||{};
    const sessions=d.sessions||{};
    const errs=(d.reader_errors||[]).length;
    const dot=$('health-dot');
    if(!ok||errs>0){ dot.className='health-dot bad'; }
    else if((sessions.stale||[]).length>0){ dot.className='health-dot warn'; }
    else { dot.className='health-dot ok'; }
    $('health-text').textContent=`db:${ok?'ok':'ERR'} · active:${sessions.active||0} · alerts:${counts.alerts||0} · ws:${counts.workspaces||0}${errs?' · ⚠ '+errs+' err':''}`;
  }catch{
    $('health-dot').className='health-dot bad';
    $('health-text').textContent='health unavailable';
  }
}

// ════════════════════════════════════════════════════════
//  Boot
// ════════════════════════════════════════════════════════
applyTheme();

// On small screens the panel starts hidden (it's a drawer, not inline)
if(isSmallScreen()){
  panelVisible = false;
  document.body.classList.add('panel-hidden');
  $('panel-toggle-btn').classList.remove('active');
} else {
  $('panel-toggle-btn').classList.add('active');
}

if(Notification.permission==='granted') $('notify-btn').classList.add('active');

// Initial loads
refreshSidebar();
loadHealth();
loadWorkspaces();
api('/api/info').then(d=>{
  const el=$('server-version');
  if(el) el.textContent=`v${d.version||'?'} (${d.implementation||'?'})`;
}).catch(()=>{});

// Polling
setInterval(refreshSidebar, 3000);
setInterval(loadHealth, 6000);
setInterval(loadAlertEvents, 8000);
</script>
</body>
</html>"""


def create_app(manager):
    from terminal.log import log

    async def index(request):
        log("GET /", "WEB")
        return HTMLResponse(HTML)

    async def api_terminals(request):
        log("GET /api/terminals", "WEB")
        return JSONResponse(manager.list_all())

    async def api_create(request: Request):
        body = await request.json()
        name = str(body.get("name", "")).strip()
        if not name:
            return JSONResponse({"error": "terminal name cannot be empty"}, status_code=400)
        interactive = bool(body.get("interactive", False))
        try:
            session = await manager.create(
                name,
                env=body.get("env"),
                startup_commands=body.get("startup_commands"),
                workspace_id=body.get("workspace_id"),
                interactive=interactive,
            )
            log(f"POST /api/create '{session.id}' interactive={interactive}", "WEB")
            return JSONResponse({"terminal_id": session.id, "status": "created"})
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def api_kill(request):
        terminal_id = request.path_params["terminal_id"]
        try:
            await manager.kill(terminal_id)
            log(f"POST /api/kill/{terminal_id}", "WEB")
            return JSONResponse({"status": "killed"})
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)

    async def api_delete(request: Request):
        terminal_id = request.path_params["terminal_id"]
        result = await manager.delete_terminal(terminal_id)
        log(f"DELETE /api/terminals/{terminal_id}", "WEB")
        return JSONResponse(result)

    async def api_rename(request: Request):
        terminal_id = request.path_params["terminal_id"]
        body = await request.json()
        new_id = str(body.get("new_id", "")).strip()
        if not new_id:
            return JSONResponse({"error": "new_id cannot be empty"}, status_code=400)
        try:
            result = manager.rename(terminal_id, new_id)
            log(f"POST /api/rename '{terminal_id}' -> '{new_id}'", "WEB")
            return JSONResponse(result)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except KeyError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    async def api_resize(request: Request):
        terminal_id = request.path_params["terminal_id"]
        body = await request.json()
        rows = int(body.get("rows", 24))
        cols = int(body.get("cols", 80))
        manager.resize(terminal_id, rows, cols)
        return JSONResponse({"status": "resized", "rows": rows, "cols": cols})

    async def api_status(request):
        terminal_id = request.path_params["terminal_id"]
        try:
            return JSONResponse(manager.status(terminal_id))
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)

    async def api_profile(request):
        terminal_id = request.path_params["terminal_id"]
        try:
            return JSONResponse(manager.get_profile(terminal_id))
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)

    async def api_profile_update(request: Request):
        terminal_id = request.path_params["terminal_id"]
        body = await request.json()
        try:
            result = manager.get_profile(terminal_id)
            for key, value in (body.get("set_env") or {}).items():
                result = manager.set_env(terminal_id, key, str(value))
            for key in body.get("unset_env") or []:
                result = manager.unset_env(terminal_id, key)
            if "startup_commands" in body:
                result = manager.set_startup_commands(terminal_id, [str(cmd) for cmd in body.get("startup_commands") or []])
            if body.get("run_startup_commands"):
                manager.run_startup_commands(terminal_id, [str(cmd) for cmd in body.get("startup_commands") or []] if "startup_commands" in body else None)
                result = manager.get_profile(terminal_id)
            return JSONResponse(result)
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def api_signal(request: Request):
        terminal_id = request.path_params["terminal_id"]
        body = await request.json()
        sig = str(body.get("signal", "SIGINT"))
        try:
            manager.signal(terminal_id, sig)
            return JSONResponse({"status": "signaled"})
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def api_workspaces(request):
        log("GET /api/workspaces", "WEB")
        return JSONResponse(manager.list_workspaces())

    async def api_workspace_create(request: Request):
        body = await request.json()
        workspace_id = str(body.get("workspace_id", "")).strip()
        if not workspace_id:
            return JSONResponse({"error": "workspace_id cannot be empty"}, status_code=400)
        try:
            ws = manager.create_workspace(workspace_id, body.get("env"), body.get("startup_commands"))
            log(f"POST /api/workspaces '{workspace_id}'", "WEB")
            return JSONResponse(ws)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def api_workspace_item(request):
        workspace_id = request.path_params["workspace_id"]
        try:
            return JSONResponse(manager.workspace_status(workspace_id))
        except KeyError:
            return JSONResponse({"error": "workspace not found"}, status_code=404)

    async def api_workspace_update(request: Request):
        workspace_id = request.path_params["workspace_id"]
        body = await request.json()
        try:
            ws = manager.configure_workspace(
                workspace_id,
                body.get("set_env"),
                body.get("unset_env"),
                body.get("startup_commands"),
                bool(body.get("apply_to_members", True)),
            )
            return JSONResponse(ws)
        except KeyError:
            return JSONResponse({"error": "workspace not found"}, status_code=404)

    async def api_workspace_add_member(request: Request):
        workspace_id = request.path_params["workspace_id"]
        body = await request.json()
        terminal_id = str(body.get("terminal_id", "")).strip()
        if not terminal_id:
            return JSONResponse({"error": "terminal_id cannot be empty"}, status_code=400)
        try:
            ws = manager.add_terminal_to_workspace(workspace_id, terminal_id)
            return JSONResponse(ws)
        except KeyError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    async def api_workspace_remove_member(request: Request):
        workspace_id = request.path_params["workspace_id"]
        terminal_id = request.path_params["terminal_id"]
        try:
            ws = manager.remove_terminal_from_workspace(workspace_id, terminal_id)
            return JSONResponse(ws)
        except KeyError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    async def api_workspace_apply(request: Request):
        workspace_id = request.path_params["workspace_id"]
        body = await request.json()
        try:
            return JSONResponse(manager.apply_workspace(workspace_id, body.get("terminal_id")))
        except KeyError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    async def api_history(request):
        terminal_id = request.path_params["terminal_id"]
        since = int(request.query_params.get("since", 0))
        try:
            data = manager.get_history(terminal_id, since)
            log(f"GET /api/history/{terminal_id}?since={since} -> {len(data['events'])} events", "WEB")
            return JSONResponse(data)
        except KeyError:
            log(f"GET /api/history/{terminal_id} -> 404", "WEB")
            return JSONResponse({"events": [], "cursor": since}, status_code=404)

    async def api_search(request):
        terminal_id = request.path_params["terminal_id"]
        query = request.query_params.get("query", "").strip()
        if not query:
            return JSONResponse({"error": "missing query"}, status_code=400)
        try:
            data = manager.search(terminal_id, query)
            log(f"GET /api/search/{terminal_id}?query={query!r} -> {len(data['matches'])} matches", "WEB")
            return JSONResponse(data)
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)

    async def api_health(request):
        log("GET /api/health", "WEB")
        return JSONResponse(manager.health())

    async def api_alerts(request):
        terminal_id = request.query_params.get("terminal_id")
        scope = request.query_params.get("scope")
        return JSONResponse(manager.list_alerts(scope, terminal_id))

    async def api_alert_create(request: Request):
        body = await request.json()
        scope = str(body.get("scope", "session")).strip()
        pattern = str(body.get("pattern", "")).strip()
        label = str(body.get("label", "")).strip() or None
        terminal_id = body.get("terminal_id")
        if not pattern:
            return JSONResponse({"error": "pattern cannot be empty"}, status_code=400)
        try:
            return JSONResponse(manager.add_alert(scope, pattern, terminal_id, label))
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def api_alert_remove(request: Request):
        alert_id = request.path_params["alert_id"]
        return JSONResponse({"removed": manager.remove_alert(alert_id), "alert_id": alert_id})

    async def api_alert_events(request):
        terminal_id = request.query_params.get("terminal_id")
        since = int(request.query_params.get("since", 0))
        return JSONResponse(manager.list_alert_events(terminal_id, since))

    async def api_checkpoints(request):
        terminal_id = request.query_params.get("terminal_id")
        if request.method == "GET":
            return JSONResponse(manager.list_checkpoints(terminal_id))
        body = await request.json()
        terminal_id = str(body.get("terminal_id", "")).strip()
        label = str(body.get("label", "")).strip()
        note = str(body.get("note", "")).strip() or None
        if not terminal_id or not label:
            return JSONResponse({"error": "terminal_id and label are required"}, status_code=400)
        try:
            return JSONResponse(manager.add_checkpoint(terminal_id, label, note, body.get("cursor")))
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)

    async def api_checkpoint_remove(request: Request):
        checkpoint_id = request.path_params["checkpoint_id"]
        return JSONResponse({"removed": manager.remove_checkpoint(checkpoint_id), "checkpoint_id": checkpoint_id})

    async def api_export(request):
        terminal_id = request.path_params["terminal_id"]
        try:
            return JSONResponse(manager.export_session(terminal_id))
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)

    async def api_import(request: Request):
        body = await request.json()
        snapshot = body.get("snapshot")
        if not isinstance(snapshot, dict):
            return JSONResponse({"error": "snapshot must be an object"}, status_code=400)
        try:
            return JSONResponse(await manager.import_session(snapshot, body.get("terminal_id")))
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def api_send(request: Request):
        terminal_id = request.path_params["terminal_id"]
        body = await request.json()
        text = body.get("text", "")
        if not text:
            return JSONResponse({"error": "missing text"}, status_code=400)
        try:
            manager.send(terminal_id, text)
            log(f"POST /api/send/{terminal_id} '{text.strip()[:60]}'", "WEB")
            return JSONResponse({"status": "sent"})
        except KeyError:
            return JSONResponse({"error": "terminal not found"}, status_code=404)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def ws_terminal(websocket: WebSocket):
        terminal_id = websocket.path_params["terminal_id"]
        since = int(websocket.query_params.get("since", 0))
        await websocket.accept()
        try:
            try:
                session = manager.get(terminal_id)
            except KeyError:
                history = manager.get_history(terminal_id, since)
                await websocket.send_json({"type": "history", **history})
                await websocket.send_json({"type": "status", "status": manager.status(terminal_id)})
                await websocket.close()
                return

            queue: asyncio.Queue[dict] = asyncio.Queue()

            def listener(text: str) -> None:
                queue.put_nowait(
                    {
                        "type": "output",
                        "text": text,
                        "cursor": session.cursor,
                        "timestamp": session.updated_at.isoformat(),
                    }
                )

            session.add_output_listener(listener)
            try:
                try:
                    history = manager.get_history(terminal_id, since)
                except KeyError:
                    history = {"events": [], "cursor": since}
                await websocket.send_json({"type": "history", **history})
                await websocket.send_json({"type": "status", "status": manager.status(terminal_id)})

                recv_task = asyncio.create_task(websocket.receive_json())
                queue_task = asyncio.create_task(queue.get())

                while True:
                    done, _ = await asyncio.wait(
                        [recv_task, queue_task],
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=1.0,
                    )

                    if not done:
                        if not session.alive:
                            await websocket.send_json({"type": "status", "status": manager.status(terminal_id)})
                            break
                        continue

                    if recv_task in done:
                        try:
                            msg = recv_task.result()
                            mtype = msg.get("type") if isinstance(msg, dict) else None
                            if mtype == "input":
                                text = msg.get("text", "")
                                if text:
                                    manager.send_raw(terminal_id, text)
                            elif mtype == "resize":
                                rows = int(msg.get("rows", 24))
                                cols = int(msg.get("cols", 80))
                                manager.resize(terminal_id, rows, cols)
                        except Exception:
                            pass
                        recv_task = asyncio.create_task(websocket.receive_json())

                    if queue_task in done:
                        event = queue_task.result()
                        await websocket.send_json(event)
                        queue_task = asyncio.create_task(queue.get())

                recv_task.cancel()
                queue_task.cancel()
                await websocket.close()
            finally:
                session.remove_output_listener(listener)
        except WebSocketDisconnect:
            return
        except KeyError:
            await websocket.close(code=4404)
        except Exception as e:
            log(f"websocket error for '{terminal_id}': {e}", "WEB")
            try:
                await websocket.close(code=1011)
            except Exception:
                pass

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    return Starlette(routes=[
        Route("/", index),
        Route("/api/terminals", api_terminals),
        Route("/api/create", api_create, methods=["POST"]),
        Route("/api/health", api_health),
        Route("/api/status/{terminal_id}", api_status),
        Route("/api/profile/{terminal_id}", api_profile),
        Route("/api/profile/{terminal_id}", api_profile_update, methods=["POST"]),
        Route("/api/kill/{terminal_id}", api_kill, methods=["POST"]),
        Route("/api/terminals/{terminal_id}", api_delete, methods=["DELETE"]),
        Route("/api/rename/{terminal_id}", api_rename, methods=["POST"]),
        Route("/api/resize/{terminal_id}", api_resize, methods=["POST"]),
        Route("/api/signal/{terminal_id}", api_signal, methods=["POST"]),
        Route("/api/history/{terminal_id}", api_history),
        Route("/api/search/{terminal_id}", api_search),
        Route("/api/workspaces", api_workspaces),
        Route("/api/workspaces", api_workspace_create, methods=["POST"]),
        Route("/api/workspaces/{workspace_id}/members/{terminal_id}", api_workspace_remove_member, methods=["DELETE"]),
        Route("/api/workspaces/{workspace_id}/members", api_workspace_add_member, methods=["POST"]),
        Route("/api/workspaces/{workspace_id}/apply", api_workspace_apply, methods=["POST"]),
        Route("/api/workspaces/{workspace_id}", api_workspace_item),
        Route("/api/workspaces/{workspace_id}", api_workspace_update, methods=["POST"]),
        Route("/api/alerts", api_alerts),
        Route("/api/alerts", api_alert_create, methods=["POST"]),
        Route("/api/alerts/{alert_id}", api_alert_remove, methods=["DELETE"]),
        Route("/api/alert-events", api_alert_events),
        Route("/api/checkpoints", api_checkpoints),
        Route("/api/checkpoints", api_checkpoints, methods=["POST"]),
        Route("/api/checkpoints/{checkpoint_id}", api_checkpoint_remove, methods=["DELETE"]),
        Route("/api/export/{terminal_id}", api_export),
        Route("/api/import", api_import, methods=["POST"]),
        Route("/api/send/{terminal_id}", api_send, methods=["POST"]),
        WebSocketRoute("/ws/{terminal_id}", ws_terminal),
    ], middleware=middleware)
