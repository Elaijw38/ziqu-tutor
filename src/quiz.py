# -*- coding: utf-8 -*-
"""出题与评阅（四库里的「题目与评分库」出口）。

题目**全部由知识库字段生成**，不预设题库——所以知识库一扩，题目跟着变。
三种题型，分别对应三个知识点：
  form   「某字代表什么」      → kp.form.pictograph（象形字辨识）
  comp   「某字由哪两个构件组成」→ kp.comp.split（构件拆分）
  stroke 「甲骨字形标注几画」   → kp.glyph.strokes（甲骨字形笔画）

每题在生成时就带上 item_id / knowledge_point_id / difficulty / source，并存进
SQLite 的 quiz_items 表；评阅时以服务端存的答案为准，客户端回传的题目不作数。

知识点与题型的对应、难度标签都放在 data/curriculum.json，改配置不用改这里。
"""
import random
import time
import uuid

import curriculum
from retrieval import get_index

TYPE_LABEL = {"form": "字义", "comp": "构件", "stroke": "笔画"}


def _pool(idx):
    rows = idx.rows
    forms, comps, plays, strokes = [], [], [], []
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
        n = m.get("strokes")
        if r.get("kind") == "glyph" and r.get("char") and isinstance(n, int) and n > 0:
            strokes.append((r["char"], n))
    return forms, comps, plays, strokes


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def new_quiz_id():
    # 短、可读、够唯一：qz + 秒级时间 + 4 位随机
    return "qz%s%s" % (str(int(time.time()))[-6:], uuid.uuid4().hex[:4])


def kp_types(kp_id):
    if not kp_id:
        return None
    k = curriculum.kp_index().get(kp_id) or {}
    return list(k.get("question_types") or [])


def make_quiz(n=3, seed=20261104, vid="", kp_id=""):
    """出题。kp_id 非空时只出该知识点的题型（用于「针对这个知识点再练」）。"""
    import learner
    idx = get_index()
    forms, comps, plays, strokes = _pool(idx)
    rnd = random.Random(seed)
    # 一个字的甲骨字形可能有多个写法，笔画数以第一条标注为准
    stroke_by_char = {}
    for c, cnt in strokes:          # 别用 n：n 是题量参数，被覆盖会出多套题
        stroke_by_char.setdefault(c, cnt)

    allowed = kp_types(kp_id)
    if kp_id and not allowed:
        # 该知识点还没有配套题型：明确返回空，不拿别的题凑数
        return {"quiz_id": "", "items": [], "count": 0, "seed": seed,
                "kp_id": kp_id, "error": "该知识点暂无对应题目"}

    # 候选顺序：答错过的字 → 没学过的字 → 其它（都打散，但错题优先）
    # 只读当前访客的记录：别人答错过的字不该优先推给你
    d = learner.load(vid)
    wrong = [a["char"] for a in (d.get("attempts") or [])
             if not a.get("ok") and a.get("char")]
    if kp_id:
        # 本知识点错过的字排最前
        kp_chars = {a.get("char") for a in learner.list_attempts(vid, limit=500)
                    if a.get("kp_id") == kp_id and not a.get("ok") and a.get("char")}
        wrong = [c for c in wrong if c in kp_chars] or wrong
    learned = learner.learned_chars(d)
    # 只在课程层里出题：字形库有 1,168 字，但多数只有形/音/笔画，
    # 拿它出「本义/构件」题会变成无意义的填空。
    rows = [r for r in idx.rows if r.get("char")
            and ((r.get("meta") or {}).get("course")
                 or r.get("kind") in learner.COURSE_KINDS
                 # 构件是逐条核对过的，有构件就该能出构件题
                 or len((r.get("meta") or {}).get("comps") or []) >= 2)]
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

    # 指定知识点时只循环该知识点的题型；否则三种轮转
    TYPE_CYCLE = allowed or ["comp", "form", "stroke"]
    qid = new_quiz_id()
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
            if want == "stroke" and ch not in stroke_by_char:
                continue
            picked = r
            break
        if not picked:
            continue
        r = picked
        ch = r["char"]
        m = r.get("meta") or {}
        if want == "comp":
            q = "「%s」由哪两个构件组成？" % ch
            right = " + ".join(m["comps"][:2])
            others = [c for c in _uniq(comps) if c not in m["comps"]]
            rnd.shuffle(others)
            opts = [right] + [" + ".join(others[i:i + 2]) for i in range(0, min(6, len(others)), 2)][:3]
        elif want == "form":
            q = "「%s」在甲骨文里像什么、代表什么？" % ch
            right = m["meaning"]
            others = [x for c, x in forms if c != ch and x != right]
            rnd.shuffle(others)
            opts = [right] + _uniq(others)[:3]
        else:
            cnt = stroke_by_char[ch]
            q = "甲骨字形「%s」标注为几画？（按甲骨字形计，不是现代通行笔画）" % ch
            right = "%d 画" % cnt
            nums = [x for x in (cnt - 2, cnt - 1, cnt + 1, cnt + 2, cnt + 3) if x > 0]
            rnd.shuffle(nums)
            opts = [right] + ["%d 画" % x for x in nums[:3]]

        opts = _uniq(opts)[:4]
        if len(opts) < 3:
            continue
        rnd.shuffle(opts)
        used_chars.add(ch)
        ti += 1
        kp = curriculum.kp_for_type(want)
        diff_key, diff_label = curriculum.difficulty_of(want)
        items.append({
            "item_id": "%s.%02d" % (qid, ti),
            "quiz_id": qid,
            "kp_id": kp, "kp_name": curriculum.kp_name(kp),
            "difficulty": diff_key, "difficulty_label": diff_label,
            "char": ch, "type": want, "type_label": TYPE_LABEL[want],
            "question": q, "options": opts,
            "answer": right, "answer_index": opts.index(right),
            "source": r.get("source") or "",
        })
    if items:
        learner.save_quiz(qid, vid, items)
    return {"quiz_id": qid if items else "", "items": items, "count": len(items),
            "seed": seed, "kp_id": kp_id}


def grade(quiz, submitted, vid="", quiz_id=""):
    """submitted: [{"item_id"/"char":..., "choice": 索引}] → 得分 + 逐题反馈 + 写证据。

    有 quiz_id 且服务端还存着这套题时，**以服务端题目与答案为准**：
    客户端回传的 answer_index 一律不看（否则改一下请求就能拿满分）。
    vid 是当前访客：只写自己的记录。
    """
    import learner
    srv = learner.get_quiz(quiz_id)
    if srv:
        quiz = srv
    items = quiz.get("items") or []
    by_item = {q.get("item_id"): q for q in items if q.get("item_id")}
    by_char = {q["char"]: q for q in items if q.get("char")}
    results, correct = [], 0
    # 读-改-写整体上锁：两个人同时交卷时，后写的那份不会覆盖掉先写的结果
    with learner.transaction(vid) as d:
        attempts = d.setdefault("attempts", [])
        # 证据已经写进 attempts 表：标记版本，避免 diagnose 时又被迁移一遍造成重复计数
        d["evidence_version"] = 2
        for s in submitted or []:
            q = by_item.get(s.get("item_id")) or by_char.get(s.get("char"))
            if not q:
                continue
            idx = s.get("choice")
            ok = (idx == q.get("answer_index"))
            chosen = (q["options"][idx] if isinstance(idx, int)
                      and 0 <= idx < len(q["options"]) else "")
            correct += 1 if ok else 0
            kp = q.get("kp_id") or curriculum.kp_for_type(q.get("type"))
            results.append({
                "attempt_id": "",           # 由服务端写入后回填
                "item_id": q.get("item_id") or "",
                "quiz_id": quiz_id or q.get("quiz_id") or "",
                "kp_id": kp, "kp_name": curriculum.kp_name(kp),
                "char": q["char"], "type": q["type"],
                "type_label": TYPE_LABEL.get(q["type"], q.get("type", "")),
                "ok": ok, "your": chosen or "未作答", "right": q["answer"],
                "why": _explain(q), "source": q.get("source") or "",
            })
            # ts 用于学情里的「最近一段时间」；JSON 里的 attempts 仍保留，
            # 出题时的「答错优先」直接读它，代价很小。
            rec = {"attempt_id": "at" + uuid.uuid4().hex[:16],
                   "quiz_id": quiz_id or q.get("quiz_id") or "",
                   "item_id": q.get("item_id") or "", "kp_id": kp,
                   "char": q["char"], "kind": q["type"], "ok": ok,
                   "chosen": chosen, "correct": q["answer"],
                   "ts": int(time.time()), "seeded": bool(d.get("seeded"))}
            attempts.append({"char": q["char"], "ok": ok, "kind": q["type"],
                             "ts": rec["ts"]})
            learner.stage_attempt(d, rec)
            results[-1]["attempt_id"] = rec["attempt_id"]

    total = len(results) or 1
    score = round(correct * 100 / total)
    if score == 100:
        advice = "全对。可以换更难的一档：挑几个易混字做辨析。"
    elif score >= 60:
        advice = "错的那几题集中在%s，回头把对应条目看一遍即可。" % _weak_types(results)
    else:
        advice = "基础还没稳，建议先看知识库条目，再回来做一轮——错题会记进学习记录。"
    return {"quiz_id": quiz_id, "score": score, "correct": correct, "total": len(results),
            "results": results, "advice": advice, "by_kp": _by_kp(results)}


def _by_kp(results):
    """按知识点小计：页面直接显示，不再由前端自己算。"""
    out = {}
    for r in results:
        k = out.setdefault(r["kp_id"], {"kp_id": r["kp_id"], "kp_name": r["kp_name"],
                                        "total": 0, "ok": 0})
        k["total"] += 1
        if r["ok"]:
            k["ok"] += 1
    return list(out.values())


def _explain(q):
    if q["type"] == "comp":
        return "构件拆分看的是字形内部结构，不是按笔画随意切开的。"
    if q["type"] == "form":
        return "象形字画的正是那个实物，这是它的构形依据。"
    return "甲骨字形的笔画数与现代通行笔画不一定相同，本题按数据集标注计。"


def _weak_types(results):
    from collections import Counter
    c = Counter(r["type_label"] for r in results if not r["ok"])
    return "、".join(c.keys()) or "个别题"
