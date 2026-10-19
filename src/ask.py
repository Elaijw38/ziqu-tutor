# -*- coding: utf-8 -*-
"""助教问答：本地检索 → 组织答案 → 附出处。

设计原则（对应 A2 的验收点「问答 + 引用溯源」）：
  1. **答案只用知识库里的内容**，不做自由发挥；每条都带真实出处。
  2. **不知道就说不知道**：相关度不够、或用户没指明是哪个字时，
     反问或拒答，绝不拿不相关的条目硬凑——这是问答系统最容易翻车的地方。
  3. **同一字只说一次**：名录条目与关卡条目常指向同一个字，
     要去重后取信息量最大的那条。

LLM 是可选增强：设 ZQ_LLM_KEY / ZQ_LLM_BASE / ZQ_LLM_MODEL 才启用；
没配就退化成抽取式回答。演示现场没网也不会白屏。
"""
import json
import random
import glyphs as _glyphs
import os
import re
import urllib.request

from retrieval import get_index
import llm as llm_mod
import dify as dify_mod

_CJK = re.compile(r"[\u3400-\u9fff]")
_LAST_LLM_ERROR = ""

# 这些词只是提问的脚手架，不代表"想查哪个字"
FILLER = ("为什么", "怎么", "什么", "这个", "那个", "请问", "如何", "是不是",
          "一共", "几笔", "多少", "意思", "来源", "怎么打", "为什么是", "介绍一下")

MIN_SCORE = 7.0      # 低于这个分视为"知识库里没有"
DOMAIN_WORDS = ("甲骨", "字形", "构形", "构件", "笔画", "王邑", "图卷", "讨伐",
                "Boss", "boss", "象形", "会意", "假借", "字", "打", "通关", "几笔")

# 三态口径：answer（答了）/ refuse（知识库确实没有）/ clarify（没听清，反问）
# 之前只有 refused 布尔值，模型说"知识库里没有"时仍报 false，前端会显示成
# "答了但不给出处"，答辩现场最容易被追问。统一在这里判定。
_CLARIFY_WORDS = ("你想问哪个字", "你指的是", "是想问", "具体是哪个字",
                  "哪一个字", "哪个字", "请告诉我你想问", "需要先知道",
                  "还没出现过", "告诉我是哪个")
_REFUSE_WORDS = ("知识库里没有", "知识库没有", "没有找到", "查不到", "无法回答",
                 "不在知识库", "只回答与", "没有相关内容", "暂时没有",
                 "帮不上忙", "查不了")


# 问"有哪些字/都有什么"这类要字表的问题：知识库没有汇总表，检索到的单字条目
# 也不构成答案，只能拒答。单独判，免得被下面的"部分可答"规则捞回去。
_LISTY = ("有哪些", "哪些字", "都有什么", "都哪些", "列一下", "列举")


def _classify(text, question="", cites=None):
    t = text or ""
    # 先判"库里没有"：模型常在同一句里既说没有、又反问要问哪个字，
    # 这种情况是拒答，不是没听清（问句本身已经明确）。
    if any(w in t for w in _REFUSE_WORDS):
        if any(w in (question or "") for w in _LISTY):
            return "refuse"
        # 部分可答：模型说"这条没有"，但问题指向的那个字确实检索到了，
        # 就不能把出处清掉——有出处可核对，比"查不到"更符合本项目的口径。
        qchars = set(_chars_in(question or ""))
        hit = set()
        for c in (cites or []):
            cid = c.get("id") or ""
            if "." in cid:
                hit.add(cid.rsplit(".", 1)[-1])
        if qchars & hit:
            return "answer"
        return "refuse"
    if any(w in t for w in _CLARIFY_WORDS):
        # 模型常在完整回答末尾补一句“告诉我具体是哪个字”，这不是反问。
        # 真正的反问通常很短、且没有检索命中；有实质内容就按 answer 处理，
        # 否则会出现“答了、有出处，却标成没听清”的误判。
        if len(t) >= 80 or len(cites or []) >= 3:
            return "answer"
        return "clarify"
    return "answer"


# 领域词本身不是"要查的字"，先剥掉再取字，否则"构件是什么"会被判成在问「构」「件」
DOMAIN_STRIP = ("甲骨文", "甲骨", "字形", "构形", "构件", "笔画", "王邑", "图卷",
                "讨伐", "象形", "会意", "假借", "通关", "弱点", "助教", "知识库")


def _chars_in(q):
    s = q
    for w in FILLER + DOMAIN_STRIP:
        s = s.replace(w, "")
    return [c for c in dict.fromkeys(_CJK.findall(s))]


def _intent(q):
    if any(w in q for w in ("打", "击破", "通关", "弱点", "怎么过", "Boss", "boss")):
        return "fight"
    if any(w in q for w in ("怎么写", "怎么写", "构形", "象形", "为什么", "几笔", "笔画", "意思", "代表")):
        return "form"
    return "any"


def _dedupe_by_char(hits, limit, intent="any"):
    """同一个字只保留信息量最大的一条（文本更长的通常带 form/play）。"""
    best = {}
    order = []
    for row, score in hits:
        ch = row.get("char") or row["id"]
        key = ch
        if key not in best:
            best[key] = (row, score)
            order.append(key)
        else:
            r0, s0 = best[key]
            def rank(r):
                txt = r["text"]
                if intent == "fight":
                    return (1 if "打" in txt or "击破" in txt else 0, len(txt))
                if intent == "form":
                    return (1 if ("构形" in txt or "象" in txt) else 0, len(txt))
                return (0, len(txt))
            if rank(row) > rank(r0):
                best[key] = (row, score)
    out = [(best[k][0], best[k][1]) for k in order]
    out.sort(key=lambda x: -x[1])
    return out[:limit]



_CJK_ONE = re.compile(r"[\u3400-\u9fff]")


def _comps_of(idx, ch):
    """取某个字在知识库里声明的构件（没有就返回 None）。"""
    for r in idx.rows:
        if r.get("char") == ch:
            comps = (r.get("meta") or {}).get("comps")
            if comps:
                return [c for c in comps if c], r
    return None, None


def _false_premise(q, idx):
    """识别"X 由 A 和 B 组成"这类断言，与知识库不符时返回纠正答案。

    返回 dict（直接当作回答）或 None（交给模型）。
    """
    m = re.search(r"([\u3400-\u9fff])由([\u3400-\u9fff]{1,2})和([\u3400-\u9fff]{1,2})组成", q or "")
    if not m:
        m = re.search(r"([\u3400-\u9fff])\s*=\s*([\u3400-\u9fff]{1,2})\s*\+\s*([\u3400-\u9fff]{1,2})", q or "")
    if not m:
        return None
    x, a, b = m.group(1), m.group(2), m.group(3)
    comps, row = _comps_of(idx, x)
    if not comps:
        # 目标字在库里没有构件（独体字/只记字形）：
        # 若这套构件其实属于另一个字，也要纠正——否则模型会顺着"木由宀和豕组成"答"对"
        claimed0 = {a, b}
        owner0 = owner_row0 = None
        for r in idx.rows:
            cs = (r.get("meta") or {}).get("comps") or []
            if cs and set(cs) == claimed0 and r.get("char") != x:
                owner0, owner_row0 = r.get("char"), r
                break
        if not owner0:
            return None                  # 认不出这套构件是谁的，交回给模型
        xrow = next((r for r in idx.rows if r.get("char") == x), None)
        if not xrow:
            return None
        msg = ("不是。「%s」不是由 %s + %s 构成的。" % (x, a, b) +
               "\n%s + %s 是「%s」的构件。" % (a, b, owner0) +
               "\n先核对是哪个字的构件，再下结论。")
        cites = [{"id": owner_row0.get("id"), "char": owner0,
                  "source": owner_row0.get("source"),
                  "title": _card_title(owner_row0),
                  "snippet": (owner_row0.get("text") or "")[:160]}]
        if (xrow.get("meta") or {}).get("comps"):
            cites.insert(0, {"id": xrow.get("id"), "char": x, "source": xrow.get("source"),
                             "title": _card_title(xrow),
                             "snippet": (xrow.get("text") or "")[:160]})
        return {"answer": msg, "citations": cites, "hits": [{"id": c["id"]} for c in cites],
                "grounded": True, "refused": False, "mode": "premise-check"}
    claimed = {a, b}
    if set(comps) == claimed or claimed <= set(comps) or set(comps) <= claimed:
        return None                      # 前提成立，交给模型细说

    # 这套构成其实属于哪个字？
    owner, owner_row = None, None
    for r in idx.rows:
        cs = (r.get("meta") or {}).get("comps") or []
        if cs and set(cs) == claimed and r.get("char") != x:
            owner, owner_row = r.get("char"), r
            break

    msg = "不是。\n「%s」的字形构成是 %s（见下方出处），不是 %s。" % (
        x, " + ".join(comps), " + ".join(sorted(claimed)))
    if owner:
        msg += "\n%s + %s 是「%s」的构成。" % (a, b, owner)
    msg += "\n这类问题先核构件再下结论，别顺着前提走。"

    cites = []
    if row:
        cites.append({"id": row.get("id"), "char": x, "source": row.get("source"),
                      "title": _card_title(row), "snippet": (row.get("text") or "")[:160]})
    if owner_row:
        cites.append({"id": owner_row.get("id"), "char": owner,
                      "source": owner_row.get("source"),
                      "title": _card_title(owner_row),
                      "snippet": (owner_row.get("text") or "")[:160]})
    return {"answer": msg, "citations": cites, "hits": [{"id": c["id"]} for c in cites],
            "grounded": True, "refused": False, "mode": "premise-check"}



_GLYPH_SOURCE = ("Oracle Bone Glyphs: Parametric Vector Dataset (v0.3)，"
                 "CC BY 4.0，DOI 10.5281/zenodo.22467946")


def _glyph_only_answer(chars):
    """B 级：课程材料没收录，但字形数据集里有 —— 只给数据集能支撑的事实。"""
    known = [c for c in chars if _glyphs.book.has(c)]
    if not known:
        return None
    lines = []
    for c in known[:3]:
        info = _glyphs.book.info(c)
        lines.append("「%s」在甲骨字形数据集里有对应字形，标注 %s 画（%s）。"
                     % (c, info.get("n_strokes") or "若干", "甲骨字形笔画，非现代通行笔画"))
    body = ("这个字不在本课课程材料里，所以**字义、释文和用法我不能讲**，"
            "避免给你没有依据的说法。\n\n"
            + "\n".join(lines) +
            "\n\n以上只是字形数据集的事实，不是本课教学结论；要理解它，建议向任课教师核对。")
    cites = [{"id": "dataset.glyph", "title": "甲骨字形数据集（非课程材料）",
              "source": _GLYPH_SOURCE, "char": known[0],
              "snippet": "数据集仅提供字形几何与笔画数标注，不含字义与释文。"}]
    return {"answer": body, "citations": cites, "hits": [{"id": "dataset.glyph"}],
            "grounded": True, "refused": False, "mode": "partial",
            "scope": "outside_course_glyph_only"}

def _answer_core(question, history=None, conversation_id="", session_id="", vid=""):
    q = (question or "").strip()
    if not q:
        return _refuse("你想问哪个字？直接说字，比如「家为什么是屋顶下有猪」。")

    idx = get_index()

    # ⓪-预备：错误前提的确定性核对（评测 f02 暴露过：模型会顺着"木由宀和豕组成"答"对"）
    _fp = _false_premise(q, idx)
    if _fp:
        return _fp

    # ⓪ 配了 Dify 就先走 Dify（知识库与编排在那边，回答自带检索来源）
    if dify_mod.status()["ready"]:
        got = None
        try:
            got = dify_mod.ask(q, conversation_id=conversation_id or "")
        except Exception:
            got = None
        if got:
            got.setdefault("grounded", True)
            got["citations"] = _dedup(got.get("citations") or [])
            _settle(got, q)
            got["hits"] = [{"id": c["id"]} for c in got["citations"]]
            return got

    # ① 配了大模型就走 agent（模型自己决定先检索还是先看学情）
    if llm_mod.status()["ready"]:
        try:
            import learner as learner_mod
            got = llm_mod.agent_answer(q, idx, learner_mod, history=history,
                                       session_id=session_id, vid=vid)
            if got:
                got.setdefault("grounded", True)
                got["citations"] = _dedup(got.get("citations") or [])
                _settle(got, q)
                got["hits"] = got.get("tools") or []
                return got
        except Exception as e:
            # 记一笔但不抛：下面用抽取式兜底，并在返回里标出降级原因
            global _LAST_LLM_ERROR
            _LAST_LLM_ERROR = str(e)[:120]

    # ② 未配置或调用失败 → 本地抽取式（原有逻辑）
    hits = idx.search(q, k=10)
    chars = _chars_in(q)

    if not hits:
        partial = _glyph_only_answer(chars)
        if partial:
            return partial
        return _refuse("这个问题在现有知识库里没有对应内容。可以问我某个字怎么写、"
                       "怎么打，或者它的甲骨字形像什么。", chars)

    best_score = hits[0][1]

    # 用户点了名（问句里出现了知识库里的字）：只答这些字，别扯别的
    named = [(r, s) for r, s in hits if r.get("char") in chars]
    if chars:
        # 出现了"像字"的词、但知识库里没有这个字 → 直接说没有，别拿别的字凑
        if not named:
            # 课程材料没有，但字形数据集可能有（如「龜」「鹿」）→ 给 B 级回答
            partial = _glyph_only_answer(chars)
            if partial:
                return partial
            return _refuse(
                "知识库里没有%s这个字。目前能答 %d 个字，可以换个字试试。"
                % ("「" + "」「".join(chars[:3]) + "」" if chars else "你说的", len(
                    {r.get("char") for r in idx.rows if r.get("char")})), chars)
        hits = named
    else:
        # 没点名：必须是本领域的问题（否则就是"今天天气"这类），且相关度够
        thr = 3.0 if any(w in q for w in DOMAIN_WORDS) else MIN_SCORE
        if best_score < thr:
            return _refuse(
                "我是甲骨文助教，只回答与汉字字形、甲骨文字形与字源相关的问题。"
                "试试：「家为什么是屋顶下有猪」「日为什么写成圆的」「虎怎么打」。", chars)

    picks = _dedupe_by_char(hits, 3, _intent(q))

    lines, cites, used = [], [], []
    for row, score in picks:
        used.append({"id": row["id"], "score": score, "char": row.get("char"),
                     "kind": row.get("kind")})
        # 材料卡：条目名 + 依据原文（蓝图 §6「出处做成可展开材料卡」）
        cites.append({"id": row["id"], "source": row["source"],
                      "char": row.get("char"),
                      "title": _card_title(row),
                      "snippet": (row.get("text") or "")[:160]})
        lines.append(row["text"])

    text = "查到的内容：\n" + "\n".join("· " + t for t in lines)
    text += "\n\n下面每一条都能点开核对原文。"

    polished = None  # 大模型已在上面的 agent 分支处理；这里不再重复调用
    if polished:
        text = polished + "\n\n出处见下方条目。"

    got = {
        "answer": text,
        "citations": _dedup(cites),
        "hits": used,
        "grounded": True,
        "mode": "llm" if polished else "extractive",
    }

    # ---- 三种作答模式（蓝图 §6：直接解释 / 给我提示 / 考考我）----
    mode = (mode or "").strip().lower()
    if mode == "hint" and picks:
        row = picks[0][0]
        first = _first_sentence(row.get("text") or "")
        got["answer"] = ("先只给一条线索：\n· " + first +
                         "\n\n你可以顺着这条想——这个字画的是什么？由哪几块构成？"
                         "\n想好了告诉我，或者说「看答案」。")
        got["hint"] = True
        got["full_answer"] = text          # 前端「看答案」时直接展开，不必再请求
        got["mode"] = "hint"
    elif mode == "quiz" and picks:
        row = picks[0][0]
        ch = row.get("char") or ""
        meta = row.get("meta") or {}
        comps = meta.get("comps") or []
        if comps and len(comps) >= 2:
            stem = "「%s」由哪两块构件组成？" % ch
            answer_line = "正确答案：%s" % " + ".join(comps[:2])
        elif meta.get("n_strokes") or meta.get("strokes"):
            stem = "「%s」的甲骨字形有几笔？" % ch
            answer_line = "正确答案：%s 笔（甲骨字形笔画，不等于现代通行笔画）" % (
                meta.get("n_strokes") or meta.get("strokes"))
        else:
            stem = "「%s」在课程材料里代表什么？" % ch
            answer_line = "正确答案：" + _first_sentence(row.get("text") or "")
        got["answer"] = ("考考你：\n" + stem +
                         "\n\n先自己答，再点「看答案」。")
        got["quiz"] = {"stem": stem, "answer": answer_line,
                       "char": ch, "knowledge_point_id": meta.get("knowledge_point_id") or ""}
        got["mode"] = "quiz"
    return _settle(got, q)


def _first_sentence(s):
    """取第一句，用于提示模式（不能把整段答案直接给出去）。"""
    s = (s or "").strip()
    for sep in ("。", "；", "\n"):
        i = s.find(sep)
        if 6 <= i <= 80:
            return s[:i + (1 if sep != "\n" else 0)]
    return s[:60]


def _card_title(row):
    """材料卡的标题：条目类型 + 字（如「构件讨伐 · 家」）。"""
    kind = {"wangyi": "王邑实物", "boss": "构件讨伐", "codex": "讨伐名录",
            "glyph": "字形", "etymology": "字源", "general": "通用"}.get(
                row.get("kind") or "", row.get("kind") or "条目")
    ch = row.get("char") or ""
    return "%s · %s" % (kind, ch) if ch else kind


def _settle(got, question=""):
    """统一三态：任何链路返回后都过一遍，保证 status / refused / citations 自洽。

    - status=answer  ：正常作答（含"只覆盖一部分但确有出处"），出处保留；
    - status=refuse  ：知识库确实没有，refused=True，出处清空；
    - status=clarify ：没听清要反问，同样不挂出处。
    refused 字段保留，兼容老前端与测试。
    """
    st = got.get("status") or _classify(got.get("answer"), question,
                                        got.get("citations"))
    if st not in ("answer", "refuse", "clarify"):
        st = "answer"
    if got.get("refused") is True:      # Dify 链路自带拒答判定，优先采信
        st = "refuse"
    tools = got.get("tools") or []
    # 学情 / 出题 / 评阅这三类工具的正常回答本来就没有检索出处，不能按
    # "文本里出现'暂时没有'就判拒答"的老规则处理（"暂时没有明显短板"会被误伤）。
    if tools and set(tools) & {"get_learner_state", "generate_quiz", "submit_answers"}:
        st = "answer"
    # 硬约束：既没出处、又没调过任何工具（查库/学情/出题），说明是凭记忆答的。
    # 本项目承诺"答案只用知识库内容并给出处"，这种回答一律按拒答处理，
    # 避免出现"答了、但一条出处都没有"的裸答（答辩现场最容易被追问）。
    elif st == "answer" and not (got.get("citations") or []) and not tools:
        st = "refuse"
    got["status"] = st
    got["refused"] = (st == "refuse")
    if st != "answer":
        got["citations"] = []
        got["hits"] = []
    got.setdefault("mode", "agent")
    return got


def _refuse(msg, chars=None):
    return {
        "answer": msg,
        "citations": [],
        "hits": [],
        "grounded": True,
        "mode": "refuse",
        "status": "refuse",
        "refused": True,
        "asked_chars": chars or [],
    }


def _dedup(cites):
    seen, out = set(), []
    for c in cites:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        out.append(c)
    return out


def _llm_polish(question, facts):
    key = os.environ.get("ZQ_LLM_KEY")
    base = os.environ.get("ZQ_LLM_BASE")
    model = os.environ.get("ZQ_LLM_MODEL")
    if not (key and base and model):
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content":
             "你是甲骨文助教。只允许使用给定事实作答，不得补充事实之外的知识；"
             "中文回答，120 字内，平实，不要编造出处，不要加开场白。"},
            {"role": "user", "content": "事实：\n" + "\n".join(facts) +
                                        "\n\n学生问：" + question},
        ],
        "temperature": 0.2,
    }
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        return (d["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None


if __name__ == "__main__":
    for q in ["日和月为什么这么写", "家为什么是屋顶下有猪", "虎怎么打",
              "今天天气怎么样", "这个字一共几笔"]:
        a = answer(q)
        print("\n" + "-" * 62)
        print("问：", q, " [%s]" % a["mode"])
        print(a["answer"])
        for c in a["citations"]:
            print("  出处:", c["id"], "|", c["source"][:60])

# ============ 统一入口：任何链路返回后，统一补材料卡 + 套三态模式 ============
def answer(question, history=None, conversation_id="", session_id="", vid="",
           mode=""):
    got = _answer_core(question, history=history, conversation_id=conversation_id,
                       session_id=session_id, vid=vid)
    try:
        return _shape_answer(got, question, mode)
    except Exception as e:
        # 以前这里静默兜底，导致"模式改了没效果也不报错"；现在至少留一条痕迹
        import sys as _sys
        _sys.stderr.write("[ask] _shape_answer failed: %s: %s\n" % (type(e).__name__, e))
        return got


def _rows_for(idx, ids_chars):
    """按 id 或字把知识库行捞回来，用于补材料卡字段。"""
    out = []
    for r in idx.rows:
        if r.get("id") in ids_chars or (r.get("char") and r.get("char") in ids_chars):
            out.append(r)
    return out


def _shape_answer(got, question, mode):
    idx = get_index()
    cites = got.get("citations") or []

    # ① 材料卡：缺 title/snippet 的，用本地知识库补上（Dify 链路本来就有）
    keys = set()
    for c in cites:
        keys.add(c.get("id"))
        if c.get("char"):
            keys.add(c["char"])
    rows = _rows_for(idx, keys)
    by_id = {r.get("id"): r for r in rows}
    by_char = {}
    for r in rows:
        by_char.setdefault(r.get("char"), r)
    for c in cites:
        if not c.get("title") or not c.get("snippet"):
            r = by_id.get(c.get("id")) or by_char.get(c.get("char"))
            if r:
                c.setdefault("title", _card_title(r))
                c.setdefault("snippet", (r.get("text") or "")[:160])

    # ② 三态模式
    mode = (mode or "").strip().lower()
    if mode not in ("hint", "quiz") or got.get("refused"):
        return got

    first = None
    for c in cites:
        r = by_id.get(c.get("id")) or by_char.get(c.get("char"))
        if r:
            first = r
            break
    if not first:
        return got

    ch = first.get("char") or ""
    meta = first.get("meta") or {}

    if mode == "hint":
        got["full_answer"] = got.get("answer") or ""
        got["answer"] = ("先只给一条线索：\n· " + _first_sentence(first.get("text") or "") +
                         "\n\n顺着这条想一想：这个字画的是什么？由哪几块构成？"
                         "\n想好了可以直接说，或者点「看答案」。")
        got["hint"] = True
        # 提示模式也不该把出处标题（含字名）直接摆出来
        got["reveal_citations"] = got.get("citations") or []
        got["citations"] = []
        got["mode"] = "hint"
    else:
        # —— 辨形题：只给甲骨字形，四选一 ——
        # 关键：目标字不能是问句里提到的字，否则"问了家、又考家"等于送答案
        asked = set(_CJK.findall(question or ""))
        course = [r for r in idx.rows
                  if r.get("char") and r.get("kind") in ("wangyi", "boss", "codex")
                  and r["char"] not in asked]
        if not course:
            course = [r for r in idx.rows
                      if r.get("char") and r.get("kind") in ("wangyi", "boss", "codex")]
        target = random.Random((hash(question) if question else 0) & 0xFFFF).choice(course)["char"]
        ch = target
        chars = [r["char"] for r in course]
        rnd = random.Random(hash(question) & 0xFFFF)
        pool = [c for c in dict.fromkeys(chars) if c != ch]
        rnd.shuffle(pool)
        opts = [ch] + pool[:3]
        rnd.shuffle(opts)
        got["answer"] = ("考考你：这个甲骨字形是哪个字？\n\n"
                         "选项：" + "、".join(opts) +
                         "\n\n先自己认，再点「看答案」。")
        # 解释与出处必须是**目标字**的，不能沿用问句那个字
        trow = next((r for r in idx.rows if r.get("char") == ch), None) or first
        got["quiz"] = {"stem": "这个甲骨字形是哪个字？", "options": opts,
                       "answer": ch,
                       "explain": _first_sentence(trow.get("text") or "")}
        # 作答前：不出出处、不显示字形标签
        got["reveal_citations"] = [{"id": trow.get("id"), "char": ch,
                                    "source": trow.get("source"),
                                    "title": _card_title(trow),
                                    "snippet": (trow.get("text") or "")[:160]}]
        got["citations"] = []
        got["mask_glyphs"] = True
        got["full_answer"] = got.get("full_answer") or ""
        got["mode"] = "quiz"
    return got
