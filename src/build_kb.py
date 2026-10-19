# -*- coding: utf-8 -*-
"""构建知识库：四层来源，彼此独立，不依赖某一款教学游戏。

    glyph      1,168 个现代字 / 1,203 个甲骨字形
               来源：Oracle Bone Glyphs 开放数据集 v0.3（CC BY 4.0）
    general    甲骨文通识：发现、材料、占卜、断代、六书、构形规律
               来源：甲骨学与文字学基本文献（逐条标注）
    etymology  常见字的本义与构形解读（日、月、山、水……）
               来源：《说文解字》与裘锡圭《文字学概要》
    wangyi / boss / codex
               课程案例层：字趣《殷商王邑》《构件讨伐》的教学内容
               ——**只是一个可选来源**，不再决定助教的知识边界

产出 data/kb.jsonl，每行一个可检索条目：

    {"id": "...", "char": "日", "kind": "glyph|general|etymology|wangyi|boss|codex",
     "text": "……", "source": "……", "meta": {...}}

为什么要带 source：验收点写着「问答 + 引用溯源」。每条都能给出真实出处，
检索时必须一起吐出来，而不是答完再补一句“来自数据集”。

字趣部分**只读**导出，绝不修改原项目。
"""
import io
import json
import os
import re

ZQ = r"C:\DSH\字趣"          # 只读来源
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(OUT_DIR, exist_ok=True)

DOI = "10.5281/zenodo.22467946"
GLYPH_SRC = ("Oracle Bone Glyphs v0.3（Li & Bian, npj Heritage Science 2026）"
             "，CC BY 4.0，DOI " + DOI)
COURSE_SRC = "字趣《构件讨伐》/《殷商王邑》教学案例"

UPSTREAM = os.path.join(OUT_DIR, "upstream", "jgw_1203_labeled.json")
GENERAL = os.path.join(OUT_DIR, "general.jsonl")

# 只为检索用的简繁别名：上游有 203 个字形标为繁体/异体，学生实际会打简体。
# 这不是完整的简繁转换表，只收本数据集里常见且对应关系无争议的字。
SIMPLIFIED = {
    "龜": "龟", "魚": "鱼", "鳳": "凤", "齊": "齐", "齒": "齿", "頭": "头",
    "寧": "宁", "尋": "寻", "師": "师", "衛": "卫", "轉": "转", "載": "载",
    "輦": "辇", "飲": "饮", "饗": "飨", "續": "续", "純": "纯", "綱": "纲",
    "細": "细", "緘": "缄", "復": "复", "徹": "彻", "協": "协", "堯": "尧",
    "備": "备", "婭": "娅", "嬪": "嫔", "擠": "挤", "糞": "粪", "絶": "绝",
    "雖": "虽", "遠": "远", "鐵": "铁", "鉗": "钳", "鉛": "铅", "銑": "铣",
    "鎳": "镍", "隸": "隶", "雛": "雏", "驤": "骧", "鴻": "鸿", "頜": "颌",
}


def load_levels():
    p = os.path.join(ZQ, "js", "core", "levels.json")
    return json.loads(io.open(p, encoding="utf-8").read())


def load_glyph_dataset(path=UPSTREAM):
    """读上游标注数据，按现代字归并（同一字可能有多个字形）。

    上游字段含义以 data/upstream/ATTRIBUTION.md 为准：
      n_strokes 是**甲骨字形**笔画数，不等于现代通行笔画数（日：甲骨 3、现代 4）；
      pinyin 只作辅助检索，未标声调；unicode 指向现代字，甲骨字形本身无编码。
    """
    if not os.path.exists(path):
        return {}
    with io.open(path, encoding="utf-8") as f:
        rows = json.load(f)
    out = {}
    for r in rows:
        ch = (r.get("modern_char") or "").strip()
        if not ch:
            continue                    # 未释读字形不进检索，避免无字可问
        item = out.setdefault(ch, {
            "char": ch, "pinyin": r.get("pinyin") or "",
            "n_strokes": [], "n_points": [], "glyph_ids": [],
            "char_form": r.get("char_form") or "",
            "unicode": r.get("unicode") or "",
        })
        if r.get("n_strokes"):
            item["n_strokes"].append(int(r["n_strokes"]))
        if r.get("n_points"):
            item["n_points"].append(int(r["n_points"]))
        if r.get("glyph_id"):
            item["glyph_ids"].append(int(r["glyph_id"]))
    return out


def load_general(path=GENERAL):
    """人工整理的通识/字源条目。每条必须自带 source，否则不许入库。"""
    if not os.path.exists(path):
        return []
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if not (r.get("id") and r.get("text") and r.get("source")):
                raise ValueError("通识条目缺字段: %s" % line[:60])
            r.setdefault("kind", "general")
            rows.append(r)
    return rows


def main():
    lv = load_levels()
    glyphs = load_glyph_dataset()
    general = load_general()
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
                          "meaning": o.get("meaning"), "form": o.get("form"),
                          "course": True},
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
                          "comps": comps, "tier_note": tier.get("note") or "",
                          "course": True},
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
            "meta": {"group": e.get("group"), "course": True},
        })

    # 4) 字形全集：上游 1,203 个甲骨字形按现代字归并成 1,168 条。
    #    这是"独立助教"的覆盖面基础——不再受课程关卡里出现过哪些字限制。
    #    措辞必须如实：n_strokes 是甲骨字形笔画，不等于现代通行笔画数。
    for ch, g in sorted(glyphs.items()):
        strokes = g["n_strokes"]
        points = g["n_points"]
        n_form = len(g["glyph_ids"])
        py = g["pinyin"]
        text = "「%s」" % ch
        if py:
            text += "读音 %s（数据集拼音，未标声调）。" % py
        text += "甲骨字形："
        if strokes:
            text += ("数据集标注 %d 画，即甲骨字形的笔画数，"
                     "与现代通行笔画数不一定相同" % strokes[0])
        else:
            text += "数据集未标注笔画数"
        if points:
            text += "；由 %d 个折线点构成。" % points[0]
        else:
            text += "。"
        if n_form > 1:
            text += "该字在数据集中有 %d 个字形（glyph_id %s），属异体或整理上的区分。" % (
                n_form, "、".join(str(x) for x in g["glyph_ids"][:4]))
        if g["char_form"] == "traditional_or_variant":
            text += "数据集标注为繁体或异体写法"
            simp = SIMPLIFIED.get(ch)
            text += ("，今简化为「%s」，按简体也能查到。" % simp) if simp else "。"
        elif g["char_form"] == "undetermined":
            text += "数据集未能确定其现代通行写法。"
        rows.append({
            "id": "glyph.%s" % ch,
            "char": ch, "kind": "glyph",
            "text": text,
            "source": GLYPH_SRC,
            "meta": {"strokes": strokes[0] if strokes else 0,
                      "points": points[0] if points else 0,
                      "pinyin": py, "glyph_ids": g["glyph_ids"],
                      "char_form": g["char_form"], "unicode": g["unicode"],
                      "forms": n_form},
        })

    # 5) 通识与字源：人工整理，逐条带出处；不混进课程字表
    for r in general:
        rows.append(r)

    # 简繁别名写进 meta，检索层据此把「龟」映射到「龜」的字形条目
    for r in rows:
        ch = r.get("char")
        if ch in SIMPLIFIED:
            m = r.setdefault("meta", {})
            m.setdefault("aliases", [])
            if SIMPLIFIED[ch] not in m["aliases"]:
                m["aliases"].append(SIMPLIFIED[ch])

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
    kinds = ("glyph", "general", "etymology", "wangyi", "boss", "codex")
    print("  条目 %d 条：%s" % (len(uniq),
          ", ".join("%s=%d" % (k, sum(1 for r in uniq if r["kind"] == k))
                    for k in kinds)))
    chars = sorted({r["char"] for r in uniq if r.get("char")})
    print("  覆盖汉字 %d 个：%s" % (len(chars), "".join(chars[:40]) + ("…" if len(chars) > 40 else "")))
    course = {r["char"] for r in uniq if (r.get("meta") or {}).get("course") and r.get("char")}
    print("  其中课程字表 %d 个（学情分母只算这一层）" % len(course))
    if len(glyphs) < 1000:
        print("  [警告] 上游字表只有 %d 字，请检查 data/upstream/ 是否完整" % len(glyphs))


if __name__ == "__main__":
    main()
