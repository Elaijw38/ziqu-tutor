# -*- coding: utf-8 -*-
"""从「字趣」导出知识库（**只读**，绝不修改原项目）。

产出 data/kb.jsonl，每行一个可检索条目：

    {"id": "...", "char": "日", "kind": "wangyi|boss|codex|glyph",
     "text": "……", "source": "……", "meta": {...}}

为什么要带 source：A2 任务的验收点写着「问答 + 引用溯源」。本项目的
字形数据来自 CC BY 4.0 数据集（DOI 10.5281/zenodo.22467946），每条都
能给出真实出处——这是同类作品很难做到的，检索时必须一起吐出来，
而不是答完再补一句"来自数据集"。
"""
import io
import json
import os
import re

ZQ = r"C:\DSH\字趣"          # 只读来源
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(OUT_DIR, exist_ok=True)

DOI = "10.5281/zenodo.22467946"
GLYPH_SRC = ("hanzi-glyphs-svg / Zenodo，CC BY 4.0，DOI " + DOI)


def load_levels():
    p = os.path.join(ZQ, "js", "core", "levels.json")
    return json.loads(io.open(p, encoding="utf-8").read())


def load_glyph_chars():
    """从 _data.js 里抠出 App.glyphs 的字表（只读，不改）。"""
    p = os.path.join(ZQ, "js", "core", "_data.js")
    t = io.open(p, encoding="utf-8", errors="replace").read()
    i = t.find("App.glyphs = ")
    if i < 0:
        return {}
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
    try:
        d = json.loads(t[i:j])
    except Exception:
        return {}
    g = d.get("glyphs") or d.get("data") or {}
    out = {}
    for k, v in (g.items() if isinstance(g, dict) else []):
        n = 0
        if isinstance(v, dict):
            st = v.get("strokes") or v.get("paths") or v.get("d") or []
            n = len(st) if isinstance(st, (list, tuple)) else (1 if st else 0)
        out[k] = n
    return out


def main():
    lv = load_levels()
    strokes = load_glyph_chars()
    rows = []

    # 1) 王邑实物（第二关）：每个实物点一条
    mp = lv.get("map") or {}
    for zone in mp.get("zones") or []:
        zname = zone.get("name")
        znote = zone.get("note")
        for o in zone.get("objects") or []:
            ch = o.get("char")
            text = "「%s」在殷商王邑图卷的%s区域，代表%s。构形：%s" % (
                ch, zname, o.get("meaning") or "", o.get("form") or "")
            if znote:
                text += "（该区域主题：%s）" % znote
            rows.append({
                "id": "wangyi.%s.%s" % (zone.get("id"), ch),
                "char": ch, "kind": "wangyi",
                "text": text,
                "source": "字趣《殷商王邑》%s区实物点 · 教学示意图（非考古复原）· 字形 %s"
                          % (zname, GLYPH_SRC),
                "meta": {"zone": zname, "zone_id": zone.get("id"),
                          "meaning": o.get("meaning"), "form": o.get("form")},
            })

    # 2) 第三关 Boss（按字）—— 顺手把名录里同一字的形象/打法并进来，
    #    因为 tiers[].list 里没有 play/form，不合并的话这些条目是空壳。
    codex_by_char = {}
    for e in ((lv.get("bossCodex") or {}).get("entries") or []):
        if e.get("char"):
            codex_by_char.setdefault(e["char"], e)
    boss = lv.get("boss") or {}
    for tier in boss.get("tiers") or []:
        for it in tier.get("list") or []:
            ch = it.get("char")
            parts = it.get("parts") or []
            comps = it.get("comps") or []
            cx = codex_by_char.get(ch) or {}
            form = it.get("form") or cx.get("form") or ""
            play = it.get("play") or cx.get("play") or ""
            py = it.get("py") or cx.get("py") or ""
            made = "、".join([p.get("n") or "" for p in parts]) or \
                   ("构件 " + "+".join(comps) if comps else ("笔画 %d 段" % (it.get("seg") or 0)))
            text = "「%s」%s属于%s，字形构成：%s。" % (
                ch, ("（%s）" % py) if py else "", tier.get("name") or "", made)
            if form:
                text += "形象：%s。" % form
            if play:
                text += "打法：%s" % play
            elif tier.get("note"):
                # 名录里没有这一尊时，用本阶的通则打法补上，
                # 否则"虎怎么打"这类问题会答不出东西。
                text += "本阶打法：%s" % tier["note"]
            rows.append({
                "id": "boss.%s" % ch, "char": ch, "kind": "boss",
                "text": text,
                "source": "字趣《构件讨伐》%s · %s" % (tier.get("name"), GLYPH_SRC),
                "meta": {"tier": tier.get("name"), "play": play, "form": form,
                          "comps": comps, "tier_note": tier.get("note") or ""},
            })

    # 3) 讨伐名录（88 尊）
    codex = (lv.get("bossCodex") or {})
    for e in codex.get("entries") or []:
        ch = e.get("char")
        text = "「%s」（%s，%s类）形象：%s。破解：%s" % (
            ch, e.get("py") or "", e.get("group") or "", e.get("form") or "", e.get("play") or "")
        rows.append({
            "id": "codex.%s" % ch, "char": ch, "kind": "codex",
            "text": text,
            "source": "字趣讨伐名录（依据《Boss（象形会意假借）》字表整理）· %s" % GLYPH_SRC,
            "meta": {"group": e.get("group")},
        })

    # 4) 字形本体（有笔画的字，给"这个字几笔、怎么来的"用）
    for ch, n in strokes.items():
        if not ch:
            continue
        rows.append({
            "id": "glyph.%s" % ch,
            "char": ch, "kind": "glyph",
            "text": "「%s」的甲骨字形共 %d 笔（按数据集逐笔几何计）。" % (ch, n or 0),
            "source": GLYPH_SRC,
            "meta": {"strokes": n},
        })

    # 去重（同 id 只留第一条）
    seen, uniq = set(), []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)

    out = os.path.join(OUT_DIR, "kb.jsonl")
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        for r in uniq:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("  写出 %s" % out)
    print("  条目 %d 条：%s" % (len(uniq),
          ", ".join("%s=%d" % (k, sum(1 for r in uniq if r["kind"] == k))
                    for k in ("wangyi", "boss", "codex", "glyph"))))
    chars = sorted({r["char"] for r in uniq if r.get("char")})
    print("  覆盖汉字 %d 个：%s" % (len(chars), "".join(chars[:40]) + ("…" if len(chars) > 40 else "")))


if __name__ == "__main__":
    main()
