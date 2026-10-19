# -*- coding: utf-8 -*-
"""截图：练习闭环（出题→作答→评阅）与学情画像。"""
import io
import json
import os
import subprocess
import time
import urllib.request

OUT = r"C:\DSH\ziqu-tutor\_shots"
os.makedirs(OUT, exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
NODE = r"C:\Users\32058\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
URL = "http://127.0.0.1:8770/"

JS = r'''
const ws = new WebSocket(process.argv[2]);
const OUTDIR = process.argv[3], URL = process.argv[4];
let id = 0; const pend = new Map();
const send = (m, q) => new Promise(r => { const i = ++id; pend.set(i, r);
  ws.send(JSON.stringify({id: i, method: m, params: q || {}})); });
ws.addEventListener('message', e => { const m = JSON.parse(e.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); } });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ev = x => send('Runtime.evaluate', {expression: x, returnByValue: true, awaitPromise: true})
  .then(r => (r && r.exceptionDetails) ? 'EXC' : (r.result && r.result.value));
const shot = async n => { const s = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
  require('fs').writeFileSync(OUTDIR + '/' + n, Buffer.from(s.data, 'base64')); };

ws.addEventListener('open', async () => {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 980, height: 1100, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url: URL});
  await sleep(3000);

  // 练习：出一套题，每题选第一个选项（故意可能有错），提交评阅
  await ev("document.querySelector('[data-tab=quiz]').click()");
  await sleep(400);
  await ev("document.getElementById('mk').click()");
  await sleep(2200);
  await ev("document.querySelectorAll('#paper .q').forEach(function(q){q.querySelector('.opt').click();})");
  await sleep(300);
  await ev("(function(){var b=[].slice.call(document.querySelectorAll('#paper .btn, #paper button'))" +
           ".filter(function(x){return x.textContent.indexOf('提交')>=0})[0]; if(b) b.click();})()");
  await sleep(2200);
  await shot('quiz-graded.png');

  // 学情：评阅会写回 attempts，画像随之变化
  await ev("document.querySelector('[data-tab=diag]').click()");
  await sleep(2200);
  await shot('diag.png');
  ws.close(); process.exit(0);
});
'''
js_path = os.path.join(OUT, "_shot2.js")
io.open(js_path, "w", encoding="utf-8").write(JS)
port = 9913
prof = os.path.join(OUT, "prof2")
if os.path.isdir(prof):
    subprocess.run(["cmd", "/c", "rd", "/s", "/q", prof], capture_output=True)
child = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                          "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof,
                          "--window-size=1000,1200", "about:blank"],
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
r = subprocess.run([NODE, js_path, page["webSocketDebuggerUrl"], OUT, URL],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
child.kill()
print("  " + (r.stdout or "").strip()[:150])
if r.stderr:
    print("  stderr: " + r.stderr[:200])
