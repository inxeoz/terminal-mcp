from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

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
let activeId=null,timer=null,statusTimer=null,cursor=0,historyFilter='';

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
  $('terminal-list').innerHTML=data.map(t=>`<div class="term-item${t.id===activeId?' active':''}" data-id="${t.id}" data-alive="${t.alive}">
    <span class="status-dot ${t.alive?'on':'off'}"></span>${t.id}
  </div>`).join('');
  $('terminal-list').querySelectorAll('.term-item').forEach(e=>e.onclick=()=>select(e.dataset.id));
}

async function select(id){
  activeId=id; cursor=0; historyFilter='';
  if(timer)clearInterval(timer);
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
  refreshList();
  await loadStatus();
  await loadHistory();
  timer=setInterval(loadHistory,800);
  statusTimer=setInterval(loadStatus,3000);
}
async function loadStatus(){
  if(!activeId)return;
  try{
    const r=await fetch('/api/status/'+activeId),d=await r.json();
    $('info-id').textContent=d.id||'-';
    $('info-pid').textContent=d.pid||'-';
    $('info-alive').textContent=d.alive?'yes':'no';
    $('info-cwd').textContent=d.cwd||'-';
    $('cmd-input').disabled=!d.alive;
    $('delete-terminal').disabled=!d.alive;
  }catch(e){}
}
async function loadHistory(){
  if(!activeId)return;
  try{
    const r=await fetch('/api/history/'+activeId+'?since='+cursor),d=await r.json();
    for(const e of d.events){
      const div=document.createElement('div');
      div.className='entry '+e.type;
      const txt=esc(e.text);
      div.innerHTML='<span class="ts">'+e.timestamp.slice(11,19)+'</span><span class="tag '+(e.type=='input'?'in':'out')+'">'+(e.type=='input'?'IN':'OUT')+'</span><span class="txt '+(e.type=='input'?'in':'out')+'">'+txt+'</span>';
      $('history').appendChild(div);
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
    const r=await fetch('/api/kill/'+activeId,{method:'POST'});
    const d=await r.json();
    if(!r.ok)throw new Error(d.error||'delete failed');
    activeId=null; cursor=0;
    if(timer)clearInterval(timer);
    if(statusTimer)clearInterval(statusTimer);
    $('history').innerHTML='';
    setDisplay('empty', 'flex');
    setDisplay('input-bar', 'none');
    $('cmd-input').disabled=true;
    $('delete-terminal').disabled=true;
    $('info-id').textContent='-';
    $('info-pid').textContent='-';
    $('info-alive').textContent='-';
    $('info-cwd').textContent='-';
    await refreshList();
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
    await fetch('/api/send/'+activeId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text+'\\n'})});
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
    const r=await fetch('/api/search/'+activeId+'?query='+encodeURIComponent(query));
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
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
$('history-search').oninput=function(e){historyFilter=e.target.value.trim().toLowerCase();applyHistoryFilter()};
$('history-clear').onclick=function(){historyFilter='';$('history-search').value='';applyHistoryFilter();$('cmd-input').focus()};
$('output-search-btn').onclick=searchOutput;
$('output-search').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();searchOutput()}};
$('create-session').onclick=createSession;
$('create-name').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();createSession()}};
$('delete-terminal').onclick=deleteSession;
$('theme-toggle').onclick=function(){setTheme(document.body.dataset.theme==='dark'?'light':'dark')};
$('cmd-input').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();sendCmd()}};
setInterval(refreshList,2000);
setTheme(localStorage.getItem('i4z-terminal-theme')||((window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark'));
refreshList();
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

    return Starlette(routes=[
        Route("/", index),
        Route("/api/terminals", api_terminals),
        Route("/api/create", api_create, methods=["POST"]),
        Route("/api/status/{terminal_id}", api_status),
        Route("/api/kill/{terminal_id}", api_kill, methods=["POST"]),
        Route("/api/history/{terminal_id}", api_history),
        Route("/api/search/{terminal_id}", api_search),
        Route("/api/send/{terminal_id}", api_send, methods=["POST"]),
    ])
