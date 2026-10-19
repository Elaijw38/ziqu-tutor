# -*- coding: utf-8 -*-
"""学情：按访客分开的进度存取 + 诊断。

诊断口径（每一句都能对上数据，不编"你很棒"这种话）：
  课程字覆盖 = 接触过的课程字 / 课程字表字数
               （课程字表与 1,179 字的字形库分开：否则字库一扩，
                覆盖率就从 20% 掉到 2%，诊断失去意义）
  练习正确率 = 答对次数 / 作答次数，只来自实际作答，不是浏览行为
  能力维度   = 按题型（构件分析 / 字义理解 / 字形笔画）分别算正确率
  待复习     = 至少答错过一次的字

不按王邑的「天象 / 山川 / 禽兽虫鱼」这些区域分类统计：那是课程地图的划分，
不是学习诊断的维度——学生在「山川」里少见了几个字，说明不了能力弱在哪。

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
# 证据表同理：诊断只关心近期作答，2000 条足够一个学期的课堂使用
MAX_EVIDENCE = 2000

# 最近一次读档失败的原因（坏行/权限问题），供 /api/health 暴露，不再静默清零
LAST_LOAD_ERROR = ""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learners (
    vid     TEXT PRIMARY KEY,
    data    TEXT NOT NULL,
    updated REAL NOT NULL DEFAULT 0
);

-- 题目与评分库：题目生成时写入，评阅时以这里为准（客户端回传的题目不作数）
CREATE TABLE IF NOT EXISTS quiz_items (
    item_id     TEXT PRIMARY KEY,
    quiz_id     TEXT NOT NULL,
    vid         TEXT NOT NULL DEFAULT '',
    kp_id       TEXT NOT NULL DEFAULT '',
    char        TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT '',
    difficulty  TEXT NOT NULL DEFAULT '',
    question    TEXT NOT NULL DEFAULT '',
    options     TEXT NOT NULL DEFAULT '[]',
    answer      TEXT NOT NULL DEFAULT '',
    answer_index INTEGER NOT NULL DEFAULT -1,
    source      TEXT NOT NULL DEFAULT '',
    ts          REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_items_quiz ON quiz_items(quiz_id);

-- 学习证据库：一次作答一行，指向题目与知识点；无姓名、无学号，只有匿名 vid
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    vid        TEXT NOT NULL,
    quiz_id    TEXT NOT NULL DEFAULT '',
    item_id    TEXT NOT NULL DEFAULT '',
    kp_id      TEXT NOT NULL DEFAULT '',
    char       TEXT NOT NULL DEFAULT '',
    kind       TEXT NOT NULL DEFAULT '',
    ok         INTEGER NOT NULL DEFAULT 0,
    chosen     TEXT NOT NULL DEFAULT '',
    correct    TEXT NOT NULL DEFAULT '',
    ts         REAL NOT NULL DEFAULT 0,
    seeded     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_att_vid ON attempts(vid, ts);
CREATE INDEX IF NOT EXISTS ix_att_quiz ON attempts(vid, quiz_id);
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
    """读-改-写全程持写锁：并发交卷不会丢更新。

    期间用 stage_attempt(d, rec) 登记的作答，会在提交前写进 attempts 表，
    和 JSON 学习记录保持同一事务——不会出现「分记了、证据没记」的半截状态。
    """
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            d = _read(conn, vid)
            d["_new_attempts"] = []
            yield d
            for rec in d.pop("_new_attempts", []) or []:
                _insert_attempt(conn, vid, rec)
            _trim_evidence(conn, vid)
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
    """清空这一个访客的记录（不动别人的，也不动题目库本身）。"""
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM learners WHERE vid=?", (vid,))
            conn.execute("DELETE FROM attempts WHERE vid=?", (vid,))
            conn.execute("DELETE FROM quiz_items WHERE vid=?", (vid,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def seed_demo(vid):
    """把示例学情复制给当前访客（用于课堂演示；标记 seeded=true 以便提示）。

    示例的作答证据也一并复制，学情页才能按知识点展示（否则只有数字没有证据）。
    """
    vid = normalize_vid(vid)
    if vid == DEMO_VID:
        return 0
    # demo 桶可能还是旧 JSON 导入的：先迁出证据，再复制（不能在事务里另开连接）
    migrate_evidence(DEMO_VID)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM learners WHERE vid=?", (DEMO_VID,)).fetchone()
            if not row:
                conn.rollback()
                return 0
            d = _norm(json.loads(row[0]))
            d["seeded"] = True
            d["evidence_version"] = 2
            _write(conn, vid, d)
            conn.execute("DELETE FROM attempts WHERE vid=?", (vid,))
            demo = conn.execute(
                "SELECT quiz_id,item_id,kp_id,char,kind,ok,chosen,correct,ts "
                "FROM attempts WHERE vid=?", (DEMO_VID,)).fetchall()
            for i, r in enumerate(demo):
                _insert_attempt(conn, vid, {
                    "attempt_id": "demo.%s.%d" % (vid[:8], i),
                    "quiz_id": r[0], "item_id": r[1], "kp_id": r[2], "char": r[3],
                    "kind": r[4], "ok": bool(r[5]), "chosen": r[6], "correct": r[7],
                    "ts": r[8], "seeded": True})
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


# ---------------- 题目与评分库 / 学习证据库 ----------------
# 四库里的这两库落在同一个 learners.db：不新建独立数据库，靠 item_id / attempt_id 关联。

QUIZ_TTL = 6 * 3600      # 题目留 6 小时：够复盘一节课，又不会无限涨


def save_quiz(quiz_id, vid, items):
    """题目生成后立刻入库。评阅时以库里的标准答案为准。"""
    vid = normalize_vid(vid)
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for it in items or []:
                conn.execute(
                    "INSERT OR REPLACE INTO quiz_items(item_id,quiz_id,vid,kp_id,char,kind,"
                    "difficulty,question,options,answer,answer_index,source,ts) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (it.get("item_id") or "", quiz_id, vid, it.get("kp_id") or "",
                     it.get("char") or "", it.get("type") or it.get("kind") or "",
                     it.get("difficulty") or "", it.get("question") or "",
                     json.dumps(it.get("options") or [], ensure_ascii=False),
                     it.get("answer") or "", int(it.get("answer_index", -1)),
                     it.get("source") or "", now))
            conn.execute("DELETE FROM quiz_items WHERE ts < ?", (now - QUIZ_TTL,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_quiz(quiz_id):
    """取回一套题（含标准答案，只在服务端用）。返回 None 表示已过期或不存在。"""
    if not quiz_id:
        return None
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT item_id,quiz_id,kp_id,char,kind,difficulty,question,options,"
                "answer,answer_index,source FROM quiz_items WHERE quiz_id=? ORDER BY item_id",
                (quiz_id,)).fetchall()
        finally:
            conn.close()
    if not rows:
        return None
    items = []
    for r in rows:
        try:
            options = json.loads(r[7] or "[]")
        except Exception:
            options = []
        items.append({"item_id": r[0], "quiz_id": r[1], "kp_id": r[2], "char": r[3],
                      "type": r[4], "difficulty": r[5], "question": r[6],
                      "options": options, "answer": r[8], "answer_index": r[9],
                      "source": r[10]})
    return {"quiz_id": quiz_id, "items": items, "count": len(items)}


def quiz_total(quiz_id):
    if not quiz_id:
        return 0
    with _LOCK:
        conn = _connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM quiz_items WHERE quiz_id=?",
                                (quiz_id,)).fetchone()[0]
        finally:
            conn.close()


def latest_quiz(vid=DEFAULT_VID):
    """最近一次有作答的套题；没有作答时退回最近生成的一套。"""
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT quiz_id FROM attempts WHERE vid=? AND quiz_id<>'' "
                "ORDER BY ts DESC LIMIT 1", (vid,)).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT quiz_id FROM quiz_items WHERE vid=? ORDER BY ts DESC LIMIT 1",
                    (vid,)).fetchone()
            return row[0] if row else ""
        finally:
            conn.close()


def _insert_attempt(conn, vid, rec):
    conn.execute(
        "INSERT OR REPLACE INTO attempts(attempt_id,vid,quiz_id,item_id,kp_id,char,kind,"
        "ok,chosen,correct,ts,seeded) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (rec.get("attempt_id") or new_vid(), vid, rec.get("quiz_id") or "",
         rec.get("item_id") or "", rec.get("kp_id") or "", rec.get("char") or "",
         rec.get("kind") or rec.get("type") or "", 1 if rec.get("ok") else 0,
         rec.get("chosen") or "", rec.get("correct") or "",
         float(rec.get("ts") or time.time()), 1 if rec.get("seeded") else 0))


def _trim_evidence(conn, vid):
    """证据只留最近 MAX_EVIDENCE 条：诊断看的是近期作答，不保留全学期明细。"""
    n = conn.execute("SELECT COUNT(*) FROM attempts WHERE vid=?", (vid,)).fetchone()[0]
    if n <= MAX_EVIDENCE:
        return
    conn.execute(
        "DELETE FROM attempts WHERE vid=? AND attempt_id NOT IN "
        "(SELECT attempt_id FROM attempts WHERE vid=? ORDER BY ts DESC LIMIT ?)",
        (vid, vid, MAX_EVIDENCE))


def stage_attempt(d, rec):
    """在 transaction() 里登记一条作答证据：结束时与 JSON 学习记录一起提交。

    调用方已经持有写锁，这里不另开连接，避免 SQLite 的嵌套事务报错。
    """
    if not isinstance(d.get("_new_attempts"), list):
        d["_new_attempts"] = []
    d["_new_attempts"].append(rec)


def list_attempts(vid=DEFAULT_VID, quiz_id="", limit=500):
    """按时间顺序返回作答证据。旧 JSON 记录会先迁移成带 kp_id 的行。"""
    vid = normalize_vid(vid)
    migrate_evidence(vid)
    # 先取最近 N 条，再按时间正序返回——直接 ASC LIMIT 会在数据多时只拿到最早的
    sql = ("SELECT * FROM (SELECT attempt_id,quiz_id,item_id,kp_id,char,kind,ok,chosen,"
           "correct,ts,seeded FROM attempts WHERE vid=?")
    args = [vid]
    if quiz_id:
        sql += " AND quiz_id=?"
        args.append(quiz_id)
    sql += " ORDER BY ts DESC LIMIT ?) ORDER BY ts ASC"
    args.append(int(limit))
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(sql, args).fetchall()
        finally:
            conn.close()
    return [{"attempt_id": r[0], "quiz_id": r[1], "item_id": r[2], "kp_id": r[3],
             "char": r[4], "kind": r[5], "ok": bool(r[6]), "chosen": r[7],
             "correct": r[8], "ts": r[9], "seeded": bool(r[10])} for r in rows]


def migrate_evidence(vid=DEFAULT_VID):
    """把旧 JSON 里的 attempts 迁成带 kp_id 的证据行——只跑一次，标记在 JSON 里。

    旧记录没有 item_id / 选择项，无法凭空补出来：item_id 记成 legacy.*，
    chosen/correct 留空，诊断时这些题的错因一律标「暂无法归因」。
    """
    import curriculum
    vid = normalize_vid(vid)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            d = _read(conn, vid)
            if int(d.get("evidence_version") or 1) >= 2:
                conn.commit()
                return 0
            seeded = bool(d.get("seeded"))
            n = 0
            for i, a in enumerate(d.get("attempts") or []):
                if not isinstance(a, dict):
                    continue
                kind = a.get("kind") or a.get("type") or ""
                _insert_attempt(conn, vid, {
                    "attempt_id": "legacy.%s.%d" % (vid[:8], i),
                    "quiz_id": "", "item_id": "", "kp_id": curriculum.kp_for_type(kind),
                    "char": a.get("char") or "", "kind": kind, "ok": bool(a.get("ok")),
                    "chosen": "", "correct": "",
                    "ts": a.get("ts") or 0, "seeded": seeded})
                n += 1
            d["evidence_version"] = 2
            _write(conn, vid, d)
            conn.commit()
            return n
        except BaseException:
            conn.rollback()
            raise
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
        "weak_comps": weak_comps,
        "wrong_top": [{"char": c, "times": n} for c, n in wrong_top],
        "suggestions": suggestions,
        # 这一页的数据只属于当前浏览器，不是全班/全机器的混合体
        "scope": "self",
        "seeded": bool(d.get("seeded")),
    }
