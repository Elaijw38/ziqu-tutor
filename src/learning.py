# -*- coding: utf-8 -*-
"""学情诊断：四库联动的那一层（只读，不改任何数据）。

四库怎么串起来
  course_id           ← data/curriculum.json（课程知识点库）
  knowledge_point_id  ← 同上；题目生成时写进 quiz_items.kp_id，作答时写进 attempts.kp_id
  item_id             ← quiz_items 主键，attempts.item_id 指向它
  attempt_id          ← attempts 主键，错因的证据引用它

诊断只做两件事：
  1. 按知识点统计作答数 / 正确数 / 错误数，并按阈值给状态（阈值全在 diagnosis.json）；
  2. 把错题按规则归到「错因」，每条错因必须挂上具体 attempt 作为证据；
     规则匹配不上就写「暂无法归因」，不猜。

不参加诊断的输入：聊天内容、模型印象、没有作答的知识点。
样本不足时状态就是「证据不足」，不给掌握结论。
"""
import re
import time

import curriculum

_MONTH_DAY = "%m-%d %H:%M"


def _L():
    import learner
    return learner


# ---------------- 知识点可用题量（判断「本课暂无题目」） ----------------

def kp_coverage(idx):
    """每个知识点在本课里能出多少字的题。0 表示现有题库覆盖不到。

    这是「本课有多少可用题源」，不是学生进度——页面用它区分
    「你不会」和「我们还没出这类的题」。
    """
    rows = idx.rows
    course = [r for r in rows if r.get("char") and
              ((r.get("meta") or {}).get("course")
               or r.get("kind") in ("wangyi", "boss", "codex"))]
    course_chars = {r["char"] for r in course}
    # 笔画数只在 glyph 条目里；课程层的字要跟 glyph 取交集才算「有题可出」
    stroke_chars = {r["char"] for r in rows
                    if r.get("kind") == "glyph" and r.get("char")
                    and isinstance((r.get("meta") or {}).get("strokes"), int)
                    and (r.get("meta") or {})["strokes"] > 0} & course_chars
    by_type = {"form": set(), "comp": set(), "stroke": stroke_chars}
    for r in course:
        m = r.get("meta") or {}
        ch = r["char"]
        if r.get("kind") == "wangyi" and m.get("meaning"):
            by_type["form"].add(ch)
        if m.get("comps") and len(m["comps"]) >= 2:
            by_type["comp"].add(ch)
        if isinstance(m.get("strokes"), int) and m["strokes"] > 0:
            by_type["stroke"].add(ch)
    out = {}
    for kp in curriculum.knowledge_points():
        chars = set()
        for t in kp.get("question_types") or []:
            chars |= by_type.get(t, set())
        out[kp["knowledge_point_id"]] = len(chars)
    return out


# ---------------- 错因归因 ----------------

_NUM = re.compile(r"(\d+)")


def _stroke_delta(a):
    m1 = _NUM.search(a.get("correct") or "")
    m2 = _NUM.search(a.get("chosen") or "")
    if not (m1 and m2):
        return None
    return abs(int(m1.group(1)) - int(m2.group(1)))


def _matches(rule, a):
    ap = rule.get("applies") or {}
    if ap.get("wrong_only") and a.get("ok"):
        return False
    # 没有保存「选了什么」的旧记录，归不到具体错因——宁可不归因，也不硬套
    if not (a.get("chosen") or "").strip():
        return False
    types = ap.get("types") or []
    if types and (a.get("kind") not in types):
        return False
    variant = ap.get("variant")
    if variant:
        d = _stroke_delta(a)
        if d is None:
            return False
        if variant == "near" and d != 1:
            return False
        if variant == "far" and d < 2:
            return False
    return True


def attribute(a):
    """返回 (cause_dict, matched: bool)。匹配不上就是「暂无法归因」。"""
    for rule in curriculum.cause_rules():
        if _matches(rule, a):
            return rule, True
    return curriculum.unattributed(), False


# ---------------- 状态判定（阈值全部来自配置） ----------------

def status_of(answered, ok, has_items):
    min_ev = curriculum.threshold("min_evidence", 3)
    solid = curriculum.threshold("solid_evidence", 5)
    mastery = curriculum.threshold("mastery_acc", 80)
    weak = curriculum.threshold("weak_acc", 60)
    acc = round(ok * 100.0 / answered, 1) if answered else 0.0

    if not has_items:
        return "no_items", acc, "none"
    if answered == 0:
        return "insufficient", acc, "none"
    if answered < min_ev:
        return "insufficient", acc, "limited"
    if answered < solid:
        return ("limited_weak" if acc < weak else "limited_ok"), acc, "limited"
    if acc < weak:
        return "weak", acc, "solid"
    if acc >= mastery:
        return "emerging", acc, "solid"
    return "steady", acc, "solid"


def _status_text(key, **kw):
    meta = curriculum.status_meta(key)
    return {
        "key": key,
        "label": meta.get("label") or key,
        "hint": curriculum.fill(meta.get("hint") or "", **kw),
    }


# ---------------- 主入口 ----------------

def diagnose(idx, vid="", quiz_id="", L=None):
    L = L or _L()
    base = L.diagnose(idx, vid)          # 旧字段全部保留，页面/模型都可继续用
    rows = idx.rows
    course = L.course_chars(rows) or {r["char"] for r in rows if r.get("char")}
    cov = kp_coverage(idx)
    kps = curriculum.knowledge_points()
    dims = curriculum.curriculum().get("dimensions") or []

    attempts = L.list_attempts(vid, limit=2000)
    # 本次练习：显式指定 > 最近一次有作答的套题 > 最近 N 次
    recent_n = int(curriculum.threshold("recent_n", 10))
    this_quiz = quiz_id or ""
    if not this_quiz:
        last = L.latest_quiz(vid)
        if last and any(a.get("quiz_id") == last for a in attempts):
            this_quiz = last
    if this_quiz:
        scoped = [a for a in attempts if a.get("quiz_id") == this_quiz]
        range_type = "quiz"
    elif attempts:
        scoped = attempts[-recent_n:]
        range_type = "recent"
    else:
        scoped = []
        range_type = "none"

    total_items = L.quiz_total(this_quiz) if this_quiz else len(scoped)
    if range_type == "quiz":
        range_text = "本次练习 · %d/%d 题" % (len(scoped), total_items or len(scoped))
    elif range_type == "recent":
        range_text = "最近 %d 次作答（没有按套题记录）" % len(scoped)
    else:
        range_text = "还没有作答记录"

    seeded = bool(base.get("seeded")) or any(a.get("seeded") for a in attempts)
    at = max((a.get("ts") or 0) for a in scoped) if scoped else 0
    if range_type == "quiz":
        basis = ("概览只描述这一次练习（%d 题）；知识点统计用累计 %d 题——两者范围不同，别相加。"
                 % (len(scoped), len(attempts)))
    elif range_type == "recent":
        basis = ("概览只描述最近 %d 次；下方知识点统计用累计 %d 题——两者范围不同，别相加。"
                 % (len(scoped), len(attempts)))
    else:
        basis = "只统计本浏览器的实际作答与评分结果；聊天内容不参与诊断。"

    # ---- 按知识点统计（累计证据；本次练习只影响概览与提示口径） ----
    kp_rows = []
    for kp in kps:
        kid = kp.get("knowledge_point_id")
        mine = [a for a in attempts if a.get("kp_id") == kid]
        ok = sum(1 for a in mine if a.get("ok"))
        answered = len(mine)
        has_items = bool(kp.get("has_items")) and cov.get(kid, 0) > 0
        st_key, acc, level = status_of(answered, ok, has_items)
        meta = _status_text(st_key, answered=answered, ok=ok, wrong=answered - ok,
                            acc=("%g" % acc), min=curriculum.threshold("min_evidence", 3),
                            kp=kp.get("name") or kid)
        in_this = [a for a in scoped if a.get("kp_id") == kid]
        kp_rows.append({
            "knowledge_point_id": kid,
            "name": kp.get("name") or kid,
            "dimension_id": kp.get("dimension_id") or "",
            "dimension_name": curriculum.dimension_name(kp.get("dimension_id")),
            "goal": kp.get("goal") or "",
            "note": kp.get("note") or "",
            "has_items": has_items,
            "available_chars": cov.get(kid, 0),
            "answered": answered, "ok": ok, "wrong": answered - ok,
            "accuracy": acc, "evidence_level": level,
            "status_key": st_key, "status": meta["label"], "status_hint": meta["hint"],
            "in_this_practice": len(in_this),
            "wrong_chars": _uniq([a["char"] for a in mine if not a.get("ok") and a.get("char")]),
        })

    # ---- 本次错题明细（带题干、你选/正确、判断依据、归因） ----
    # 有「本次练习」就只列本次的错题（本次全对就是空，不拿旧错题凑数）；
    # 没有按套题记录时，列最近几次的错题，并在卡片上标出时间。
    if range_type == "quiz":
        wrong_scope = [a for a in scoped if not a.get("ok")]
    else:
        wrong_scope = [a for a in attempts if not a.get("ok")][-8:]
    qcache = {}

    def item_of(a):
        qid = a.get("quiz_id") or ""
        if not qid or not a.get("item_id"):
            return {}
        if qid not in qcache:
            q = L.get_quiz(qid) or {}
            qcache[qid] = {it.get("item_id"): it for it in (q.get("items") or [])}
        return qcache[qid].get(a.get("item_id")) or {}

    wrong_items = []
    max_wrong = int(curriculum.threshold("max_wrong_items", 8))
    for a in reversed(wrong_scope):
        if len(wrong_items) >= max_wrong:
            break
        it = item_of(a)
        cause, matched = attribute(a)
        why = curriculum.fill(cause.get("why") or "", right=a.get("correct") or "—",
                              your=a.get("chosen") or "—")
        wrong_items.append({
            "attempt_id": a.get("attempt_id") or "",
            "item_id": a.get("item_id") or "",
            "quiz_id": a.get("quiz_id") or "",
            "char": a.get("char") or "",
            "knowledge_point_id": a.get("kp_id") or "",
            "knowledge_point": curriculum.kp_name(a.get("kp_id")),
            "question": it.get("question") or "",
            "kind": a.get("kind") or "",
            "your": a.get("chosen") or "",
            "right": a.get("correct") or "",
            "why": why,
            "cause_id": cause.get("cause_id") or "",
            "cause": cause.get("name") or "暂无法归因",
            "attributed": matched,
            "ts": a.get("ts") or 0,
            "legacy": not a.get("item_id"),
        })

    # ---- 错因汇总：每条都挂证据 ----
    causes = {}
    for a in attempts:
        if a.get("ok"):
            continue
        cause, matched = attribute(a)
        cid = cause.get("cause_id") or "cause.unattributed"
        c = causes.setdefault(cid, {
            "cause_id": cid, "name": cause.get("name") or "暂无法归因",
            "why": curriculum.fill(cause.get("why") or "",
                                   right=a.get("correct") or "—",
                                   your=a.get("chosen") or "—"),
            "hint": cause.get("hint") or "", "drill": cause.get("drill") or "",
            "attributed": matched, "count": 0, "evidence": [], "kp_ids": [],
        })
        c["count"] += 1
        if a.get("kp_id") and a["kp_id"] not in c["kp_ids"]:
            c["kp_ids"].append(a["kp_id"])
        if len(c["evidence"]) < 5:
            c["evidence"].append({
                "attempt_id": a.get("attempt_id") or "",
                "char": a.get("char") or "",
                "your": a.get("chosen") or "",
                "right": a.get("correct") or "",
                "ts": a.get("ts") or 0,
            })
    cause_list = sorted(causes.values(), key=lambda c: (-c["count"], c["name"]))
    cause_list = cause_list[:int(curriculum.threshold("max_causes", 4))]

    # ---- 可执行建议：一条针对最该动的知识点 ----
    actions = []
    weak_kps = sorted([k for k in kp_rows if k["status_key"] in ("weak", "limited_weak")],
                      key=lambda k: (k["accuracy"], -k["wrong"]))
    insuff = [k for k in kp_rows if k["status_key"] == "insufficient"]
    emerging = [k for k in kp_rows if k["status_key"] in ("emerging", "limited_ok")]
    no_items = [k for k in kp_rows if k["status_key"] == "no_items"]

    if not attempts:
        actions.append({"text": curriculum.action("no_record"), "cta": "quiz",
                        "knowledge_point_id": "", "knowledge_point": "", "n": 3})
    for k in weak_kps[:1]:
        # 只取这个知识点上、真正归因成功的错因；「暂无法归因」不能拿来当建议依据
        cands = [x for x in cause_list
                 if x.get("attributed") and k["knowledge_point_id"] in (x.get("kp_ids") or [])]
        c = cands[0] if cands else None
        text = (c.get("hint") if c and c.get("hint") else k["status_hint"])
        actions.append({"text": text + "（" + k["name"] + "）", "cta": "practice",
                        "knowledge_point_id": k["knowledge_point_id"],
                        "knowledge_point": k["name"], "n": 3})
    for k in insuff[:1]:
        actions.append({
            "text": curriculum.action("insufficient", n=3, kp=k["name"]),
            "cta": "practice", "knowledge_point_id": k["knowledge_point_id"],
            "knowledge_point": k["name"], "n": 3})
    if weak_kps:
        pass
    elif emerging and not insuff:
        nxt = (no_items[0] if no_items else None)
        if nxt:
            actions.append({"text": curriculum.action("emerging", next=nxt["name"]),
                            "cta": "", "knowledge_point_id": "", "knowledge_point": "", "n": 0})
    if not actions and attempts:
        actions.append({"text": "现有证据还看不出稳定倾向，再做一组练习即可更新诊断。",
                        "cta": "quiz", "knowledge_point_id": "", "knowledge_point": "", "n": 3})
    actions = actions[:3]

    return {
        "ok": True,
        "course": {
            "course_id": curriculum.course_id(),
            "title": curriculum.curriculum().get("course_title") or "",
            "goals": curriculum.curriculum().get("goals") or [],
            "dimensions": [{"dimension_id": d.get("dimension_id"),
                            "name": d.get("name"), "note": d.get("note") or ""} for d in dims],
        },
        "overview": {
            "range_type": range_type,
            "range_text": range_text,
            "quiz_id": this_quiz,
            "answered": len(scoped),
            "total_items": total_items,
            "correct": sum(1 for a in scoped if a.get("ok")),
            "at": at,
            "at_text": time.strftime(_MONTH_DAY, time.localtime(at)) if at else "",
            "seeded": seeded,
            "basis": basis,
        },
        "knowledge_points": kp_rows,
        "wrong_items": wrong_items,
        "causes": cause_list,
        "actions": actions,
        # ---- 以下为兼容旧页面/旧调用保留的字段，口径与原来一致 ----
        **{k: base.get(k) for k in
           ("coverage", "level", "learned", "total_chars", "lexicon_chars",
            "attempts_total", "accuracy", "recent", "by_kind", "weak_comps",
            "wrong_top", "suggestions", "scope", "seeded")},
    }


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out
