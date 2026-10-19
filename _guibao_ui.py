# -*- coding: utf-8 -*-
"""把龟宝接进助教界面与人设。

改动四处：
  1) 对话里「助教」改为「龟宝」，消息左侧加头像；
  2) 提问后显示"龟宝正在翻书…"的等待态（带头像），回答到达即替换；
  3) 卡片头部放一枚小头像 + 一句话身份；
  4) 大模型系统提示词加入龟宝人设（但事实约束不变）。
"""
import io

HTML = r"C:\DSH\ziqu-tutor\web\index.html"
LLM = r"C:\DSH\ziqu-tutor\src\llm.py"

h = io.open(HTML, encoding="utf-8").read()

# ---- 1) 样式：头像、身份行、等待态 ----
anchor_css = "  .who{font-size:11.5px;letter-spacing:1px;color:var(--ink-2);margin-bottom:4px}"
new_css = """  .who{display:flex;align-items:center;gap:8px;font-size:11.5px;letter-spacing:1px;
    color:var(--ink-2);margin-bottom:5px}
  .avatar{width:26px;height:26px;border-radius:50%;background:#fff;border:1px solid var(--line);
    object-fit:cover;flex:none}
  .avatar.lg{width:44px;height:44px}
  /* 等待态：龟宝翻书中 */
  .typing .bubble{display:inline-flex;align-items:center;gap:8px;color:var(--ink-2);
    background:#f4f8fd;border:1px dashed #bcd2ee;border-radius:12px;padding:9px 13px}
  .dots i{display:inline-block;width:5px;height:5px;margin-left:2px;border-radius:50%;
    background:var(--zzu-blue);opacity:.35;animation:bl 1.1s infinite}
  .dots i:nth-child(2){animation-delay:.18s}
  .dots i:nth-child(3){animation-delay:.36s}
  @keyframes bl{0%,100%{opacity:.22}50%{opacity:1}}
  .guide{display:flex;gap:12px;align-items:flex-start;padding:14px 16px 4px}
  .guide .say{font-size:13.5px;color:var(--ink-2);line-height:1.7}
  .guide b{color:var(--ink)}"""
assert h.count(anchor_css) == 1
h = h.replace(anchor_css, new_css)

# ---- 2) 卡片头部：小头像 + 身份 ----
old_h2 = '<div class="card-h"><h2>向助教提问</h2>'
new_h2 = ('<div class="card-h"><img class="avatar" src="assets/guibao.png" alt="龟宝">'
          '<h2>问龟宝</h2>')
assert h.count(old_h2) == 1
h = h.replace(old_h2, new_h2)

# ---- 3) 欢迎语（龟宝自我介绍）----
old_quick = '<div class="quick" id="quick"></div>'
new_quick = ('''<div class="guide">
      <img class="avatar lg" src="assets/guibao.png" alt="龟宝">
      <div class="say"><b>我是龟宝，甲骨小向导。</b><br>
      字形怎么来的、某个字在第三关怎么打、我这段时间弱在哪 —— 都可以问我。
      我只看课程知识库回答，答完会给出处，查不到就直接说没有。</div>
    </div>
    <div class="quick" id="quick"></div>''')
assert h.count(old_quick) == 1
h = h.replace(old_quick, new_quick)

# ---- 4) 消息渲染：头像 + 改称呼 ----
old_addask = """function addAsk(q){ const m = el('div','msg ask'); m.appendChild(el('div','who','学生'));
  m.appendChild(el('div','bubble',q)); log.appendChild(m); log.scrollTop = 1e9; }"""
new_addask = """function avatar(cls){
  const i = document.createElement('img');
  i.className = 'avatar' + (cls ? ' ' + cls : '');
  i.src = 'assets/guibao.png'; i.alt = '龟宝';
  return i;
}
function addAsk(q){ const m = el('div','msg ask');
  const w = el('div','who'); w.appendChild(el('span',null,'学生'));
  m.appendChild(w); m.appendChild(el('div','bubble',q));
  log.appendChild(m); log.scrollTop = 1e9; }"""
assert h.count(old_addask) == 1
h = h.replace(old_addask, new_addask)

old_addans = """function addAnswer(a){
  const m = el('div','msg ans'); m.appendChild(el('div','who','助教'));"""
new_addans = """function addAnswer(a){
  const m = el('div','msg ans');
  const w = el('div','who'); w.appendChild(avatar()); w.appendChild(el('span',null,'龟宝'));
  m.appendChild(w);"""
assert h.count(old_addans) == 1
h = h.replace(old_addans, new_addans)

# ---- 5) 等待态 ----
old_ask = """  addAsk(q); input.value=''; send.disabled = true;
  try{"""
new_ask = """  addAsk(q); input.value=''; send.disabled = true;
  // 龟宝"翻书"等待态：先给反馈，避免看起来卡住
  const wait = el('div','msg ans typing');
  const ww = el('div','who'); ww.appendChild(avatar()); ww.appendChild(el('span',null,'龟宝'));
  wait.appendChild(ww);
  const bb = el('div','bubble');
  bb.appendChild(document.createTextNode('正在翻书'));
  const dots = el('span','dots');
  for (let i = 0; i < 3; i++) dots.appendChild(el('i'));
  bb.appendChild(dots); wait.appendChild(bb);
  log.appendChild(wait); log.scrollTop = 1e9;
  try{"""
assert h.count(old_ask) == 1
h = h.replace(old_ask, new_ask)

old_fin = """  finally{ send.disabled = false; input.focus(); }"""
new_fin = """  finally{ if (wait.parentNode) wait.parentNode.removeChild(wait);
    send.disabled = false; input.focus(); }"""
assert h.count(old_fin) == 1
h = h.replace(old_fin, new_fin)

# ---- 6) 页脚补一句素材来源 ----
h = h.replace("<span>校徽版权归郑州大学所有</span>",
              "<span>校徽版权归郑州大学所有</span><span class=\"dot\">·</span>"
              "<span>龟宝形象为本项目原创</span>")

io.open(HTML, "w", encoding="utf-8", newline="\n").write(h)
print("  index.html 已接入龟宝头像/等待态/欢迎语")

# ---- 7) 人设 ----
t = io.open(LLM, encoding="utf-8").read()
old_sys = 'SYSTEM = (\n    "你是郑州大学汉字通识课的甲骨文助教。规则（必须遵守）：\\n"'
new_sys = ('SYSTEM = (\n'
           '    "你是「龟宝」，郑州大学汉字通识课的甲骨文 AI 助教，形象是一只背着行囊的甲骨小向导。\\n"\n'
           '    "自称用「我」，语气亲切但不卖萌，不要用颜文字。\\n"\n'
           '    "规则（必须遵守）：\\n"')
if old_sys in t:
    t = t.replace(old_sys, new_sys)
    io.open(LLM, "w", encoding="utf-8", newline="\n").write(t)
    print("  llm.py 已加入龟宝人设")
else:
    print("  !! 未找到 SYSTEM 锚点，人设未改")
