# -*- coding: utf-8 -*-
"""截图：四库联动后的学情诊断（含示例学情、本次练习、窄屏）。"""
import io
import json
import os
import subprocess
import time
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_shots")
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
const shot = async (n, h) => {
  // 不用 captureBeyondViewport：headless 下它会复用旧合成层，截到上一帧
  await send('Emulation.setDeviceMetricsOverride', {width: h ? 390 : 1000, height: h || 1980,
    deviceScaleFactor: 1, mobile: !!h});
  await sleep(900);
  await ev("window.scrollTo(0,0)");
  await sleep(400);
  const s = await send('Page.captureScreenshot', {format: 'png'});
  require('fs').writeFileSync(OUTDIR + '/' + n, Buffer.from(s.data, 'base64')); };

ws.addEventListener('open', async () => {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1000, height: 1400, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url: URL});
  await sleep(3200);

  // 学情：载入示例学情（旧记录，标注为示例）
  await ev("document.querySelector('[data-tab=diag]').click()");
  await sleep(1800);
  await ev("(function(){var b=[].slice.call(document.querySelectorAll('#diagBox button'))" +
           ".filter(function(x){return x.textContent.indexOf('载入示例')>=0})[0]; if(b) b.click();})()");
  await sleep(2400);
  await shot('diag-seed.png');

  // 练习：出一套同知识点的题（诊断页第一条建议的按钮），答错几题留下完整证据
  await ev("(function(){var b=[].slice.call(document.querySelectorAll('#diagBox .act .btn'))[0]; if(b) b.click();})()");
  await sleep(2600);
  await ev("document.querySelectorAll('#paper .q').forEach(function(q){q.querySelector('.opt').click();})");
  await sleep(300);
  await ev("(function(){var b=[].slice.call(document.querySelectorAll('#paper button'))" +
           ".filter(function(x){return x.textContent.indexOf('提交')>=0})[0]; if(b) b.click();})()");
  await sleep(2400);
  await shot('quiz-kp.png');

  // 回学情：本次练习口径 + 知识点证据 + 错题归因
  await ev("document.querySelector('[data-tab=diag]').click()");
  await sleep(2600);
  // 重新加载一次再截：避免 headless 合成层沿用旧帧
  await send('Page.reload');
  await sleep(3400);
  await ev("document.querySelector('[data-tab=diag]').click()");
  await sleep(2800);
  await shot('diag-final5.png');
  await shot('diag-mobile-final5.png', 844);
  ws.close(); process.exit(0);
});
'''
js_path = os.path.join(OUT, "_shot_diag.js")
io.open(js_path, "w", encoding="utf-8").write(JS)
port = 9917
prof = os.path.join(OUT, "prof_diag")
if os.path.isdir(prof):
    subprocess.run(["cmd", "/c", "rd", "/s", "/q", prof], capture_output=True)
child = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                          "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof,
                          "--window-size=1000,1400", "about:blank"],
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
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
child.kill()
print((r.stdout or "").strip()[:3000])
if r.stderr:
    print("  stderr: " + r.stderr[:300])
