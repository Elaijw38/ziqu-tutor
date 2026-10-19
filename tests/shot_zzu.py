# -*- coding: utf-8 -*-
"""给一组 URL 截图（只看公开页面，不做任何登录）。"""
import io
import json
import os
import subprocess
import time
import urllib.request

OUT = r"C:\DSH\ziqu-tutor\_shots\zzu"
os.makedirs(OUT, exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
NODE = r"C:\Users\32058\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"

URLS = [
    ("portal", "https://info.s.zzu.edu.cn/main.html"),
    ("ehall", "http://ehall.v.zzu.edu.cn/taskcenter/"),
    ("jwxt", "https://jwxt.zzu.edu.cn/"),
    ("jw-old", "http://jw.zzu.edu.cn/"),
]

JS = r'''
const ws = new WebSocket(process.argv[2]);
const OUTDIR = process.argv[3];
let id = 0; const pend = new Map();
const send = (m, q) => new Promise(r => { const i = ++id; pend.set(i, r);
  ws.send(JSON.stringify({id:i, method:m, params:q||{}})); });
ws.addEventListener('message', e => { const m = JSON.parse(e.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); } });
const sleep = ms => new Promise(r => setTimeout(r, ms));
ws.addEventListener('open', async () => {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width:1440,height:900,deviceScaleFactor:1,mobile:false});
  const pairs = JSON.parse(process.argv[4]);
  for (const [name, url] of pairs) {
    try {
      await send('Page.navigate', {url});
      await sleep(6000);
      const title = await send('Runtime.evaluate', {expression:'document.title', returnByValue:true});
      const s = await send('Page.captureScreenshot', {format:'png'});
      require('fs').writeFileSync(OUTDIR + '/' + name + '.png', Buffer.from(s.data,'base64'));
      console.log('OK ' + name + ' | ' + ((title.result && title.result.value) || ''));
    } catch (e) {
      console.log('FAIL ' + name);
    }
  }
  ws.close(); process.exit(0);
});
'''
js_path = os.path.join(OUT, "_shot.js")
io.open(js_path, "w", encoding="utf-8").write(JS)

port = 9921
prof = os.path.join(OUT, "prof")
if os.path.isdir(prof):
    subprocess.run(["cmd", "/c", "rd", "/s", "/q", prof], capture_output=True)
child = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                          "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof,
                          "--window-size=1500,1000", "about:blank"],
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
r = subprocess.run([NODE, js_path, page["webSocketDebuggerUrl"], OUT,
                    json.dumps(URLS, ensure_ascii=False)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
child.kill()
print((r.stdout or "").strip())
if r.stderr:
    print("stderr:", r.stderr[:300])
