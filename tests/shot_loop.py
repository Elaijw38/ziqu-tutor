# -*- coding: utf-8 -*-
"""截图：智能体自主多步（出题 → 判分 → 巩固）与工具轨迹。"""
import json
import os
import subprocess
import time
import urllib.request

ROOT = r"C:\DSH\ziqu-tutor"
OUT = os.path.join(ROOT, "_shots")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
NODE = r"C:\Users\32058\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"

JS = r'''
const ws = new WebSocket(process.argv[2]);
const OUTDIR = process.argv[3], URL = process.argv[4];
let id = 0; const pend = new Map();
const send = (m, q) => new Promise(r => { const i = ++id; pend.set(i, r);
  ws.send(JSON.stringify({id:i, method:m, params:q||{}})); });
ws.addEventListener('message', e => { const m = JSON.parse(e.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); } });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ev = x => send('Runtime.evaluate', {expression:x, returnByValue:true, awaitPromise:true})
  .then(r => (r && r.exceptionDetails) ? 'EXC' : (r.result && r.result.value));
async function say(text, wait){
  await ev("(function(){var i=document.getElementById('q');i.value=" + JSON.stringify(text) + ";" +
    "var f=document.getElementById('f');f.dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));})()");
  await sleep(wait);
}
ws.addEventListener('open', async () => {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:1080, height:1400, deviceScaleFactor:1, mobile:false});
  await send('Page.navigate', {url: URL});
  await sleep(6000);
  await say('给我出三道题', 20000);
  await say('第一题选 A，其余都选 B', 26000);
  const info = await ev("JSON.stringify({trace:[].slice.call(document.querySelectorAll('.tchip')).map(function(x){return x.textContent;})," +
    "msgs:document.querySelectorAll('.msg').length})");
  console.log('INFO ' + info);
  const s = await send('Page.captureScreenshot', {format:'png', captureBeyondViewport:true});
  require('fs').writeFileSync(OUTDIR + '/agent-loop.png', Buffer.from(s.data,'base64'));
  ws.close(); process.exit(0);
});
'''
js_path = os.path.join(OUT, "_shot_loop.js")
open(js_path, "w", encoding="utf-8").write(JS)
port = 9981
prof = os.path.join(OUT, "loopprof")
if os.path.isdir(prof):
    subprocess.run(["cmd", "/c", "rd", "/s", "/q", prof], capture_output=True)
child = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                          "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof,
                          "--window-size=1100,1450", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
targets = None
for _ in range(80):
    time.sleep(0.4)
    try:
        targets = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=8))
        if any(t.get("type") == "page" and t.get("webSocketDebuggerUrl") for t in targets):
            break
    except Exception:
        pass
page = [t for t in (targets or []) if t.get("type") == "page" and t.get("webSocketDebuggerUrl")][0]
r = subprocess.run([NODE, js_path, page["webSocketDebuggerUrl"], OUT, "http://127.0.0.1:8770/"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
child.kill()
print((r.stdout or "").strip()[:400])
if r.stderr:
    print("stderr:", r.stderr[:200])
