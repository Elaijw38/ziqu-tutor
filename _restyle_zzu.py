# -*- coding: utf-8 -*-
"""按郑大网上办事大厅的实际视觉重做界面：
主色改深宝蓝（#16336B），底色改白→浅蓝，顶栏改「校徽＋双语校名｜应用名」，
主视觉加大号「求是 担当」水印，卡片改白底圆角轻阴影。
"""
import io
import re

P = r"C:\DSH\ziqu-tutor\web\index.html"
t = io.open(P, encoding="utf-8").read()

# ---------- 1) 颜色体系 ----------
old_root = re.search(r"  :root\{.*?\n  \}\n", t, re.S).group(0)
new_root = """  :root{
    /* 取色参照郑大网上办事大厅：主色深宝蓝，红仅作校徽红点缀 */
    --zzu-blue:#16336b;
    --zzu-blue-2:#1f4a8f;
    --zzu-blue-soft:#eaf1fb;
    --zzu-red:#a4231f;
    --paper:#f4f8fd;
    --paper-2:#ffffff;
    --ink:#1b2432;
    --ink-2:#5c6b80;
    --line:#e2e9f3;
    --gold:#b98b3c;
    --ok:#2f6b46;
  }
"""
t = t.replace(old_root, new_root)

# 变量改名的连带替换
t = t.replace("var(--navy-2)", "var(--zzu-blue-2)").replace("var(--navy)", "var(--zzu-blue)")
t = t.replace("rgba(164,35,31,.1)", "rgba(22,51,107,.12)")

# ---------- 2) 页面底：白 → 浅蓝 ----------
t = t.replace("body{margin:0;color:var(--ink);background:var(--paper);",
              "body{margin:0;color:var(--ink);\n    background:linear-gradient(180deg,#ffffff 0%,#eef4fc 38%,#e8f0fa 100%) fixed;")

# ---------- 3) 顶栏：白底 + 校徽位 + 双语校名 ----------
old_top = re.search(r"  /\* 校名顶栏 \*/\n.*?  \.contest\{[^}]*\}\n", t, re.S).group(0)
new_top = """  /* 校名顶栏：照郑大办事大厅的做法——白底、圆形校徽位、双语校名、竖线分隔 */
  .top{background:#fff;border-bottom:1px solid var(--line);
    box-shadow:0 1px 6px rgba(22,51,107,.06)}
  .top-in{max-width:1120px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  .zzu{display:flex;align-items:center;gap:11px}
  .zzu .mark{width:38px;height:38px;border-radius:50%;border:2px solid var(--zzu-red);
    display:grid;place-items:center;position:relative;background:#fff;flex:none}
  .zzu .mark::after{content:'郑';color:var(--zzu-red);font-size:17px;font-weight:700}
  .zzu .names{display:flex;flex-direction:column;line-height:1.15}
  .zzu .cn{font-size:16.5px;letter-spacing:3px;font-weight:600;color:var(--ink)}
  .zzu .en{font-size:8.5px;letter-spacing:1.6px;color:#8a97ab;text-transform:uppercase}
  .top-sep{width:1px;height:26px;background:var(--line)}
  .app-name{font-size:15.5px;letter-spacing:1px;color:var(--zzu-blue);font-weight:600}
  .top-right{margin-left:auto;display:flex;align-items:center;gap:10px}
  .contest{font-size:12px;letter-spacing:.5px;padding:4px 10px;border-radius:999px;
    background:var(--zzu-blue-soft);border:1px solid #cfe0f5;color:var(--zzu-blue)}
"""
t = t.replace(old_top, new_top)

# ---------- 4) 课程条：白蓝，弱化 ----------
t = t.replace(".ctx{background:#eee7d7;border-bottom:1px solid var(--line)}",
              ".ctx{background:#f8fbff;border-bottom:1px solid var(--line)}")

# ---------- 5) 主视觉：加大号「求是 担当」水印 ----------
t = t.replace("  .hero{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:16px}",
"""  .hero{position:relative;display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;
    margin-bottom:16px;overflow:hidden;padding:6px 0 2px}
  /* 校训水印：郑大办事大厅左侧就是这四个字，这里做成极淡的背景，不抢内容 */
  .hero::before{content:'求是 担当';position:absolute;right:-6px;top:-18px;
    font-size:78px;letter-spacing:8px;color:rgba(22,51,107,.055);font-weight:700;
    pointer-events:none;white-space:nowrap}""")

# ---------- 6) 卡片/标签/按钮改用蓝色为主 ----------
t = t.replace(".tab.on{background:var(--zzu-red);border-color:var(--zzu-red);color:#fff;font-weight:600}",
              ".tab.on{background:var(--zzu-blue);border-color:var(--zzu-blue);color:#fff;font-weight:600}")
t = t.replace(".btn{padding:10px 20px;border:0;border-radius:10px;background:var(--zzu-red);color:#fff;",
              ".btn{padding:10px 22px;border:0;border-radius:9px;background:var(--zzu-blue);color:#fff;")
t = t.replace(".btn:hover{background:var(--zzu-red-deep)}", ".btn:hover{background:var(--zzu-blue-2)}")
t = t.replace(".ans .bubble{background:#fff;border:1px solid var(--line);border-left:3px solid var(--zzu-red);",
              ".ans .bubble{background:#fff;border:1px solid var(--line);border-left:3px solid var(--zzu-blue);")
t = t.replace(".bar i{display:block;height:100%;background:linear-gradient(90deg,var(--zzu-red),#c9564f)}",
              ".bar i{display:block;height:100%;background:linear-gradient(90deg,var(--zzu-blue),#3f74c4)}")
t = t.replace(".stat.red b{color:var(--zzu-red)}", ".stat.red b{color:var(--zzu-red)}\n  .stat b{color:var(--zzu-blue)}")
t = t.replace("h1 em{font-style:normal;color:var(--zzu-red)}",
              "h1 em{font-style:normal;color:var(--zzu-blue)}")
t = t.replace(".opt.sel{border-color:var(--zzu-red);background:#fdf1ee}",
              ".opt.sel{border-color:var(--zzu-blue);background:#f2f7ff}")
t = t.replace("input[type=text]:focus{border-color:var(--zzu-red);",
              "input[type=text]:focus{border-color:var(--zzu-blue);")
t = t.replace('.comp b{color:var(--zzu-red);font-weight:600}',
              '.comp b{color:var(--zzu-blue);font-weight:600}')

# ---------- 7) 顶栏 DOM 结构 ----------
old_dom = re.search(r'    <span class="zzu"><i>郑</i>郑州大学</span>\n', t).group(0)
new_dom = """    <span class="zzu">
      <span class="mark"></span>
      <span class="names"><b class="cn">郑州大学</b><span class="en">Zhengzhou University</span></span>
    </span>
"""
t = t.replace(old_dom, new_dom)

io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("  已按郑大办事大厅视觉重做：深宝蓝主色 / 白底 / 双语校名 / 求是担当水印")
