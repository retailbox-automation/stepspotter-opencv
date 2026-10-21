"""Agent mode page: the Guide agent decides the tool calls; the page shows each one.

Same look as form A (web/chat_page.py): the same colour tokens, the same three meanings
(green = do this, red = leave alone / refused, orange = stop). What is new is that every
answer carries the agent's own tool calls — and under each photo tool, what OpenCV
decided and the pictures of why; under a refused call, the gate's words. The page holds
no state: ``?agent=<session>`` restores the whole conversation from the server.
"""

AGENT_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>StepSpotter agent</title>
<style>
  :root{--bg:#eef0f4;--panel:#fff;--ink:#15181e;--dim:#5d6572;--line:#dfe3ea;--act:#12804a;--actbg:#e8f6ee;
        --avoid:#c62a30;--avoidbg:#fdecec;--stop:#b45309;--stopbg:#fdf3e3;--accent:#1f5fd6;--mine:#dbe7fb;
        --gatebg:#f1f3f7;--field:#fff}
  @media (prefers-color-scheme: dark){:root{--bg:#0f1217;--panel:#171b22;--ink:#eef1f6;--dim:#a3adbb;--line:#2a313b;
        --act:#4ecf8f;--actbg:#14301f;--avoid:#ff8e90;--avoidbg:#38191b;--stop:#f0b45f;--stopbg:#35240f;
        --accent:#7aa8ff;--mine:#1c2a44;--gatebg:#1b2029;--field:#11151b}}
  *{box-sizing:border-box} html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .app{display:flex;flex-direction:column;height:100dvh;max-width:560px;margin:0 auto}
  header{background:var(--panel);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;gap:12px;align-items:center}
  header b{flex:1} header a{color:var(--dim);font-size:13px}
  .feed{flex:1 1 auto;overflow-y:auto;padding:16px 12px}
  .msg{margin:0 0 14px;max-width:94%} .you{margin-left:auto}
  .bubble{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px 14px}
  .you .bubble{background:var(--mine)} .who{font-size:12px;color:var(--dim);margin:0 0 4px}
  .tool{border:1px solid var(--line);border-left:3px solid var(--dim);border-radius:10px;background:var(--gatebg);
        padding:8px 12px;margin:6px 0;font-size:14px}
  .tool code{font-size:13px} .tool .res{color:var(--dim);margin-top:4px;white-space:pre-wrap}
  .tool.refused{border-left-color:var(--avoid)} .tool.refused b.g{color:var(--avoid)}
  .cv{margin-top:6px;padding:6px 8px;border-radius:8px;background:var(--panel);border:1px solid var(--line)}
  .cv.block{border-left:3px solid var(--avoid)} .cv.route2{border-left:3px solid var(--accent)} .cv.ok{border-left:3px solid var(--act)}
  .cv .do{font-weight:600;color:var(--ink);margin-top:2px}
  .shots{display:flex;gap:6px;overflow-x:auto;margin-top:6px} .shots img{height:72px;border-radius:6px;border:1px solid var(--line)}
  .composer{background:var(--panel);border-top:1px solid var(--line);padding:10px 16px calc(10px + env(safe-area-inset-bottom))}
  textarea{width:100%;min-height:64px;border:1px solid var(--line);border-radius:12px;padding:10px;font:inherit;background:var(--field);color:var(--ink)}
  .row{display:flex;gap:8px;margin-top:8px;align-items:center}
  .row label{flex:1;border:1px dashed var(--line);border-radius:12px;padding:10px;color:var(--dim);font-size:15px}
  .row label.has{border-style:solid;border-color:var(--act);color:var(--ink);background:var(--actbg)}
  button{border:0;border-radius:12px;padding:12px 18px;background:var(--accent);color:#fff;font:inherit;font-weight:700}
  button:disabled{opacity:.5} .hint{color:var(--dim);font-size:13px;margin-top:6px} .err{color:var(--avoid);font-size:14px}
  .hide{display:none}
</style>
</head>
<body><div class="app">
<header><b>StepSpotter — agent mode</b><a href="/">the guided page</a></header>
<div class="feed" id="feed"></div>
<div class="composer">
  <textarea id="text" placeholder="What do you want to do? (first message: with a photo of the thing)"></textarea>
  <div class="row"><label id="shotLabel" for="photo">Attach a photo</label>
    <input id="photo" type="file" accept="image/*" capture="environment" class="hide">
    <button id="send">Send</button></div>
  <p class="hint">The agent chooses which tools to call. Under every photo it checks you see what OpenCV
     decided first, and the gate (code, not the model) refuses any move a photo has not earned.</p>
  <p class="err hide" id="err"></p>
</div></div>
<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => (s==null?"":String(s)).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let SID = new URLSearchParams(location.search).get("agent");
const ROUTE = {opencv_block:"refused by OpenCV — no model call", llm_single:"then the model checked this one photo",
               llm_two_image:"then the model compared it with your first photo"};
function fail(m){ $("err").textContent = m; $("err").classList.remove("hide"); }
async function api(url, opts){ const r = await fetch(url, opts||{}); let b=null; try{ b = await r.json(); }catch(e){}
  if(!r.ok) throw new Error((b && (b.detail||b.message)) || ("Something went wrong ("+r.status+")")); return b; }
function stepHTML(s){
  let h = '<div class="tool' + (s.refused_by_gate ? ' refused' : '') + '">'
    + '<div><code>' + esc(s.tool) + '</code> ' + esc(Object.values(s.input||{}).join(" · ")).slice(0,140) + '</div>';
  if(s.opencv){ const o = s.opencv, cls = o.route === "opencv_block" ? "block" : (o.route === "llm_two_image" ? "route2" : "ok");
    h += '<div class="cv ' + cls + '"><b>OpenCV: ' + esc(o.decision) + '</b> · ' + Math.round(o.ms_total||0) + ' ms · '
      + esc(ROUTE[o.route] || o.route) + '<div>' + esc(o.reason) + '</div>'
      + (o.instruction ? '<div class="do">' + esc(o.instruction) + '</div>' : '')
      + ((o.images||[]).length ? '<div class="shots">' + o.images.map(i => '<a href="' + esc(i.url) + '" target="_blank" rel="noopener"><img alt="'
          + esc(i.kind) + '" src="' + esc(i.url) + '"></a>').join("") + '</div>' : '') + '</div>'; }
  if(s.refused_by_gate) h += '<div><b class="g">Gate (code, not the model) refused this call</b></div>';
  if(s.result) h += '<div class="res">' + esc(s.result.slice(0,300)) + '</div>';
  return h + '</div>';
}
function drawTurn(t, localPhoto){
  const you = document.createElement("div"); you.className = "msg you";
  you.innerHTML = '<div class="who">You</div><div class="bubble">' + esc(t.person.text) + (t.person.photo ? ' <i>(photo attached)</i>' : '')
    + (localPhoto ? '<img style="display:block;width:100%;border-radius:10px;margin-top:6px" src="' + localPhoto + '">' : '') + '</div>';
  $("feed").appendChild(you);
  const ag = document.createElement("div"); ag.className = "msg";
  ag.innerHTML = '<div class="who">StepSpotter agent · ' + (t.steps||[]).length + ' tool call(s)</div>'
    + (t.steps||[]).map(stepHTML).join("") + '<div class="bubble">' + esc(t.reply).replace(/\n/g,"<br>") + '</div>';
  $("feed").appendChild(ag); ag.scrollIntoView({block:"start"});
}
$("photo").addEventListener("change", () => { const f = $("photo").files[0];
  $("shotLabel").textContent = f ? "Photo ready — tap to change" : "Attach a photo"; $("shotLabel").classList.toggle("has", !!f); });
$("send").addEventListener("click", async () => {
  const text = $("text").value.trim(), f = $("photo").files[0]; $("err").classList.add("hide");
  if(!SID && (!text || !f)) return fail("First message: say what you want to do and attach a photo of it.");
  if(SID && !text && !f) return fail("Write something or attach a photo.");
  const fd = new FormData(); fd.append("text", text); if(f) fd.append("photo", f); if(!SID) fd.append("task", text);
  const url = !SID ? "/api/agent/start" : ("/api/agent/" + SID + (f ? "/photo" : "/say"));
  $("send").disabled = true; $("send").textContent = "Working…";
  const local = f ? URL.createObjectURL(f) : null;
  try { const out = await api(url, {method:"POST", body:fd});
        if(!SID){ SID = out.session; history.replaceState(null, "", "?agent=" + SID); }
        drawTurn(out.turn, local); $("text").value = ""; $("photo").value = "";
        $("shotLabel").textContent = "Attach a photo"; $("shotLabel").classList.remove("has"); }
  catch(e){ fail(e.message); } finally { $("send").disabled = false; $("send").textContent = "Send"; }
});
(async function(){ if(!SID) return; try { const h = await api("/api/agent/" + SID); (h.turns||[]).forEach(t => drawTurn(t)); }
  catch(e){ fail(e.message); SID = null; } })();
</script>
</body></html>
"""
