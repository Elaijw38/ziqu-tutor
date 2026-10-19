# -*- coding: utf-8 -*-
"""学情：进度存取 + 诊断。

诊断口径（每一句都能对上数据，不编"你很棒"这种话）：
  覆盖度   = 已学课程字数 / 课程字表字数
             （课程字表与 1,168 字的字形库分开：否则字库一扩，
              覆盖率就从 20% 掉到 2%，诊断失去意义）
  分片掌握 = 按王邑五片看各片完成比例，找出最弱的一片
  构件短板 = 从「合体字」条目里抽出构件（宀+豕 这种），
             统计哪些构件所在的字还没学 → 这是最有价值的诊断，
             因为第三关的破防部位就是构件
  错题优先 = attempts 里答错过的字，权重最高

进度文件放在 data/learner.json，结构故意做得和前端解耦：
    {"done": {"sky": ["日","月"], "life": ["家"]},
     "bossCleared": [0,1],
     "attempts": [{"char": "日", "ok": false, "kind": "form", "ts": 0}]}
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEARNER = os.path.join(ROOT, "data", "learner.json")

_EMPTY = {"done": {}, "bossCleared": [], "attempts": []}

# 服务是多线程的（ThreadingHTTPServer），而「读-改-写」不是原子操作：
# 两人同时交卷会互相覆盖。所有写路径必须走 transaction()。
_LOCK = threading.RLock()

# attempts 只用于算错题排行，保留最近若干条足够；无上限会随学期无限膨胀
MAX_ATTEMPTS = 500

# 最近一次读档失败的原因（半截文件/权限问题），供 /api/health 暴露，不再静默清零
LAST_LOAD_ERROR = ""


def load():
    global LAST_LOAD_ERROR
    try:
        d = json.loads(io.open(LEARNER, encoding="utf-8").read())
    except FileNotFoundError:
        d = {}
    except Exception as e:
        # 文件损坏时先留证据：直接返回空会让全部进度静默消失，事后无法追溯
        LAST_LOAD_ERROR = "%s: %s" % (type(e).__name__, e)
        try:
            shutil.copyfile(LEARNER, LEARNER + ".corrupt")
        except Exception:
            pass
        d = {}
    if not isinstance(d, dict):
        d = {}
    for k, v in _EMPTY.items():
        d.setdefault(k, [] if isinstance(v, list) else {})
    return d


def save(d):
    """原子写：先写同目录临时文件再 os.replace，避免留下半截 JSON。"""
    os.makedirs(os.path.dirname(LEARNER), exist_ok=True)
    with _LOCK:
        attempts = d.get("attempts")
        if isinstance(attempts, list) and len(attempts) > MAX_ATTEMPTS:
            d["attempts"] = attempts[-MAX_ATTEMPTS:]
        data = json.dumps(d, ensure_ascii=False, indent=1)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(LEARNER), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            # Windows 上目标文件被杀毒/索引短暂占用会失败，重试几次
            for i in range(5):
                try:
                    os.replace(tmp, LEARNER)
                    break
                except PermissionError:
                    if i == 4:
                        raise
                    time.sleep(0.05)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise


@contextlib.contextmanager
def transaction():
    """读-改-写全程持锁：并发交卷不会丢更新。"""
    with _LOCK:
        d = load()
        yield d
        save(d)


def learned_chars(d):
    out = set()
    for _zone, chars in (d.get("done") or {}).items():
        out.update(chars or [])
    for a in d.get("attempts") or []:
        if a.get("ok"):
            out.add(a.get("char"))
    out.discard(None)
    return out


COURSE_KINDS = ("wangyi", "boss", "codex")


def course_chars(rows):
    """课程字表：只含课程层，不含 1,168 字的通用字形库。

    学情分母必须用它。字形库是"能查多少字"的能力边界，不是教学进度。
    兼容旧数据：没有 meta.course 时按 kind 判断。
    """
    out = set()
    for r in rows:
        ch = r.get("char")
        if not ch:
            continue
        if (r.get("meta") or {}).get("course") or r.get("kind") in COURSE_KINDS:
            out.add(ch)
    return out


KIND_LABEL = {"comp": "构件分析", "form": "字义理解", "stroke": "字形笔画"}


def _kind_stats(attempts):
    """按题型统计正确率——学情里最有用的一层：错在哪类能力，而不是笼统对几个。"""
    st = {}
    for a in attempts or []:
        k = a.get("kind") or a.get("type") or "other"
        s = st.setdefault(k, {"total": 0, "ok": 0})
        s["total"] += 1
        if a.get("ok"):
            s["ok"] += 1
    out = []
    for k in ("comp", "form", "stroke", "other"):
        if k not in st:
            continue
        s = st[k]
        out.append({"kind": k, "label": KIND_LABEL.get(k, "其他"),
                    "total": s["total"], "ok": s["ok"],
                    "acc": round(s["ok"] * 100.0 / max(1, s["total"]), 1)})
    return out


def diagnose(idx):
    """返回可直接渲染的学习诊断。

    每个数字都要能对上口径：
      · 课程字覆盖 = 接触过的课程字 / 课程字表字数，只表示「见过」，不等于会做；
      · 练习正确率 = 答对次数 / 作答次数，来自实际作答，不是浏览行为；
      · 能力维度   = 按题型（构件分析 / 字义理解 / 字形笔画）分别算正确率；
      · 待复习     = 至少答错过一次的字。
    """
    from retrieval import get_kb_meta
    d = load()
    rows = idx.rows
    meta = get_kb_meta()

    course = course_chars(rows)
    if not course:                       # 兜底：老知识库没有课程标记
        course = {r["char"] for r in rows if r.get("char")}
    lexicon = {r["char"] for r in rows if r.get("char")}
    learned = learned_chars(d) & course
    coverage = round(len(learned) / max(1, len(course)) * 100, 1)

    attempts = d.get("attempts") or []
    n_att = len(attempts)
    n_ok = sum(1 for a in attempts if a.get("ok"))
    accuracy = round(n_ok * 100.0 / n_att, 1) if n_att else 0.0
    by_kind = _kind_stats(attempts)
    recent_n = min(10, n_att)
    recent_acc = (round(sum(1 for a in attempts[-recent_n:] if a.get("ok"))
                        * 100.0 / recent_n, 1) if recent_n else 0.0)

    # 字义主题分布：只作「知识面」看，不再当游戏地图进度
    zones = []
    for zid, zname in meta["zones"]:
        zchars = meta["zone_chars"].get(zid, [])
        got = [c for c in zchars if c in learned]
        zones.append({"id": zid, "name": zname, "done": len(got),
                      "total": len(zchars),
                      "pct": round(len(got) * 100 / max(1, len(zchars)), 1)})
    zones_sorted = sorted([z for z in zones if z["total"]], key=lambda z: z["pct"])
    weakest_zone = zones_sorted[0] if zones_sorted else None

    # 错题
    wrong = {}
    for a in attempts:
        if not a.get("ok") and a.get("char"):
            wrong[a["char"]] = wrong.get(a["char"], 0) + 1
    wrong_top = sorted(wrong.items(), key=lambda kv: -kv[1])[:5]

    # 构件短板：从答错的字反查构件。
    # 旧算法是「没学过的字里有这个构件」，那只是没学到，不叫短板。
    weak_comps = []
    if wrong:
        for comp, chars in meta["comp_chars"].items():
            hit = [c for c in chars if c in wrong]
            if hit:
                weak_comps.append({"comp": comp, "chars": hit,
                                   "times": sum(wrong[c] for c in hit)})
        weak_comps.sort(key=lambda x: (-x["times"], -len(x["chars"])))
        weak_comps = weak_comps[:4]

    # 建议：按证据强弱排，不按模板排
    suggestions = []
    if wrong_top:
        top = wrong_top[:3]
        suggestions.append("「%s」累计答错 %d 次，先回看这几个字的字形与构形，比继续刷新题有效。"
                           % ("」「".join(c for c, _ in top), sum(n for _, n in top)))
    if n_att >= 5:
        cand = [k for k in by_kind if k["total"] >= 3]
        if cand:
            wk = min(cand, key=lambda k: k["acc"])
            if wk["acc"] < 80:
                suggestions.append("%s正确率 %.0f%%（%d/%d）是目前最薄的一环，"
                                   "下一轮练习集中考这一类。"
                                   % (wk["label"], wk["acc"], wk["ok"], wk["total"]))
    if weakest_zone and weakest_zone["pct"] < 100:
        suggestions.append("课程字表按字义分「%s」类，这一类你还差 %d 个字，可以按类往下补。"
                           % (weakest_zone["name"],
                              weakest_zone["total"] - weakest_zone["done"]))
    if n_att == 0:
        suggestions.insert(0, "还没有作答记录——上面的覆盖只是「见过」，不等于会做。"
                              "先做一轮随堂练习，正确率才有参考价值。")
    elif coverage >= 80 and accuracy >= 85:
        suggestions.append("覆盖 %s%%、正确率 %s%%，可以转到易混字辨析或整字释读上练。"
                           % (coverage, accuracy))
    if not suggestions:
        suggestions.append("记录还很少，再问几个字或做一轮练习，我就能给出更准的建议。")

    if n_att == 0:
        level = "未开始"
    elif coverage < 5:
        level = "起步"
    elif coverage < 30:
        level = "入门"
    elif coverage < 70:
        level = "进阶"
    else:
        level = "熟练"

    return {
        "coverage": coverage,
        "level": level,
        "learned": len(learned),
        "total_chars": len(course),
        "lexicon_chars": len(lexicon),
        "attempts_total": n_att,
        "accuracy": accuracy,
        "recent": {"n": recent_n, "acc": recent_acc},
        "by_kind": by_kind,
        "zones": zones,
        "weakest_zone": weakest_zone,
        "weak_comps": weak_comps,
        "wrong_top": [{"char": c, "times": n} for c, n in wrong_top],
        "suggestions": suggestions,
    }
