# -*- coding: utf-8 -*-
"""知识库结构测试：覆盖边界、来源完整性、诊断分母、检索命中。

不依赖大模型，也不写 learner.json —— 只读数据文件。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import learner                      # noqa: E402
from retrieval import get_index      # noqa: E402

OK = []


def check(name, cond, detail=""):
    OK.append(bool(cond))
    print("  %s %s%s" % ("✓" if cond else "✗", name,
                         ("  ← " + detail) if (detail and not cond) else ""))


def main():
    idx = get_index()
    rows = idx.rows

    print("\n[1] 覆盖面")
    glyph = [r for r in rows if r["kind"] == "glyph"]
    glyph_chars = {r["char"] for r in glyph}
    check("字形层 ≥ 1100 字", len(glyph_chars) >= 1100, str(len(glyph_chars)))
    check("总字表 ≥ 1150 字", len({r["char"] for r in rows if r.get("char")}) >= 1150)
    check("通识层 ≥ 20 条", sum(1 for r in rows if r["kind"] == "general") >= 20)
    check("字源层 ≥ 25 条", sum(1 for r in rows if r["kind"] == "etymology") >= 25)

    print("\n[2] 来源与字段")
    no_src = [r["id"] for r in rows if not (r.get("source") or "").strip()]
    check("每条都有 source", not no_src, "缺: %s" % no_src[:3])
    bad_glyph = [r["id"] for r in glyph
                 if not (r.get("meta") or {}).get("pinyin")
                 or not (r.get("meta") or {}).get("strokes")]
    check("字形条条有拼音与笔画", not bad_glyph, "缺: %s" % bad_glyph[:3])
    check("字形来源含 DOI", all("10.5281/zenodo.22467946" in r["source"] for r in glyph))
    gen = [r for r in rows if r["kind"] == "general"]
    check("通识来源可核查", all(("《" in r["source"]) for r in gen),
          "可疑: %s" % [r["id"] for r in gen if "《" not in r["source"]][:3])

    print("\n[3] 课程层与字形层分离")
    course = learner.course_chars(rows)
    check("课程字表 = 146", len(course) == 146, str(len(course)))
    glyph_only = sorted(glyph_chars - course)
    check("存在字形独有字", bool(glyph_only), "无")

    orig = learner.load
    try:
        learner.load = lambda vid="": {"done": {"sky": [glyph_only[0]]},
                                "bossCleared": [], "attempts": []}
        d = learner.diagnose(idx)
    finally:
        learner.load = orig
    check("学过字形独有字不改覆盖率", d["coverage"] == 0.0, str(d["coverage"]))
    check("诊断分母是课程字表", d["total_chars"] == 146, str(d["total_chars"]))
    check("诊断同时给出字表规模", d["lexicon_chars"] >= 1150, str(d["lexicon_chars"]))
    # 口径：lexicon_chars 必须是「真有甲骨字形数据」的字数，不能拿知识库去重字数顶替
    real_glyph = {r["char"] for r in idx.rows if r.get("kind") == "glyph"}
    check("字形库口径不含无字形字",
          d["lexicon_chars"] == len(real_glyph) and d["lexicon_chars"] < d["kb_chars"],
          "lexicon=%s kb=%s" % (d["lexicon_chars"], d["kb_chars"]))

    print("\n[4] 检索命中")
    def top(q, k=3):
        return [(r["kind"], r.get("char")) for r, _ in idx.search(q, k)]

    check("「日怎么读」首条是字形", top("日怎么读")[0] == ("glyph", "日"), str(top("日怎么读")))
    check("「龟几画」命中龜的字形", ("glyph", "龜") in top("龟几画"), str(top("龟几画")))
    check("「甲骨文是谁发现的」命中通识",
          any(k == "general" for k, _ in top("甲骨文是谁发现的")), str(top("甲骨文是谁发现的")))
    check("「家为什么是屋顶下有猪」命中课程层",
          any(k in ("wangyi", "boss", "codex") for k, _ in top("家为什么是屋顶下有猪")),
          str(top("家为什么是屋顶下有猪")))
    check("「什么是会意」命中六书条目",
          any(k == "general" for k, _ in top("什么是会意")), str(top("什么是会意")))

    print("\n[5] 出题不越界")
    import quiz
    qz = quiz.make_quiz(3, seed=7)
    chars = {it["char"] for it in qz.get("items") or []}
    check("出题只取课程字", chars.issubset(course), str(sorted(chars - course)))
    # 练习页签的题目由浏览器回传判分（已知待改）；这里只校验 agent 工具路径是否泄答案
    import llm
    tool = llm._exec_tool("generate_quiz", {"n": 2, "seed": 7}, idx, learner)
    check("agent 出题不泄答案",
          all("answer" not in it and "answer_index" not in it
              for it in tool.get("items") or []))

    ok = all(OK)
    print("\n结论:", "✓ 知识库结构通过（%d/%d）" % (sum(OK), len(OK))
          if ok else "✗ 未通过（%d/%d）" % (sum(OK), len(OK)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
