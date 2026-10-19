import io
p = "web/index.html"
t = io.open(p, encoding="utf-8").read()

# 用真校徽替换 CSS 占位圆环
old_css = """  .zzu .mark{width:38px;height:38px;border-radius:50%;border:2px solid var(--zzu-red);
    display:grid;place-items:center;position:relative;background:#fff;flex:none}
  .zzu .mark::after{content:'郑';color:var(--zzu-red);font-size:17px;font-weight:700}"""
new_css = """  /* 校徽：只按比例缩放到 38px 高，不裁切、不变形、不改色（遵守校徽使用规范） */
  .zzu .mark{width:38px;height:38px;display:block;flex:none;object-fit:contain}"""
assert t.count(old_css) == 1
t = t.replace(old_css, new_css)

old_dom = '      <span class="mark"></span>'
new_dom = '      <img class="mark" src="assets/zzu-logo.png" alt="郑州大学校徽">'
assert t.count(old_dom) == 1
t = t.replace(old_dom, new_dom)

# 页脚补一句：校徽版权归学校
t = t.replace("<span>非商业教学演示</span>",
              "<span>非商业教学演示</span><span class=\"dot\">·</span><span>校徽版权归郑州大学所有</span>")
io.open(p, "w", encoding="utf-8", newline="\n").write(t)
print("  校徽已接入顶栏")
