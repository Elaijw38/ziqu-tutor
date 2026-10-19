# -*- coding: utf-8 -*-
"""摸清 stroke 字段的编码：一行到底怎么排成笔画。"""
import collections
import io
import json

P = r"C:\DSH\ziqu-tutor\data\upstream\jgw_1203_labeled.json"
d = json.loads(io.open(P, encoding="utf-8").read())
print("  记录数:", len(d))

for r in d[:3]:
    toks = [t for t in (r["stroke"] or "").split(",")]
    print("\n  glyph %s 「%s」 n_points=%s n_strokes=%s"
          % (r["glyph_id"], r["modern_char"], r["n_points"], r["n_strokes"]))
    print("    stroke 原文:", (r["stroke"] or "")[:120])
    print("    token 数（含空）:", len(toks), " 非空 token:", len([t for t in toks if t.strip()]))

# 统计
lens = []
for r in d:
    toks = (r["stroke"] or "").split(",")
    lens.append((len(toks), len([t for t in toks if t.strip()]), r["n_points"], r["n_strokes"]))
print("\n  样本统计（前 8 条）：")
for x in lens[:8]:
    print("   tokens=%d 非空=%d n_points=%s n_strokes=%s" % x)

# 检查 非空token 与 n_points 的关系
rel = collections.Counter()
for tot, ne, np_, ns in lens:
    rel[(round(ne / max(1, np_ * 2), 2), round(ne / max(1, np_), 2))] = rel.get(
        (round(ne / max(1, np_ * 2), 2), round(ne / max(1, np_), 2)), 0) + 1
print("\n  非空token / (n_points) 与 / (n_points*2) 的比值分布（前 6）：")
for k, v in rel.most_common(6):
    print("    ratio(ne/(np*2)), ne/np = %s  次数 %d" % (str(k), v))

# 值域
vals = []
for r in d[:200]:
    for t in (r["stroke"] or "").split(","):
        t = t.strip()
        if t:
            try:
                vals.append(float(t))
            except ValueError:
                pass
if vals:
    print("\n  数值范围: %.1f ~ %.1f（样本 %d 个）" % (min(vals), max(vals), len(vals)))
