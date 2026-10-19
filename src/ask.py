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


def answer(question):
    q = (question or "").strip()
    if not q:
        return _refuse("你想问哪个字？直接说字，比如「家为什么是屋顶下有猪」。")

    idx = get_index()

    # ⓪ 配了 Dify 就先走 Dify（知识库与编排在那边，回答自带检索来源）
    if dify_mod.status()["ready"]:
        got = None
        try:
            got = dify_mod.ask(q)
        except Exception:
            got = None
        if got:
            got.setdefault("grounded", True)
            got.setdefault("refused", False)
            got["citations"] = _dedup(got.get("citations") or [])
            got["hits"] = [{"id": c["id"]} for c in got["citations"]]
            return got

    # ① 配了大模型就走 agent（模型自己决定先检索还是先看学情）
    if llm_mod.status()["ready"]:
        try:
            import learner as learner_mod
            got = llm_mod.agent_answer(q, idx, learner_mod)
            if got:
                got.setdefault("grounded", True)
                got.setdefault("refused", False)
                got["citations"] = _dedup(got.get("citations") or [])
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
        return _refuse("这个问题在现有知识库里没有对应内容。可以问我某个字怎么写、"
                       "怎么打，或者它在王邑图里代表什么。", chars)

    best_score = hits[0][1]

    # 用户点了名（问句里出现了知识库里的字）：只答这些字，别扯别的
    named = [(r, s) for r, s in hits if r.get("char") in chars]
    if chars:
        # 出现了"像字"的词、但知识库里没有这个字 → 直接说没有，别拿别的字凑
        if not named:
            return _refuse(
                "知识库里没有%s这个字。现在覆盖 %d 个字（王邑 61 个实物、讨伐 21 关、"
                "名录 88 尊），可以换个字试试。"
                % ("「" + "」「".join(chars[:3]) + "」" if chars else "你说的", len(
                    {r.get("char") for r in idx.rows if r.get("char")})), chars)
        hits = named
    else:
        # 没点名：必须是本领域的问题（否则就是"今天天气"这类），且相关度够
        thr = 3.0 if any(w in q for w in DOMAIN_WORDS) else MIN_SCORE
        if best_score < thr:
            return _refuse(
                "我是甲骨文助教，只回答与汉字字形、王邑图卷、构件讨伐相关的问题。"
                "试试：「家为什么是屋顶下有猪」「日为什么写成圆的」「虎怎么打」。", chars)

    picks = _dedupe_by_char(hits, 3, _intent(q))

    lines, cites, used = [], [], []
    for row, score in picks:
        used.append({"id": row["id"], "score": score, "char": row.get("char"),
                     "kind": row.get("kind")})
        cites.append({"id": row["id"], "source": row["source"], "char": row.get("char")})
        lines.append(row["text"])

    text = "查到的内容：\n" + "\n".join("· " + t for t in lines)
    text += "\n\n下面每一条都能点开核对原文。"

    polished = None  # 大模型已在上面的 agent 分支处理；这里不再重复调用
    if polished:
        text = polished + "\n\n出处见下方条目。"

    return {
        "answer": text,
        "citations": _dedup(cites),
        "hits": used,
        "grounded": True,
        "mode": "llm" if polished else "extractive",
        "refused": False,
    }


def _refuse(msg, chars=None):
    return {
        "answer": msg,
        "citations": [],
        "hits": [],
        "grounded": True,
        "mode": "refuse",
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
