# -*- coding: utf-8 -*-
"""给助教页面截图（用 Edge headless + CDP，和字趣那套一样）。"""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

OUT = r"C:\DSH\ziqu-tutor\_shots"
os.makedirs(OUT, exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
NODE = r"C:\Users\32058\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
URL = "http://127.0.0.1:8770/"
W = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
H = int(sys.argv[2]) if len(sys.argv) > 2 else 900

JS = r'''
const ws = new WebSocket(process.argv[2]);
const OUTDIR = process.argv[3], URL = process.argv[4];
let id = 0; const pend = new Map();
const send = (m, q) => new Promise(r => { const i = ++id; pend.set(i, r);
  ws.send(JSON.stringify({id: i, method: m, params: q || {}})); });
ws.addEventListener('message', e => { const m = JSON.parse(e.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); } });
const sleep = ms => new Promise(r => setTimeout(r, ms));
ws.addEventListener('open', async () => {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',
    {width: +process.argv[5], height: +process.argv[6], deviceScaleFactor: 1, mobile: +process.argv[5] < 700});
  await send('Page.navigate', {url: URL});
  await sleep(3500);
  const click = "(function(){var b=[].slice.call(document.querySelectorAll('.chip'))" +
    ".filter(function(x){return x.textContent.indexOf('虎怎么打')>=0})[0];" +
    "if(!b)return 'no-chip';b.click();return 'ok';})()";
  const r = await send('Runtime.evaluate', {expression: click, returnByValue: true});
  console.log('CLICK ' + (r.result && r.result.value));
  await sleep(1600);
  const s = await send('Page.captureScreenshot', {format: 'png'});
  require('fs').writeFileSync(OUTDIR + '/tutor-' + process.argv[5] + 'x' + process.argv[6] + '.png', Buffer.from(s.data, 'base64'));
  ws.close(); process.exit(0);
});
'''
js_path = os.path.join(OUT, "_shot.js")
io.open(js_path, "w", encoding="utf-8").write(JS)
port = 9911
prof = os.path.join(OUT, "prof")
if os.path.isdir(prof):
    subprocess.run(["cmd", "/c", "rd", "/s", "/q", prof], capture_output=True)
child = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                          "--remote-debugging-port=%d" % port,
                          "--user-data-dir=" + prof, "--window-size=1100,1000",
                          "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
targets = None
for _ in range(80):
    time.sleep(0.4)
    try:
        targets = json.load(urllib.request.urlopen(
            "http://127.0.0.1:%d/json/list" % port, timeout=8))
        if any(t.get("type") == "page" and t.get("webSocketDebuggerUrl") for t in targets):
            break
    except Exception:
        pass
page = [t for t in (targets or []) if t.get("type") == "page"
        and t.get("webSocketDebuggerUrl")][0]
r = subprocess.run([NODE, js_path, page["webSocketDebuggerUrl"], OUT, URL,
                    str(W), str(H)],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=180)
child.kill()
print("  " + (r.stdout or "").strip()[:200])
if r.stderr:
    print("  stderr: " + r.stderr[:200])
try:
    os.remove(js_path)
except OSError:
    pass
