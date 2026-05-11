import asyncio

from starlette.applications import Starlette
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
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;
  --fg:#c9d1d9;
  --sidebar:#161b22;
  --panel:#11151b;
  --border:#30363d;
  --accent:#58a6ff;
  --accent-strong:#1f6feb;
  --muted:#8b949e;
  --muted-2:#484f58;
  --hover:#1f2937;
  --input:#0d1117;
  --button:#21262d;
  --button-hover:#30363d;
  --success:#3fb950;
  --danger:#f85149;
}
body[data-theme="light"]{
  --bg:#f6f8fa;
  --fg:#24292f;
  --sidebar:#ffffff;
  --panel:#ffffff;
  --border:#d0d7de;
  --accent:#0969da;
  --accent-strong:#0969da;
  --muted:#6e7781;
  --muted-2:#8c959f;
  --hover:#eaeef2;
  --input:#ffffff;
  --button:#f6f8fa;
  --button-hover:#eaeef2;
  --success:#1a7f37;
  --danger:#cf222e;
}
body{background:var(--bg);color:var(--fg);font-family:monospace;display:flex;height:100vh}
#sidebar{width:260px;background:var(--sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
#sidebar h2{padding:16px;font-size:14px;border-bottom:1px solid var(--border);color:var(--accent)}
#create-bar{padding:10px 12px;border-bottom:1px solid var(--border);display:flex;gap:8px;flex-shrink:0}
#create-name{flex:1;background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:12px;padding:7px 10px;border-radius:4px;outline:none}
#create-name:focus{border-color:var(--accent)}
#create-session{background:var(--button);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:12px;padding:7px 10px;border-radius:4px;cursor:pointer}
#create-session:hover{background:var(--button-hover)}
#terminal-list{flex:1;overflow-y:auto;padding:8px}
.term-item{padding:10px 12px;cursor:pointer;border-radius:6px;font-size:12px;margin:2px 0;display:flex;align-items:center;gap:8px}
.term-item:hover{background:var(--hover)}
.term-item.active{background:var(--accent-strong)}
.status-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.status-dot.on{background:var(--success)}
.status-dot.off{background:var(--danger)}
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#info{padding:10px 16px;border-bottom:1px solid var(--border);font-size:12px;display:flex;gap:20px;flex-shrink:0;flex-wrap:wrap;align-items:center}
#info span{color:var(--muted)}
#info strong{color:var(--fg);margin-left:4px}
#actions{margin-left:auto;display:flex;gap:8px;align-items:center}
#theme-toggle,#delete-terminal{background:var(--button);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:12px;padding:7px 10px;border-radius:4px;cursor:pointer}
#theme-toggle:hover,#delete-terminal:hover{background:var(--button-hover)}
#theme-toggle:disabled,#delete-terminal:disabled{opacity:.5;cursor:not-allowed}
#toolbar{padding:8px 12px;border-bottom:1px solid var(--border);display:flex;gap:8px;align-items:center;flex-shrink:0;background:var(--panel);flex-wrap:wrap}
#history-search,#output-search{flex:1;min-width:180px;background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:12px;padding:7px 10px;border-radius:4px;outline:none}
#history-search:focus,#output-search:focus{border-color:var(--accent)}
#history-clear,#output-search-btn{background:var(--button);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:12px;padding:7px 10px;border-radius:4px;cursor:pointer}
#history-clear:hover,#output-search-btn:hover{background:var(--button-hover)}
#history-count{color:var(--muted);font-size:11px;min-width:84px;text-align:right}
#search-results{border-bottom:1px solid var(--border);padding:8px 12px;display:none;flex-shrink:0;max-height:180px;overflow-y:auto;background:var(--bg)}
#search-results-head{display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:12px;color:var(--muted);margin-bottom:6px}
#search-results-body{display:flex;flex-direction:column;gap:6px}
.search-match{padding:6px 8px;border:1px solid var(--border);border-radius:4px;background:var(--panel);white-space:pre-wrap;word-break:break-word;font-size:12px;color:var(--fg)}
.search-empty{color:var(--muted-2);font-size:12px}
#history{flex:1;overflow-y:auto;padding:8px 12px}
.entry{padding:6px 8px;margin:2px 0;border-radius:4px;font-size:12px;display:flex;gap:10px}
.entry.input{border-left:2px solid var(--accent)}
.entry.output{border-left:2px solid var(--border)}
.entry .ts{color:var(--muted-2);flex-shrink:0;font-size:11px;min-width:70px}
.entry .tag{flex-shrink:0;font-size:10px;padding:1px 5px;border-radius:3px;font-weight:bold}
.entry .tag.in{color:var(--accent);background:rgba(88,166,255,0.1)}
.entry .tag.out{color:var(--muted);background:rgba(139,148,158,0.1)}
.entry .txt{white-space:pre-wrap;word-break:break-all;flex:1}
.entry .txt.in{color:var(--fg)}
.entry .txt.out{color:var(--muted)}
#empty{display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted-2);font-size:14px}
#input-bar{display:none;padding:6px 12px;border-top:1px solid var(--border);background:var(--sidebar);flex-shrink:0}
#input-bar input{width:100%;background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:13px;padding:8px 12px;border-radius:4px;outline:none}
#input-bar input:focus{border-color:var(--accent)}
#db-info{font-size:11px;color:var(--muted-2);padding:4px 12px;border-top:1px solid var(--border)}
#health{padding:8px 16px;border-bottom:1px solid var(--border);font-size:12px;color:var(--muted);background:var(--panel)}
#feature-panels{border-bottom:1px solid var(--border);background:var(--bg);flex-shrink:0}
#feature-panels>summary{cursor:pointer;padding:8px 12px;color:var(--accent);font-size:12px}
#feature-panels .panel-grid{padding:0 12px 8px;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px;max-height:260px;overflow:auto}
.card{border:1px solid var(--border);border-radius:6px;background:var(--panel);padding:8px;display:flex;flex-direction:column;gap:6px}
.card h3{font-size:12px;color:var(--accent)}
.row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.card input,.card textarea,.card select{background:var(--input);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:11px;padding:6px 8px;border-radius:4px;outline:none}
.card input:focus,.card textarea:focus,.card select:focus{border-color:var(--accent)}
.card textarea{min-height:52px;resize:vertical}
.card button{background:var(--button);border:1px solid var(--border);color:var(--fg);font-family:monospace;font-size:11px;padding:6px 8px;border-radius:4px;cursor:pointer}
.card button:hover{background:var(--button-hover)}
.card button:disabled{opacity:.5;cursor:not-allowed}
.card pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:6px;font-size:11px;max-height:120px;overflow:auto}
.list{display:flex;flex-direction:column;gap:4px;max-height:120px;overflow:auto}
.list-item{display:flex;justify-content:space-between;gap:6px;align-items:center;border:1px solid var(--border);border-radius:4px;padding:4px 6px;font-size:11px}
.list-item button{padding:3px 6px;font-size:10px}
.muted{color:var(--muted-2);font-size:11px}
</style>
</head>
<body>
<div id="sidebar">
<h2>Terminals</h2>
<div id="create-bar">
  <input id="create-name" placeholder="New session name" minlength="1">
  <button id="create-session" type="button">Create</button>
</div>
<div id="terminal-list"><div style="color:#484f58;padding:12px;font-size:12px">No terminals</div></div>
<div id="db-info"></div>
</div>
<div id="main">
<div id="info">
  <span>ID: <strong id="info-id">-</strong></span>
  <span>PID: <strong id="info-pid">-</strong></span>
  <span>Alive: <strong id="info-alive">-</strong></span>
  <span>CWD: <strong id="info-cwd">-</strong></span>
  <div id="actions">
    <button id="delete-terminal" type="button" disabled>Delete</button>
    <button id="theme-toggle" type="button">Theme: dark</button>
  </div>
</div>
<div id="health">Health: loading...</div>
<details id="feature-panels">
  <summary>Management panels</summary>
  <div class="panel-grid">
  <div class="card">
    <h3>Session profile</h3>
    <div class="row">
      <input id="profile-key" placeholder="ENV_KEY" style="flex:1;min-width:100px">
      <input id="profile-value" placeholder="value" style="flex:1;min-width:100px">
      <button id="profile-set-btn" type="button">Set env</button>
      <button id="profile-unset-btn" type="button">Unset env</button>
    </div>
    <textarea id="profile-startup" placeholder="startup commands, one per line"></textarea>
    <div class="row">
      <label style="font-size:11px;color:var(--muted)"><input id="profile-run-startup" type="checkbox"> run now</label>
      <button id="profile-save-btn" type="button">Save startup</button>
    </div>
    <pre id="profile-view">Select a terminal</pre>
  </div>
  <div class="card">
    <h3>Workspace profiles</h3>
    <div class="row">
      <input id="workspace-id" placeholder="workspace id" style="flex:1;min-width:110px">
      <button id="workspace-create-btn" type="button">Create</button>
      <button id="workspace-refresh-btn" type="button">Refresh</button>
    </div>
    <textarea id="workspace-env-json" placeholder='env JSON, e.g. {"NODE_ENV":"dev"}'></textarea>
    <textarea id="workspace-startup" placeholder="workspace startup commands, one per line"></textarea>
    <div class="row">
      <select id="workspace-list" style="flex:1;min-width:130px"></select>
      <button id="workspace-apply-btn" type="button">Save &amp; Apply</button>
      <button id="workspace-add-member-btn" type="button">Add member</button>
      <button id="workspace-remove-member-btn" type="button">Remove member</button>
    </div>
    <pre id="workspace-view">No workspace selected</pre>
  </div>
  <div class="card">
    <h3>Output alerts</h3>
    <div class="row">
      <select id="alert-scope"><option value="session">session</option><option value="global">global</option></select>
      <input id="alert-pattern" placeholder="pattern" style="flex:1;min-width:110px">
      <input id="alert-label" placeholder="label" style="flex:1;min-width:90px">
      <button id="alert-add-btn" type="button">Add</button>
      <button id="alert-refresh-btn" type="button">Refresh</button>
    </div>
    <div id="alert-list" class="list"></div>
  </div>
  <div class="card">
    <h3>Checkpoints</h3>
    <div class="row">
      <input id="checkpoint-label" placeholder="label" style="flex:1;min-width:90px">
      <input id="checkpoint-note" placeholder="note" style="flex:1;min-width:90px">
      <button id="checkpoint-add-btn" type="button">Add</button>
      <button id="checkpoint-refresh-btn" type="button">Refresh</button>
    </div>
    <div id="checkpoint-list" class="list"></div>
  </div>
  <div class="card">
    <h3>Snapshots</h3>
    <div class="row">
      <button id="snapshot-export-btn" type="button">Export selected</button>
      <button id="snapshot-import-btn" type="button">Import JSON</button>
    </div>
    <textarea id="snapshot-json" placeholder="Exported JSON appears here or paste a snapshot to import"></textarea>
    <pre id="snapshot-status">No snapshot loaded</pre>
  </div>
  </div>
</details>
<div id="toolbar">
  <input id="history-search" placeholder="Filter history...">
  <button id="history-clear" type="button">Clear</button>
  <input id="output-search" placeholder="Search output...">
  <button id="output-search-btn" type="button">Search</button>
  <span id="history-count"></span>
</div>
<div id="search-results">
  <div id="search-results-head">
    <span>Output search</span>
    <span id="search-results-count"></span>
  </div>
  <div id="search-results-body"></div>
</div>
<div id="history">
<div id="empty">Select a terminal from the sidebar</div>
</div>
<div id="input-bar">
<input id="cmd-input" placeholder="Type command and press Enter..." autofocus>
</div>
</div>
<script>
const $=id=>document.getElementById(id);
let activeId=null,statusTimer=null,cursor=0,historyFilter='',streamSocket=null,streamReconnectTimer=null;

function setTheme(next){
  const theme=next==='light'?'light':'dark';
  document.body.dataset.theme=theme;
  localStorage.setItem('i4z-terminal-theme', theme);
  const toggle=$('theme-toggle');
  if(toggle) toggle.textContent='Theme: '+theme;
}

function setDisplay(id, value){
  const el=$(id);
  if(el) el.style.display=value;
}

function setText(id, value){
  const el=$(id);
  if(el) el.textContent=value;
}

async function fetchJson(url, options){
  const r=await fetch(url, options);
  const data=await r.json();
  if(!r.ok) throw new Error(data.error||'request failed');
  return data;
}

function currentTerminal(){
  return activeId;
}

function currentWorkspace(){
  return $('workspace-list').value || '';
}

function terminalPath(id){
  return encodeURIComponent(id);
}

function workspacePath(id){
  return encodeURIComponent(id);
}

function clearStream(){
  if(streamReconnectTimer){
    clearTimeout(streamReconnectTimer);
    streamReconnectTimer=null;
  }
  if(streamSocket){
    const socket=streamSocket;
    streamSocket=null;
    socket.__terminalId=null;
    socket.__shouldReconnect=false;
    try{socket.close()}catch(e){}
  }
}

function appendEvent(type, text, timestamp){
  const div=document.createElement('div');
  div.className='entry '+type;
  const txt=esc(text);
  const ts=(timestamp||new Date().toISOString()).slice(11,19);
  div.innerHTML='<span class="ts">'+ts+'</span><span class="tag '+(type=='input'?'in':'out')+'">'+(type=='input'?'IN':'OUT')+'</span><span class="txt '+(type=='input'?'in':'out')+'">'+txt+'</span>';
  $('history').appendChild(div);
}

function appendStreamOutput(text, timestamp){
  appendEvent('output', text, timestamp);
  applyHistoryFilter();
  $('history').scrollTop=$('history').scrollHeight;
}

function connectStream(){
  clearStream();
  if(!activeId) return;
  const proto=location.protocol==='https:'?'wss:':'ws:';
  const url=`${proto}//${location.host}/ws/${terminalPath(activeId)}?since=${cursor}`;
  const socket=new WebSocket(url);
  socket.__terminalId=activeId;
  socket.__shouldReconnect=true;
  streamSocket=socket;
  socket.onmessage=function(ev){
    let msg;
    try{
      msg=JSON.parse(ev.data);
    }catch(e){
      return;
    }
    if(msg.type==='output'){
      appendStreamOutput(msg.text||'', msg.timestamp);
      if(typeof msg.cursor==='number') cursor=msg.cursor;
      return;
    }
    if(msg.type==='history'){
      const events=msg.events||[];
      for(const e of events){
        appendEvent(e.type, e.text, e.timestamp);
      }
      applyHistoryFilter();
      if(typeof msg.cursor==='number') cursor=msg.cursor;
      $('history').scrollTop=$('history').scrollHeight;
      return;
    }
    if(msg.type==='status'){
      if(msg.status){
        $('info-id').textContent=msg.status.id||'-';
        $('info-pid').textContent=msg.status.pid||'-';
        $('info-alive').textContent=msg.status.alive?'yes':'no';
        $('info-cwd').textContent=msg.status.cwd||'-';
        $('cmd-input').disabled=!msg.status.alive;
        $('delete-terminal').disabled=!msg.status.alive;
        if(!msg.status.alive) socket.__shouldReconnect=false;
      }
    }
  };
  socket.onclose=function(){
    if(socket.__shouldReconnect && activeId===socket.__terminalId){
      streamSocket=null;
      streamReconnectTimer=setTimeout(()=>{if(activeId===socket.__terminalId) connectStream()},1000);
    }
  };
  socket.onerror=function(){};
}

function applyHistoryFilter(){
  const entries=$('history').querySelectorAll('.entry');
  let visible=0;
  for(const entry of entries){
    const match=!historyFilter || entry.textContent.toLowerCase().includes(historyFilter);
    entry.style.display=match?'flex':'none';
    if(match) visible++;
  }
  $('history-count').textContent=historyFilter?`${visible}/${entries.length}`:(entries.length?`${entries.length} total`:'');
}

async function refreshList(){
  const r=await fetch('/api/terminals'),data=await r.json();
  $('db-info').textContent=data.length?data.length+' terminal(s)':'';
  if(!data.length){$('terminal-list').innerHTML='<div style="color:#484f58;padding:12px;font-size:12px">No terminals</div>';return}
  $('terminal-list').innerHTML=data.map(t=>`<div class="term-item${t.id===activeId?' active':''}" data-id="${esc(t.id)}" data-alive="${t.alive}">
    <span class="status-dot ${t.alive?'on':'off'}"></span>${esc(t.id)}
  </div>`).join('');
  $('terminal-list').querySelectorAll('.term-item').forEach(e=>e.onclick=()=>select(e.dataset.id));
}

async function select(id){
  activeId=id; cursor=0; historyFilter='';
  if(statusTimer)clearInterval(statusTimer);
  setDisplay('empty', 'none');
  $('history').innerHTML='';
  $('history-search').value='';
  $('history-count').textContent='';
  $('output-search').value='';
  setDisplay('search-results', 'none');
  setText('search-results-body', '');
  setText('search-results-count', '');
  setDisplay('input-bar', 'block');
  $('cmd-input').focus();
  clearStream();
  refreshList();
  await loadStatus();
  await loadProfile();
  await loadAlerts();
  await loadCheckpoints();
  await loadWorkspaces();
  await loadHistory();
  connectStream();
  statusTimer=setInterval(loadStatus,3000);
}
async function loadStatus(){
  if(!activeId)return;
  try{
    const r=await fetch('/api/status/'+terminalPath(activeId)),d=await r.json();
    $('info-id').textContent=d.id||'-';
    $('info-pid').textContent=d.pid||'-';
    $('info-alive').textContent=d.alive?'yes':'no';
    $('info-cwd').textContent=d.cwd||'-';
    $('cmd-input').disabled=!d.alive;
    $('delete-terminal').disabled=!d.alive;
  }catch(e){}
}
async function loadHealth(){
  try{
    const d=await fetchJson('/api/health');
    const counts=d.counts||{};
    const sessions=d.sessions||{};
    const errors=d.reader_errors||[];
    $('health').textContent=`Health: db ${d.db&&d.db.ok?'ok':'bad'} | sessions ${sessions.active||0} active, ${sessions.stale?sessions.stale.length:0} stale | alerts ${counts.alerts||0}, alert hits ${counts.alert_events||0} | workspaces ${counts.workspaces||0} | reader errors ${errors.length}`;
  }catch(e){
    $('health').textContent='Health: unavailable';
  }
}
async function loadProfile(){
  if(!activeId){
    $('profile-view').textContent='Select a terminal';
    $('profile-startup').value='';
    return;
  }
  try{
    const d=await fetchJson('/api/profile/'+terminalPath(activeId));
    $('profile-view').textContent=JSON.stringify(d,null,2);
    $('profile-startup').value=(d.startup_commands||[]).join('\\n');
  }catch(e){
    $('profile-view').textContent=e.message||'profile unavailable';
  }
}
async function loadWorkspaces(){
  try{
    const items=await fetchJson('/api/workspaces');
    $('workspace-list').innerHTML=items.map(ws=>`<option value="${esc(ws.id)}">${esc(ws.id)} (${ws.member_count||0})</option>`).join('');
    if(items.length && !$('workspace-list').value) $('workspace-list').value=items[0].id;
    if(currentWorkspace()) await loadWorkspaceStatus();
    else $('workspace-view').textContent='No workspace selected';
  }catch(e){
    $('workspace-list').innerHTML='';
    $('workspace-view').textContent=e.message||'workspaces unavailable';
  }
}
async function loadWorkspaceStatus(){
  const id=currentWorkspace();
  if(!id){
    $('workspace-view').textContent='No workspace selected';
    return;
  }
  try{
    const d=await fetchJson('/api/workspaces/'+workspacePath(id));
    $('workspace-view').textContent=JSON.stringify(d,null,2);
    $('workspace-env-json').value=JSON.stringify(d.env||{},null,2);
    $('workspace-startup').value=(d.startup_commands||[]).join('\\n');
  }catch(e){
    $('workspace-view').textContent=e.message||'workspace unavailable';
  }
}
async function loadAlerts(){
  try{
    const terminal_id=currentTerminal();
    const qs=terminal_id?`?terminal_id=${encodeURIComponent(terminal_id)}`:'';
    const items=await fetchJson('/api/alerts'+qs);
    $('alert-list').innerHTML=items.length?items.map(a=>`<div class="list-item" data-id="${esc(a.id)}"><span>${esc(a.scope)} ${esc(a.pattern)}${a.terminal_id?` @ ${esc(a.terminal_id)}`:''}</span><button type="button" data-remove="${esc(a.id)}">Remove</button></div>`).join(''):'<div class="muted">No alerts</div>';
    $('alert-list').querySelectorAll('button[data-remove]').forEach(btn=>btn.onclick=()=>removeAlert(btn.dataset.remove));
  }catch(e){
    $('alert-list').innerHTML=`<div class="muted">${esc(e.message||'alerts unavailable')}</div>`;
  }
}
async function loadCheckpoints(){
  try{
    const terminal_id=currentTerminal();
    const qs=terminal_id?`?terminal_id=${encodeURIComponent(terminal_id)}`:'';
    const items=await fetchJson('/api/checkpoints'+qs);
    $('checkpoint-list').innerHTML=items.length?items.map(c=>`<div class="list-item" data-id="${esc(c.id)}"><span>${esc(c.label)}${c.note?` — ${esc(c.note)}`:''}</span><button type="button" data-remove="${esc(c.id)}">Remove</button></div>`).join(''):'<div class="muted">No checkpoints</div>';
    $('checkpoint-list').querySelectorAll('button[data-remove]').forEach(btn=>btn.onclick=()=>removeCheckpoint(btn.dataset.remove));
  }catch(e){
    $('checkpoint-list').innerHTML=`<div class="muted">${esc(e.message||'checkpoints unavailable')}</div>`;
  }
}
async function exportSnapshot(){
  if(!activeId) return alert('Select a terminal first');
  try{
    const d=await fetchJson('/api/export/'+terminalPath(activeId));
    $('snapshot-json').value=JSON.stringify(d,null,2);
    $('snapshot-status').textContent=`Exported ${activeId}`;
  }catch(e){
    alert(e.message||'export failed');
  }
}
async function importSnapshot(){
  const raw=$('snapshot-json').value.trim();
  if(!raw) return alert('Paste a snapshot JSON first');
  try{
    const snapshot=JSON.parse(raw);
    const d=await fetchJson('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({snapshot})});
    $('snapshot-status').textContent=`Imported ${d.terminal_id}`;
    await refreshList();
  }catch(e){
    alert(e.message||'import failed');
  }
}
async function createWorkspace(){
  const workspace_id=$('workspace-id').value.trim();
  if(!workspace_id) return;
  try{
    let env={};
    const rawEnv=$('workspace-env-json').value.trim();
    if(rawEnv) env=JSON.parse(rawEnv);
    const startup_commands=$('workspace-startup').value.split('\\n').map(s=>s.trim()).filter(Boolean);
    await fetchJson('/api/workspaces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace_id,env,startup_commands})});
    $('workspace-view').textContent='workspace created';
    await loadWorkspaces();
  }catch(e){
    alert(e.message||'workspace create failed');
  }
}
async function configureWorkspace(){
  const workspace_id=currentWorkspace();
  if(!workspace_id) return;
  try{
    let set_env={};
    const rawEnv=$('workspace-env-json').value.trim();
    if(rawEnv) set_env=JSON.parse(rawEnv);
    const startup_commands=$('workspace-startup').value.split('\\n').map(s=>s.trim()).filter(Boolean);
    await fetchJson('/api/workspaces/'+workspacePath(workspace_id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({set_env,startup_commands,apply_to_members:true})});
    await loadWorkspaceStatus();
    await loadProfile();
  }catch(e){
    alert(e.message||'workspace update failed');
  }
}
async function addTerminalToWorkspace(){
  const workspace_id=currentWorkspace();
  if(!workspace_id||!activeId) return;
  try{
    await fetchJson('/api/workspaces/'+workspacePath(workspace_id)+'/members',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({terminal_id:activeId})});
    await loadWorkspaceStatus();
  }catch(e){
    alert(e.message||'add member failed');
  }
}
async function removeTerminalFromWorkspace(){
  const workspace_id=currentWorkspace();
  if(!workspace_id||!activeId) return;
  try{
    await fetchJson('/api/workspaces/'+workspacePath(workspace_id)+'/members/'+terminalPath(activeId),{method:'DELETE'});
    await loadWorkspaceStatus();
  }catch(e){
    alert(e.message||'remove member failed');
  }
}
async function applyWorkspace(){
  const workspace_id=currentWorkspace();
  if(!workspace_id) return;
  try{
    await fetchJson('/api/workspaces/'+workspacePath(workspace_id)+'/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({terminal_id:activeId||null})});
    await loadWorkspaceStatus();
    await loadProfile();
  }catch(e){
    alert(e.message||'apply workspace failed');
  }
}
async function saveProfileEnv(set){
  if(!activeId) return alert('Select a terminal first');
  const key=$('profile-key').value.trim();
  const value=$('profile-value').value;
  try{
    await fetchJson('/api/profile/'+terminalPath(activeId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(set?{set_env:{[key]:value}}:{unset_env:[key]})});
    await loadProfile();
  }catch(e){
    alert(e.message||'profile update failed');
  }
}
async function saveStartup(){
  if(!activeId) return alert('Select a terminal first');
  const startup_commands=$('profile-startup').value.split('\\n').map(s=>s.trim()).filter(Boolean);
  const run_startup_commands=$('profile-run-startup').checked;
  try{
    await fetchJson('/api/profile/'+terminalPath(activeId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({startup_commands,run_startup_commands})});
    await loadProfile();
    await loadHistory();
  }catch(e){
    alert(e.message||'startup save failed');
  }
}
async function addAlert(){
  const scope=$('alert-scope').value;
  const pattern=$('alert-pattern').value.trim();
  const label=$('alert-label').value.trim();
  if(!pattern) return;
  try{
    await fetchJson('/api/alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,pattern,label,terminal_id:scope==='session'?activeId:null})});
    await loadAlerts();
  }catch(e){
    alert(e.message||'alert create failed');
  }
}
async function removeAlert(id){
  try{
    await fetchJson('/api/alerts/'+encodeURIComponent(id),{method:'DELETE'});
    await loadAlerts();
  }catch(e){
    alert(e.message||'alert remove failed');
  }
}
async function addCheckpoint(){
  if(!activeId) return alert('Select a terminal first');
  const label=$('checkpoint-label').value.trim();
  const note=$('checkpoint-note').value.trim();
  if(!label) return;
  try{
    await fetchJson('/api/checkpoints',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({terminal_id:activeId,label,note})});
    await loadCheckpoints();
  }catch(e){
    alert(e.message||'checkpoint add failed');
  }
}
async function removeCheckpoint(id){
  try{
    await fetchJson('/api/checkpoints/'+encodeURIComponent(id),{method:'DELETE'});
    await loadCheckpoints();
  }catch(e){
    alert(e.message||'checkpoint remove failed');
  }
}
async function loadHistory(){
  if(!activeId)return;
  try{
    const r=await fetch('/api/history/'+terminalPath(activeId)+'?since='+cursor),d=await r.json();
    for(const e of d.events){
      appendEvent(e.type, e.text, e.timestamp);
    }
    applyHistoryFilter();
    if(d.events.length){cursor=d.cursor;$('history').scrollTop=$('history').scrollHeight}
  }catch(e){}
}
async function createSession(){
  const inp=$('create-name');
  const name=inp.value.trim();
  if(!name)return;
  try{
    const r=await fetch('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'create failed');
    inp.value='';
    await refreshList();
    await select(d.terminal_id);
  }catch(e){
    alert(e.message||'create failed');
  }
}
async function deleteSession(){
  if(!activeId)return;
  if(!confirm('Delete terminal '+activeId+'?'))return;
  try{
    const r=await fetch('/api/kill/'+terminalPath(activeId),{method:'POST'});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'delete failed');
    activeId=null; cursor=0;
    if(statusTimer)clearInterval(statusTimer);
    clearStream();
    $('history').innerHTML='';
    setDisplay('empty', 'flex');
    setDisplay('input-bar', 'none');
    $('cmd-input').disabled=true;
    $('delete-terminal').disabled=true;
    $('info-id').textContent='-';
    $('info-pid').textContent='-';
    $('info-alive').textContent='-';
    $('info-cwd').textContent='-';
    $('profile-view').textContent='Select a terminal';
    $('profile-startup').value='';
    $('workspace-view').textContent='No workspace selected';
    $('alert-list').innerHTML='';
    $('checkpoint-list').innerHTML='';
    await refreshList();
    await loadHealth();
  }catch(e){
    alert(e.message||'delete failed');
  }
}
async function sendCmd(){
  const inp=$('cmd-input');
  const text=inp.value;
  if(!text||!activeId)return;
  inp.value='';
  try{
    await fetch('/api/send/'+terminalPath(activeId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text+'\\n'})});
  }catch(e){}
}
async function searchOutput(){
  const query=$('output-search').value.trim();
  if(!activeId||!query){
    setDisplay('search-results', 'none');
    setText('search-results-body', '');
    setText('search-results-count', '');
    return;
  }
  try{
    const r=await fetch('/api/search/'+terminalPath(activeId)+'?query='+encodeURIComponent(query));
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'search failed');
    const matches=d.matches||[];
    setDisplay('search-results', 'block');
    setText('search-results-count', matches.length?`${matches.length} match${matches.length===1?'':'es'}`:'0 matches');
    $('search-results-body').innerHTML=matches.length?matches.map(m=>`<div class="search-match">${esc(m)}</div>`).join(''):'<div class="search-empty">No matches</div>';
  }catch(e){
    alert(e.message||'search failed');
  }
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
$('history-search').oninput=function(e){historyFilter=e.target.value.trim().toLowerCase();applyHistoryFilter()};
$('history-clear').onclick=function(){historyFilter='';$('history-search').value='';applyHistoryFilter();$('cmd-input').focus()};
$('output-search-btn').onclick=searchOutput;
$('output-search').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();searchOutput()}};
$('create-session').onclick=createSession;
$('create-name').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();createSession()}};
$('delete-terminal').onclick=deleteSession;
$('theme-toggle').onclick=function(){setTheme(document.body.dataset.theme==='dark'?'light':'dark')};
$('cmd-input').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();sendCmd()}};
$('workspace-refresh-btn').onclick=loadWorkspaces;
$('workspace-list').onchange=loadWorkspaceStatus;
$('workspace-create-btn').onclick=createWorkspace;
$('workspace-apply-btn').onclick=configureWorkspace;
$('workspace-add-member-btn').onclick=addTerminalToWorkspace;
$('workspace-remove-member-btn').onclick=removeTerminalFromWorkspace;
$('profile-set-btn').onclick=function(){saveProfileEnv(true)};
$('profile-unset-btn').onclick=function(){saveProfileEnv(false)};
$('profile-save-btn').onclick=saveStartup;
$('alert-add-btn').onclick=addAlert;
$('alert-refresh-btn').onclick=loadAlerts;
$('checkpoint-add-btn').onclick=addCheckpoint;
$('checkpoint-refresh-btn').onclick=loadCheckpoints;
$('snapshot-export-btn').onclick=exportSnapshot;
$('snapshot-import-btn').onclick=importSnapshot;
setInterval(refreshList,2000);
setInterval(loadHealth,4000);
setTheme(localStorage.getItem('i4z-terminal-theme')||((window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark'));
refreshList();
loadHealth();
loadWorkspaces();
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
        try:
            session = await manager.create(name)
            log(f"POST /api/create '{session.id}'", "WEB")
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
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        if not session.alive:
                            await websocket.send_json({"type": "status", "status": manager.status(terminal_id)})
                            break
                        continue
                    await websocket.send_json(event)
                await websocket.close()
            finally:
                session.remove_output_listener(listener)
        except WebSocketDisconnect:
            return
        except KeyError:
            await websocket.close(code=4404)
        except Exception as e:
            log(f"websocket error for '{terminal_id}': {e}", "WEB")
            await websocket.close(code=1011)

    return Starlette(routes=[
        Route("/", index),
        Route("/api/terminals", api_terminals),
        Route("/api/create", api_create, methods=["POST"]),
        Route("/api/status/{terminal_id}", api_status),
        Route("/api/profile/{terminal_id}", api_profile),
        Route("/api/profile/{terminal_id}", api_profile_update, methods=["POST"]),
        Route("/api/kill/{terminal_id}", api_kill, methods=["POST"]),
        Route("/api/history/{terminal_id}", api_history),
        Route("/api/search/{terminal_id}", api_search),
        Route("/api/health", api_health),
        Route("/api/workspaces", api_workspaces),
        Route("/api/workspaces", api_workspace_create, methods=["POST"]),
        Route("/api/workspaces/{workspace_id}", api_workspace_item),
        Route("/api/workspaces/{workspace_id}", api_workspace_update, methods=["POST"]),
        Route("/api/workspaces/{workspace_id}/members", api_workspace_add_member, methods=["POST"]),
        Route("/api/workspaces/{workspace_id}/members/{terminal_id}", api_workspace_remove_member, methods=["DELETE"]),
        Route("/api/workspaces/{workspace_id}/apply", api_workspace_apply, methods=["POST"]),
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
    ])
