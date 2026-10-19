# -*- coding: utf-8 -*-
"""出题与评阅。

题目**全部由知识库字段生成**，不预设题库——所以知识库一扩，题目跟着变。
三种题型，分别对应三种能力：
  form   「某字代表什么」→ 考象形理解
  comp   「某字由哪两块构件组成」→ 考构字结构（第三关破防的依据）
  play   「某字怎么打」→ 考规则掌握

干扰项从其它条目的同类字段里随机抽，且**不与正确答案重复**；
用固定 seed 保证同一份进度出同一套题，便于复盘与演示。
"""
import random

from retrieval import get_index

TYPE_LABEL = {"form": "字义", "comp": "构件", "play": "打法"}


def _pool(idx):
    rows = idx.rows
    forms, comps, plays = [], [], []
    for r in rows:
        m = r.get("meta") or {}
        if r.get("kind") == "wangyi" and m.get("meaning"):
            forms.append((r["char"], m["meaning"]))
        for c in (m.get("comps") or []):
            comps.append(c)
        if m.get("play"):
            plays.append((r["char"], m["play"]))
        elif m.get("tier_note"):
            plays.append((r["char"], m["tier_note"]))
    return forms, comps, plays


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def make_quiz(n=3, seed=20261104):
    import learner
    idx = get_index()
    forms, comps, plays = _pool(idx)
    rnd = random.Random(seed)

    # 候选顺序：答错过的字 → 没学过的字 → 其它（都打散，但错题优先）
    d = learner.load()
    wrong = [a["char"] for a in (d.get("attempts") or []) if not a.get("ok") and a.get("char")]
    learned = learner.learned_chars(d)
    # 只在课程层里出题：字形库有 1,168 字，但多数只有形/音/笔画，
    # 拿它出「本义/构件/打法」题会变成无意义的填空。
    rows = [r for r in idx.rows if r.get("char")
            and ((r.get("meta") or {}).get("course")
                 or r.get("kind") in learner.COURSE_KINDS)]
    by_char = {}
    for r in rows:
        by_char.setdefault(r["char"], r)

    def order(c):
        return (0 if c in wrong else (1 if c not in learned else 2))

    cand = sorted(by_char.values(), key=lambda r: order(r["char"]))
    # 同档内打散，避免永远考同几个字
    buckets = {}
    for r in cand:
        buckets.setdefault(order(r["char"]), []).append(r)
    cand = []
    for k in sorted(buckets):
        part = buckets[k][:]
        rnd.shuffle(part)
        cand.extend(part)

    TYPE_CYCLE = ["comp", "form", "play"]
    items, used_chars, ti = [], set(), 0
    for want in TYPE_CYCLE * max(1, n):
        if len(items) >= n:
            break
        picked = None
        for r in cand:
            ch = r["char"]
            if ch in used_chars:
                continue
            m = r.get("meta") or {}
            if want == "comp" and not (m.get("comps") and len(m["comps"]) >= 2):
                continue
            if want == "form" and not m.get("meaning"):
                continue
            if want == "play" and not (m.get("play") or m.get("tier_note")):
                continue
            picked = r
            break
        if not picked:
            continue
        r = picked
        ch = r["char"]
        m = r.get("meta") or {}
        if want == "comp":
            q = "「%s」由哪两块构件组成？" % ch
            right = " + ".join(m["comps"][:2])
            others = [c for c in _uniq(comps) if c not in m["comps"]]
            rnd.shuffle(others)
            opts = [right] + [" + ".join(others[i:i + 2]) for i in range(0, min(6, len(others)), 2)][:3]
        elif want == "form":
            q = "「%s」在王邑图卷里代表什么？" % ch
            right = m["meaning"]
            others = [x for c, x in forms if c != ch and x != right]
            rnd.shuffle(others)
            opts = [right] + _uniq(others)[:3]
        else:
            q = "打「%s」这一关，正确的破法是？" % ch
            right = m.get("play") or m.get("tier_note")
            others = [x for c, x in plays if c != ch and x != right]
            rnd.shuffle(others)
            opts = [right] + _uniq(others)[:3]

        opts = _uniq(opts)[:4]
        if len(opts) < 3:
            continue
        rnd.shuffle(opts)
        used_chars.add(ch)
        ti += 1
        items.append({
            "char": ch, "type": want, "type_label": TYPE_LABEL[want],
            "question": q, "options": opts,
            "answer": right, "answer_index": opts.index(right),
        })
    return {"items": items, "count": len(items), "seed": seed}


def grade(quiz, submitted):
    """submitted: [{"char":..., "choice": 索引}, ...] → 得分 + 逐题反馈 + 更新进度。"""
    import learner
    by_char = {q["char"]: q for q in quiz.get("items") or []}
    results, correct = [], 0
    # 读-改-写整体上锁：两个人同时交卷时，后写的那份不会覆盖掉先写的结果
    with learner.transaction() as d:
        attempts = d.setdefault("attempts", [])
        for s in submitted or []:
            q = by_char.get(s.get("char"))
            if not q:
                continue
            idx = s.get("choice")
            ok = (idx == q["answer_index"])
            correct += 1 if ok else 0
            results.append({
                "char": q["char"], "type": q["type"], "ok": ok,
                "your": q["options"][idx] if isinstance(idx, int) and 0 <= idx < len(q["options"]) else "未作答",
                "right": q["answer"],
                "why": _explain(q),
            })
            attempts.append({"char": q["char"], "ok": ok, "kind": q["type"]})

    total = len(results) or 1
    score = round(correct * 100 / total)
    if score == 100:
        advice = "全对。可以让他练更高一档：去第三关试「完美通关」，一阶一次都不挑错。"
    elif score >= 60:
        advice = "错的那几题集中在%s，回头把对应条目看一遍即可。" % _weak_types(results)
    else:
        advice = "基础还没稳，建议先看学习卡，再回来做一轮——错题会记进画像。"
    return {"score": score, "correct": correct, "total": len(results),
            "results": results, "advice": advice}


def _explain(q):
    if q["type"] == "comp":
        return "该字的构件就是它在第三关的可击破部位。"
    if q["type"] == "form":
        return "象形字画的正是那个实物，这是它的构形依据。"
    return "破法依据该字的字形结构，不是随便设的。"


def _weak_types(results):
    from collections import Counter
    c = Counter(r["type_label"] for r in results if not r["ok"])
    return "、".join(c.keys()) or "个别题"
