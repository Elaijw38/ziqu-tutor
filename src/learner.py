# -*- coding: utf-8 -*-
"""学情：按访客分开的进度存取 + 诊断。

诊断口径（每一句都能对上数据，不编"你很棒"这种话）：
  课程字覆盖 = 接触过的课程字 / 课程字表字数
               （课程字表与 1,179 字的字形库分开：否则字库一扩，
                覆盖率就从 20% 掉到 2%，诊断失去意义）
  练习正确率 = 答对次数 / 作答次数，只来自实际作答，不是浏览行为
  能力维度   = 按题型（构件分析 / 字义理解 / 字形笔画）分别算正确率
  待复习     = 至少答错过一次的字

存储：SQLite（sqlite3 是标准库，仍然零依赖），单文件 data/learners.db

    learners(vid TEXT PRIMARY KEY, data TEXT, updated REAL)
    data 里存的就是原来的字典结构，字段随功能扩展不用改表：
        {"done": {"sky": ["日"]}, "bossCleared": [0],
         "attempts": [{"char": "日", "ok": false, "kind": "form", "ts": 0}],
         "seeded": true/false}

为什么要分人：以前所有访客共写一份 learner.json，A 同学交的卷会记到 B 同学
头上，学情页显示的其实是"这台机器上所有人的混合体"，不能当学习证据用。
现在每个浏览器拿一个随机 vid（HttpOnly cookie，不含任何个人信息），各存各的。

为什么不每人一个 JSON 文件：一个班几十人就会散成一地小文件，备份、统计、
清理都麻烦；SQLite 自带事务，并发交卷由 BEGIN IMMEDIATE 保证不丢更新。
"""
import contextlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DATA = os.path.join(ROOT, "data")
DB = os.path.join(DATA, "learners.db")
# 旧的单文件学情：不再写入，只在建库时导入成「示例」，供演示时一键载入
LEGACY = os.path.join(DATA, "learner.json")
CORRUPT_DIR = os.path.join(DATA, "corrupt")

# 没有 cookie 的调用（curl、脚本、被禁用 cookie 的浏览器）落在这个桶里
DEFAULT_VID = "local"
# 示例学情：由旧的 learner.json 导入，只能被「载入示例」复制，不参与真实统计
DEMO_VID = "demo"

_EMPTY = {"done": {}, "bossCleared": [], "attempts": []}

# 服务是多线程的（ThreadingHTTPServer）；跨进程交给 SQLite 的写锁，
# 进程内再串行一层，避免同一 DB 上大量锁等待。
_LOCK = threading.RLock()

# attempts 只用于算错题排行，保留最近若干条足够；无上限会随学期无限膨胀
MAX_ATTEMPTS = 500

# 最近一次读档失败的原因（坏行/权限问题），供 /api/health 暴露，不再静默清零
LAST_LOAD_ERROR = ""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    vid     TEXT PRIMARY KEY,
    data    TEXT NOT NULL,
    updated REAL NOT NULL DEFAULT 0
);
"""

# 已经建过表的库路径，避免每次连接都跑一遍 DDL
_READY = set()


# ---------------- 访客标识 ----------------

_VID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_vid():
    """随机访客标识：不含任何个人信息，只是这一份学情的钥匙。"""
    return uuid.uuid4().hex


def is_valid_vid(v):
    return bool(_VID_RE.match(v or ""))


def normalize_vid(vid):
    """只接受服务端签发过的格式；其它一律落到本机桶，避免任意字符串建行。

    两个保留桶例外：本机兜底（local）与示例（demo）——它们不是 cookie 值。
    """
    vid = (vid or "").strip()
    if vid in (DEFAULT_VID, DEMO_VID):
        return vid
    return vid if is_valid_vid(vid) else DEFAULT_VID


# ---------------- 连接与读写 ----------------

def _connect():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=8000")
    if DB not in _READY:
        conn.executescript(_SCHEMA)
        _import_legacy(conn)
        _READY.add(DB)
    return conn


def _import_legacy(conn):
    """把旧的单文件学情导入 demo 桶——只导一次，之后该文件不再参与写入。"""
    if not os.path.isfile(LEGACY):
        return
    n = conn.execute("SELECT COUNT(*) FROM learners WHERE vid=?", (DEMO_VID,)).fetchone()[0]
    if n:
        return
    try:
        d = json.loads(open(LEGACY, encoding="utf-8").read())
        if not isinstance(d, dict):
            return
    except Exception as e:
        global LAST_LOAD_ERROR
        LAST_LOAD_ERROR = "legacy: %s: %s" % (type(e).__name__, e)
        return
    d = _norm(d)
    d["seeded"] = True
    conn.execute("INSERT OR REPLACE INTO learners(vid,data,updated) VALUES(?,?,?)",
                 (DEMO_VID, json.dumps(d, ensure_ascii=False), time.time()))


def _fresh():
    return {"done": {}, "bossCleared": [], "attempts": []}


def _norm(d):
    if not isinstance(d, dict):
        d = {}
    for k, v in _EMPTY.items():
        d.setdefault(k, [] if isinstance(v, list) else {})
    if not isinstance(d.get("done"), dict):
        d["done"] = {}
    if not isinstance(d.get("attempts"), list):
        d["attempts"] = []
    if not isinstance(d.get("bossCleared"), list):
        d["bossCleared"] = []
    return d


def _backup_corrupt(vid, raw):
    """坏行留证据：直接返回空会让进度静默消失，事后无法追溯。"""
    try:
        os.makedirs(CORRUPT_DIR, exist_ok=True)
        p = os.path.join(CORRUPT_DIR, "%s-%d.json" % (vid[:16], int(time.time())))
        with open(p, "w", encoding="utf-8") as f:
            f.write(raw or "")
    except Exception:
        pass


def _read(conn, vid):
    global LAST_LOAD_ERROR
    row = conn.execute("SELECT data FROM learners WHERE vid=?", (vid,)).fetchone()
    if not row:
        return _fresh()
    try:
        return _norm(json.loads(row[0]))
    except Exception as e:
        LAST_LOAD_ERROR = "%s: %s" % (type(e).__name__, e)
        _backup_corrupt(vid, row[0])
        return _fresh()


def _write(conn, vid, d):
    attempts = d.get("attempts")
    if isinstance(attempts, list) and len(attempts) > MAX_ATTEMPTS:
        d["attempts"] = attempts[-MAX_ATTEMPTS:]
    conn.execute(
        "INSERT INTO learners(vid,data,updated) VALUES(?,?,?) "
        "ON CONFLICT(vid) DO UPDATE SET data=excluded.data, updated=excluded.updated",
        (vid, json.dumps(d, ensure_ascii=False), time.time()))


def load(vid=DEFAULT_VID):
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            return _read(conn, vid)
        finally:
            conn.close()


def save(d, vid=DEFAULT_VID):
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _write(conn, vid, _norm(d))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


@contextlib.contextmanager
def transaction(vid=DEFAULT_VID):
    """读-改-写全程持写锁：并发交卷不会丢更新。"""
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            d = _read(conn, vid)
            yield d
            _write(conn, vid, d)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---------------- 分人相关的三条运维动作 ----------------

def has_record(vid):
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT 1 FROM learners WHERE vid=?", (vid,)).fetchone()
            return bool(row)
        finally:
            conn.close()


def reset(vid):
    """清空这一个访客的记录（不动别人的）。"""
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM learners WHERE vid=?", (vid,))
        finally:
            conn.close()


def seed_demo(vid):
    """把示例学情复制给当前访客（用于课堂演示；标记 seeded=true 以便提示）。"""
    vid = normalize_vid(vid)
    if vid == DEMO_VID:
        return 0
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT data FROM learners WHERE vid=?", (DEMO_VID,)).fetchone()
            if not row:
                return 0
            d = _norm(json.loads(row[0]))
            d["seeded"] = True
            conn.execute("BEGIN IMMEDIATE")
            _write(conn, vid, d)
            conn.commit()
            return len(d.get("attempts") or [])
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def stats(vid=DEFAULT_VID):
    """给 /api/health 用：当前桶的条数 + 全站访客数（不暴露各自内容）。"""
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            d = _read(conn, vid)
            visitors = conn.execute("SELECT COUNT(*) FROM learners WHERE vid<>?",
                                    (DEMO_VID,)).fetchone()[0]
            row = conn.execute("SELECT updated FROM learners WHERE vid=?", (vid,)).fetchone()
            return {"attempts": len(d.get("attempts") or []),
                    "learned": len(learned_chars(d)),
                    "seeded": bool(d.get("seeded")),
                    "updated": (row[0] if row else 0),
                    "visitors": visitors,
                    "error": LAST_LOAD_ERROR}
        finally:
            conn.close()


# ---------------- 统计 ----------------

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
    """课程字表：只含课程层，不含 1,179 字的通用字形库。

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


def diagnose(idx, vid=DEFAULT_VID):
    """返回可直接渲染的学习诊断（只看这一个访客的记录）。

    每个数字都要能对上口径：
      · 课程字覆盖 = 接触过的课程字 / 课程字表字数，只表示「见过」，不等于会做；
      · 练习正确率 = 答对次数 / 作答次数，来自实际作答，不是浏览行为；
      · 能力维度   = 按题型（构件分析 / 字义理解 / 字形笔画）分别算正确率；
      · 待复习     = 至少答错过一次的字。
    """
    from retrieval import get_kb_meta
    vid = normalize_vid(vid)
    d = load(vid)
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
        # 这一页的数据只属于当前浏览器，不是全班/全机器的混合体
        "scope": "self",
        "seeded": bool(d.get("seeded")),
    }
