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


def diagnose(idx):
    """返回可直接渲染的诊断对象。"""
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

    # 分片掌握
    zones = []
    for zid, zname in meta["zones"]:
        zchars = meta["zone_chars"].get(zid, [])
        got = [c for c in zchars if c in learned]
        zones.append({"id": zid, "name": zname, "done": len(got),
                      "total": len(zchars),
                      "pct": round(len(got) * 100 / max(1, len(zchars)), 1)})
    zones_sorted = sorted([z for z in zones if z["total"]], key=lambda z: z["pct"])
    weakest_zone = zones_sorted[0] if zones_sorted else None

    # 构件短板：构件所在字若没学，记一笔
    comps = {}
    for comp, chars in meta["comp_chars"].items():
        miss = [c for c in chars if c not in learned]
        if miss:
            comps[comp] = {"total": len(chars), "missing": miss}
    weak_comps = sorted(comps.items(), key=lambda kv: -len(kv[1]["missing"]))[:4]

    # 错题
    wrong = {}
    for a in d.get("attempts") or []:
        if not a.get("ok") and a.get("char"):
            wrong[a["char"]] = wrong.get(a["char"], 0) + 1
    wrong_top = sorted(wrong.items(), key=lambda kv: -kv[1])[:5]

    suggestions = []
    if wrong_top:
        suggestions.append("先把答错过的「%s」再过一遍，它们最值得优先复习。"
                           % "」「".join([c for c, _ in wrong_top[:3]]))
    if weakest_zone and weakest_zone["pct"] < 100:
        suggestions.append("「%s」这片只学了 %d/%d，从它入手最划算。"
                           % (weakest_zone["name"], weakest_zone["done"], weakest_zone["total"]))
    if weak_comps:
        c0, i0 = weak_comps[0]
        suggestions.append("构件「%s」还没掌握（%d 个字里差 %d 个），"
                           "而构件拆分正是辨形的基础，建议优先补。"
                           % (c0, i0["total"], len(i0["missing"])))
    if coverage >= 80:
        suggestions.append("覆盖度已经 %s%%，可以开始练更难的辨析题，试着一次不错。" % coverage)
    if not suggestions:
        suggestions.append("还没有学习记录。先去问几个字形，或做一轮练习，我就能给出学习建议。")

    level = "未入门" if coverage < 5 else ("入门" if coverage < 30 else
            ("进阶" if coverage < 70 else ("熟练" if coverage < 95 else "全覆盖")))

    return {
        "coverage": coverage,
        "level": level,
        "learned": len(learned),
        "total_chars": len(course),
        "lexicon_chars": len(lexicon),
        "zones": zones,
        "weakest_zone": weakest_zone,
        "weak_comps": [{"comp": c, "total": v["total"], "missing": v["missing"]} for c, v in weak_comps],
        "wrong_top": [{"char": c, "times": n} for c, n in wrong_top],
        "suggestions": suggestions,
    }
