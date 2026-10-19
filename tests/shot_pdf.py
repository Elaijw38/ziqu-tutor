# -*- coding: utf-8 -*-
"""把 PDF 前两页渲染成 PNG（Edge 自带 PDF 阅读器），用于目视检查表单排版。"""
import io
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

OUT = r"C:\DSH\ziqu-tutor\out"
PDF = os.path.join(OUT, "申报表预览.pdf")
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
ws.addEventListener('open', async () => {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:1100,height:1500,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate', {url: URL});
  await sleep(9000);
  for (let i = 1; i <= 2; i++) {
    const s = await send('Page.captureScreenshot', {format:'png'});
    require('fs').writeFileSync(OUTDIR + '/form-p' + i + '.png', Buffer.from(s.data,'base64'));
    await send('Runtime.evaluate', {expression:
      "window.scrollBy(0, window.innerHeight)"});
    await sleep(1500);
  }
  ws.close(); process.exit(0);
});
'''
js = os.path.join(OUT, "_pdfshot.js")
io.open(js, "w", encoding="utf-8").write(JS)
url = "file:///" + urllib.parse.quote(PDF.replace("\\", "/"))
port = 9931
prof = os.path.join(OUT, "pdfprof")
if os.path.isdir(prof):
    subprocess.run(["cmd", "/c", "rd", "/s", "/q", prof], capture_output=True)
child = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                          "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof,
                          "--window-size=1200,1600", "about:blank"],
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
r = subprocess.run([NODE, js, page["webSocketDebuggerUrl"], OUT, url],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
child.kill()
print("  " + (r.stdout or "").strip()[:120])
for f in ("form-p1.png", "form-p2.png"):
    p = os.path.join(OUT, f)
    print("  %s %s" % (f, "OK %.0f KB" % (os.path.getsize(p) / 1024) if os.path.exists(p) else "缺失"))
