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
body{background:#0d1117;color:#c9d1d9;font-family:monospace;display:flex;height:100vh}
#sidebar{width:260px;background:#161b22;border-right:1px solid #30363d;display:flex;flex-direction:column;flex-shrink:0}
#sidebar h2{padding:16px;font-size:14px;border-bottom:1px solid #30363d;color:#58a6ff}
#terminal-list{flex:1;overflow-y:auto;padding:8px}
.term-item{padding:10px 12px;cursor:pointer;border-radius:6px;font-size:12px;margin:2px 0;display:flex;align-items:center;gap:8px}
.term-item:hover{background:#1f2937}
.term-item.active{background:#1f6feb}
.status-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.status-dot.on{background:#3fb950}
.status-dot.off{background:#f85149}
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#info{padding:10px 16px;border-bottom:1px solid #30363d;font-size:12px;display:flex;gap:20px;flex-shrink:0;flex-wrap:wrap}
#info span{color:#8b949e}
#info strong{color:#c9d1d9;margin-left:4px}
#toolbar{padding:8px 12px;border-bottom:1px solid #30363d;display:flex;gap:8px;align-items:center;flex-shrink:0;background:#11151b}
#history-search{flex:1;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;font-family:monospace;font-size:12px;padding:7px 10px;border-radius:4px;outline:none}
#history-search:focus{border-color:#58a6ff}
#history-clear{background:#21262d;border:1px solid #30363d;color:#c9d1d9;font-family:monospace;font-size:12px;padding:7px 10px;border-radius:4px;cursor:pointer}
#history-clear:hover{background:#30363d}
#history-count{color:#8b949e;font-size:11px;min-width:84px;text-align:right}
#history{flex:1;overflow-y:auto;padding:8px 12px}
.entry{padding:6px 8px;margin:2px 0;border-radius:4px;font-size:12px;display:flex;gap:10px}
.entry.input{border-left:2px solid #58a6ff}
.entry.output{border-left:2px solid #30363d}
.entry .ts{color:#484f58;flex-shrink:0;font-size:11px;min-width:70px}
.entry .tag{flex-shrink:0;font-size:10px;padding:1px 5px;border-radius:3px;font-weight:bold}
.entry .tag.in{color:#58a6ff;background:rgba(88,166,255,0.1)}
.entry .tag.out{color:#8b949e;background:rgba(139,148,158,0.1)}
.entry .txt{white-space:pre-wrap;word-break:break-all;flex:1}
.entry .txt.in{color:#c9d1d9}
.entry .txt.out{color:#8b949e}
#empty{display:flex;align-items:center;justify-content:center;height:100%;color:#484f58;font-size:14px}
#input-bar{display:none;padding:6px 12px;border-top:1px solid #30363d;background:#161b22;flex-shrink:0}
#input-bar input{width:100%;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;font-family:monospace;font-size:13px;padding:8px 12px;border-radius:4px;outline:none}
#input-bar input:focus{border-color:#58a6ff}
#db-info{font-size:11px;color:#484f58;padding:4px 12px;border-top:1px solid #161b22}
</style>
</head>
<body>
<div id="sidebar">
<h2>Terminals</h2>
<div id="terminal-list"><div style="color:#484f58;padding:12px;font-size:12px">No terminals</div></div>
<div id="db-info"></div>
</div>
<div id="main">
<div id="info">
  <span>ID: <strong id="info-id">-</strong></span>
  <span>PID: <strong id="info-pid">-</strong></span>
  <span>Alive: <strong id="info-alive">-</strong></span>
  <span>CWD: <strong id="info-cwd">-</strong></span>
</div>
<div id="toolbar">
  <input id="history-search" placeholder="Filter history...">
  <button id="history-clear" type="button">Clear</button>
  <span id="history-count"></span>
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
  $('empty').style.display='none';
  $('history').innerHTML='';
  $('history-search').value='';
  $('history-count').textContent='';
  $('input-bar').style.display='block';
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
async function sendCmd(){
  const inp=$('cmd-input');
  const text=inp.value;
  if(!text||!activeId)return;
  inp.value='';
  try{
    await fetch('/api/send/'+activeId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text+'\\n'})});
  }catch(e){}
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
$('history-search').oninput=function(e){historyFilter=e.target.value.trim().toLowerCase();applyHistoryFilter()};
$('history-clear').onclick=function(){historyFilter='';$('history-search').value='';applyHistoryFilter();$('cmd-input').focus()};
$('cmd-input').onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();sendCmd()}};
setInterval(refreshList,2000);
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
        Route("/api/status/{terminal_id}", api_status),
        Route("/api/history/{terminal_id}", api_history),
        Route("/api/send/{terminal_id}", api_send, methods=["POST"]),
    ])
