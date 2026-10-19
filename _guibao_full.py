# -*- coding: utf-8 -*-
"""把龟宝从"圆形头像"改成"站在对话旁边的完整形象"。

理由：头像裁成圆形后，龟宝的行囊、围巾、龟壳全被切掉，形象就不成立了。
现在改成左栏一个整身龟宝（带一句自我介绍），右栏是对话；手机上龟宝缩到顶部一行。
消息里不再放头像，只保留「学生 / 龟宝」的名字标注。
"""
import io

P = r"C:\DSH\ziqu-tutor\web\index.html"
h = io.open(P, encoding="utf-8").read()

# ---------- 1) CSS ----------
old_css = """  .avatar{width:26px;height:26px;border-radius:50%;background:#fff;border:1px solid var(--line);
    object-fit:cover;flex:none}
  .avatar.lg{width:44px;height:44px}"""
new_css = """  /* 龟宝：整身站在对话左侧，不做圆形头像 */
  .chat-wrap{display:flex;align-items:stretch}
  .guide-col{width:214px;flex:none;padding:6px 0 12px 14px;display:flex;
    flex-direction:column;justify-content:flex-end;gap:10px}
  .guide-fig{width:100%;max-width:200px;margin:0 auto;display:block;
    filter:drop-shadow(0 10px 16px rgba(60,70,90,.14))}
  .guide-say{font-size:12.5px;line-height:1.65;color:var(--ink-2);background:#fff;
    border:1px solid var(--line);border-radius:12px;padding:9px 11px;position:relative}
  .guide-say::after{content:'';position:absolute;left:16px;bottom:-6px;width:10px;height:10px;
    background:#fff;border-right:1px solid var(--line);border-bottom:1px solid var(--line);
    transform:rotate(45deg)}
  .guide-say b{color:var(--ink)}
  .main-col{flex:1;min-width:0;display:flex;flex-direction:column}"""
assert h.count(old_css) == 1
h = h.replace(old_css, new_css)

old_guide_css = """  .guide{display:flex;gap:12px;align-items:flex-start;padding:14px 16px 4px}
  .guide .say{font-size:13.5px;color:var(--ink-2);line-height:1.7}
  .guide b{color:var(--ink)}"""
new_guide_css = """  @media (max-width:760px){
    .chat-wrap{flex-direction:column}
    .guide-col{width:auto;flex-direction:row;align-items:center;gap:12px;
      padding:12px 14px 0;justify-content:flex-start}
    .guide-fig{width:104px;flex:none;margin:0}
    .guide-say::after{left:50%;bottom:-6px;margin-left:-5px}
  }"""
assert h.count(old_guide_css) == 1
h = h.replace(old_guide_css, new_guide_css)

# ---------- 2) 卡片标题：去掉小头像 ----------
old_h2 = ('<div class="card-h"><img class="avatar" src="assets/guibao.png" alt="龟宝">'
          '<h2>问龟宝</h2>')
new_h2 = '<div class="card-h"><h2>问龟宝</h2>'
assert h.count(old_h2) == 1
h = h.replace(old_h2, new_h2)

# ---------- 3) 结构：左龟宝 / 右对话 ----------
old_body = """    <div class="guide">
      <img class="avatar lg" src="assets/guibao.png" alt="龟宝">
      <div class="say"><b>我是龟宝，甲骨小向导。</b><br>
      字形怎么来的、某个字在第三关怎么打、我这段时间弱在哪 —— 都可以问我。
      我只看课程知识库回答，答完会给出处，查不到就直接说没有。</div>
    </div>
    <div class="quick" id="quick"></div>
    <div class="log" id="log"></div>
    <form id="f">
      <input type="text" id="q" placeholder="例如：家为什么是屋顶下有猪" autocomplete="off">
      <button class="btn" type="submit" id="send">提问</button>
    </form>"""
new_body = """    <div class="chat-wrap">
      <aside class="guide-col">
        <img class="guide-fig" src="assets/guibao.png" alt="龟宝——甲骨小向导">
        <div class="guide-say"><b>我是龟宝，甲骨小向导。</b><br>
          字形怎么来的、某个字在第三关怎么打、我这段时间弱在哪，都可以问我。
          答完会给出处，查不到就直接说没有。</div>
      </aside>
      <div class="main-col">
        <div class="quick" id="quick"></div>
        <div class="log" id="log"></div>
        <form id="f">
          <input type="text" id="q" placeholder="例如：家为什么是屋顶下有猪" autocomplete="off">
          <button class="btn" type="submit" id="send">提问</button>
        </form>
      </div>
    </div>"""
assert h.count(old_body) == 1
h = h.replace(old_body, new_body)

# ---------- 4) JS：去掉消息里的头像 ----------
old_av = """function avatar(cls){
  const i = document.createElement('img');
  i.className = 'avatar' + (cls ? ' ' + cls : '');
  i.src = 'assets/guibao.png'; i.alt = '龟宝';
  return i;
}
"""
assert h.count(old_av) == 1
h = h.replace(old_av, "")

old_ans = """  const w = el('div','who'); w.appendChild(avatar()); w.appendChild(el('span',null,'龟宝'));
  m.appendChild(w);"""
new_ans = """  m.appendChild(el('div','who','龟宝'));"""
assert h.count(old_ans) == 1
h = h.replace(old_ans, new_ans)

old_wait = """  const ww = el('div','who'); ww.appendChild(avatar()); ww.appendChild(el('span',null,'龟宝'));
  wait.appendChild(ww);"""
new_wait = """  wait.appendChild(el('div','who','龟宝'));"""
assert h.count(old_wait) == 1
h = h.replace(old_wait, new_wait)

io.open(P, "w", encoding="utf-8", newline="\n").write(h)
print("  已改为：整身龟宝在左、对话在右；消息内不再放头像")
