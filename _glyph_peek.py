# -*- coding: utf-8 -*-
"""摸清 字趣 里 App.glyphs 的结构，为导出甲骨字形做准备（只读）。"""
import io
import json

P = r"C:\DSH\字趣\js\core\_data.js"
t = io.open(P, encoding="utf-8", errors="replace").read()

i = t.find("App.glyphs = ")
i += len("App.glyphs = ")
depth, j = 0, i
while j < len(t):
    ch = t[j]
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
        if depth == 0:
            j += 1
            break
    j += 1
d = json.loads(t[i:j])
print("  顶层字段:", list(d.keys())[:10])
for k in list(d.keys())[:6]:
    v = d[k]
    if isinstance(v, dict):
        print("  %s: dict(%d)，子键样例 %s" % (k, len(v), list(v.keys())[:6]))
    elif isinstance(v, list):
        print("  %s: list(%d)，首元素类型 %s" % (k, len(v), type(v[0]).__name__))
    else:
        print("  %s: %r" % (k, v))

# 找一个字看细节
for cand in ("glyphs", "data", "items", "chars"):
    if isinstance(d.get(cand), dict) and d[cand]:
        k0 = next(iter(d[cand]))
        print("\n  %s 首键: %r" % (cand, k0))
        print("  值:", json.dumps(d[cand][k0], ensure_ascii=False)[:500])
        break
