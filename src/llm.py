# -*- coding: utf-8 -*-
"""大模型接入层（OpenAI 兼容协议）+ 工具调用 agent。

为什么用 OpenAI 兼容协议：国内主流平台（百炼、火山方舟、DeepSeek、智谱、Moonshot）
和本地 Ollama / vLLM 都提供 `/chat/completions` 兼容端点，换平台只改三个环境变量，
代码一行不动。

设计约束（都在代码里落实，不是口头承诺）：
  1. **密钥只在服务端**：前端永远拿不到 key；health 接口只报"已接入/未接入"。
  2. **超时必降级**：任何异常/超时都退回本地抽取式回答，演示不会白屏。
  3. **事实由我们给**：工具只返回知识库原文，系统提示词禁止模型补充事实外内容。
  4. **可解释**：模型调了哪些工具、检索到哪些条目，全部记在返回里。

配置（环境变量，或项目根目录 config.local.env）：
    ZQ_LLM_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
    ZQ_LLM_KEY=sk-xxxx
    ZQ_LLM_MODEL=qwen-plus
常见取值（以各平台文档为准）：
    DeepSeek      https://api.deepseek.com/v1                deepseek-chat
    阿里云百炼     https://dashscope.aliyuncs.com/compatible-mode/v1   qwen-plus
    火山方舟       https://ark.cn-beijing.volces.com/api/v3   <endpoint-id>
    智谱          https://open.bigmodel.cn/api/paas/v4        glm-4-plus
    本地 Ollama   http://127.0.0.1:11434/v1                  qwen2.5:7b
"""
import io
import json
import os
import urllib.error
import urllib.request

def _urlopen(req, timeout):
    """本地地址绕过代理，外网地址沿用系统代理。"""
    import urllib.request as _u
    from urllib.parse import urlparse
    host = (urlparse(req.full_url).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        opener = _u.build_opener(_u.ProxyHandler({}))
        return opener.open(req, timeout=timeout)
    return _u.urlopen(req, timeout=timeout)


TIMEOUT = float(os.environ.get("ZQ_LLM_TIMEOUT") or 25)
MAX_ROUNDS = 4          # 多给一轮：出题 → 评阅 需要两次工具往返
MAX_HISTORY = 6         # 最多回溯 6 条（约 3 轮），再长会挤掉知识库上下文
HISTORY_CHARS = 600     # 单条历史截断，防止长答案把 token 吃掉

# 出题是"有状态"的：题目存在服务端，学生答完再凭 quiz_id 取回评阅。
# 这样模型拿不到答案，也就没法在提问时把答案漏给学生。
_QUIZ_STORE = {}
_QUIZ_SEQ = [0]
# 会话 → 最近一套题。学生下一句说"选 B、C"时，模型手里没有 quiz_id
# （那是上一次工具返回里的东西），靠这里接上，出题→评阅才真能跨轮。
_SESSION_QUIZ = {}


def _load_dotenv():
    """支持项目根目录的 config.local.env（一行一个 KEY=VALUE），省得每次 set。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "config.local.env")
    if not os.path.isfile(p):
        return
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def config():
    _load_dotenv()
    base = (os.environ.get("ZQ_LLM_BASE") or "").rstrip("/")
    key = os.environ.get("ZQ_LLM_KEY") or ""
    model = os.environ.get("ZQ_LLM_MODEL") or ""
    return {"base": base, "key": key, "model": model,
            "ready": bool(base and model and key)}


def chat(messages, tools=None, temperature=0.2, timeout=None):
    """调用 /chat/completions。返回 (message_dict, raw)。异常向上抛，由调用方降级。"""
    c = config()
    if not c["ready"]:
        raise RuntimeError("未配置大模型（ZQ_LLM_BASE/KEY/MODEL）")
    payload = {"model": c["model"], "messages": messages,
               "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(
        c["base"] + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + c["key"]})
    with _urlopen(req, timeout or TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"], data


# ---------------- 工具（只暴露"查知识库/看学情"，不许模型自己编） ----------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "检索甲骨文课程知识库，返回若干条带出处的原文条目。"
                           "回答任何关于字形、字义、构件、打法的问题之前必须先调用它。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "检索词，例如「家 构件」"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_learner_state",
            "description": "读取当前学生的学习诊断（覆盖率、分片掌握、构件短板、错题）。"
                           "学生问「我哪里弱」「接下来学什么」时必须先调用它。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": "按当前学情出一套随堂练习（答错过的字优先，其次没学过的字）。"
                           "返回题目与选项，但不返回答案——答案由服务端保存。"
                           "学生说「给我出几道题」「考考我」「练一下」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "题量，1-5，默认 3"},
                    "seed": {"type": "integer", "description": "可选。固定后同一套题可复现，便于课堂对照"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answers",
            "description": "提交学生对某套题的作答并评阅，结果会写回学习记录（学情页随之变化）。"
                           "answers 里每项是 {\"char\": 题面里的那个字, \"choice\": 选项下标（从 0 开始）}。",
            "parameters": {
                "type": "object",
                "properties": {
                    "quiz_id": {"type": "string",
                                "description": "可省略。默认评阅本次会话最近出的那套题"},
                    "answers": {
                        "type": "array",
                        "description": "学生作答列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "char": {"type": "string"},
                                "choice": {"type": "integer"},
                            },
                            "required": ["char", "choice"],
                        },
                    },
                },
                "required": ["answers"],
            },
        },
    },
]

SYSTEM = (
    "你是「龟宝」，郑州大学汉字通识课的甲骨文 AI 助教，形象是一只背着行囊的甲骨小向导。\n"
    "自称用「我」，语气亲切但不卖萌，不要用颜文字。\n"
    "你通过工具做事，不要凭空回答：\n"
    "· search_kb —— 查字形、字义、构件、打法、王邑图卷；\n"
    "· get_learner_state —— 看学生进度、薄弱分区、构件短板、错题；\n"
    "· generate_quiz —— 按学情出随堂练习；\n"
    "· submit_answers —— 学生作答后评阅，并写回学习记录。\n"
    "规则（必须遵守）：\n"
    "1. 只使用工具返回的知识库内容作答，不得补充事实之外的知识；\n"
    "2. 每条结论对应到检索到的条目，不要编造出处；\n"
    "3. 字形/字义/构件/打法 → 先调 search_kb；问自己学得怎么样 → 先调 get_learner_state；\n"
    "   学生要练题 → generate_quiz；学生给出作答 → submit_answers；\n"
    "4. 知识库里没有的内容，直接说「知识库里没有……」，并建议可以问什么，不要拿别的字硬凑；\n"
    "5. 对话上文里出现过的字，学生说「它」「这个字」时指的就是那个字，不要重新猜；\n"
    "6. 出题时只给题目和选项，不要报答案；评阅后才可以讲错因；\n"
    "7. 中文回答，简洁（120 字内），不要开场客套，不要用 Markdown 标题。"
)


def _remember_quiz(quiz, session_id=""):
    """题目存服务端，只把 quiz_id 交给模型——模型看不到答案，也就漏不出去。"""
    _QUIZ_SEQ[0] += 1
    qid = "q%d" % _QUIZ_SEQ[0]
    _QUIZ_STORE[qid] = quiz
    while len(_QUIZ_STORE) > 30:          # 只留最近 30 套，常驻内存不无限涨
        _QUIZ_STORE.pop(next(iter(_QUIZ_STORE)), None)
    if session_id:
        _SESSION_QUIZ[session_id] = qid
        while len(_SESSION_QUIZ) > 200:
            _SESSION_QUIZ.pop(next(iter(_SESSION_QUIZ)), None)
    return qid


def _exec_tool(name, args, idx, learner_mod, session_id=""):
    if name == "search_kb":
        q = (args or {}).get("query") or ""
        hits = idx.search(q, k=5)
        rows = [{"id": r["id"], "char": r.get("char"), "text": r["text"],
                 "source": r["source"]} for r, s in hits]
        return {"found": len(rows), "items": rows}
    if name == "get_learner_state":
        d = learner_mod.diagnose(idx)
        return {"level": d["level"], "coverage": d["coverage"],
                "weakest_zone": d["weakest_zone"],
                "weak_comps": [c["comp"] for c in d["weak_comps"]],
                "wrong": [w["char"] for w in d["wrong_top"]],
                "suggestions": d["suggestions"]}
    if name == "generate_quiz":
        import quiz as quiz_mod
        n = max(1, min(5, int((args or {}).get("n") or 3)))
        seed = (args or {}).get("seed")
        quiz = quiz_mod.make_quiz(n, int(seed) if seed else 20261104)
        qid = _remember_quiz(quiz, session_id)
        items = [{"char": it["char"], "type": it["type_label"],
                  "question": it["question"], "options": it["options"]}
                 for it in quiz.get("items") or []]
        return {"quiz_id": qid, "count": len(items), "items": items,
                "note": "答案在服务端。把题目和选项原样给学生；学生作答后用 submit_answers 评阅。"}
    if name == "submit_answers":
        import quiz as quiz_mod
        qid = (args or {}).get("quiz_id") or _SESSION_QUIZ.get(session_id) or ""
        quiz = _QUIZ_STORE.get(qid)
        if not quiz:
            return {"error": "找不到这套题（quiz_id=%s），请先调 generate_quiz 再评阅。" % qid}
        res = quiz_mod.grade(quiz, (args or {}).get("answers") or [])
        _QUIZ_STORE.pop(qid, None)
        if _SESSION_QUIZ.get(session_id) == qid:
            _SESSION_QUIZ.pop(session_id, None)
        return {"score": res["score"], "correct": res["correct"], "total": res["total"],
                "results": [{"char": r["char"], "ok": r["ok"],
                             "right": r["right"], "why": r["why"]}
                            for r in res["results"]],
                "advice": res["advice"]}
    return {"error": "unknown tool: %s" % name}


def _trace_entry(name, args, result):
    """给前端看的工具轨迹：调了什么、查到几条、出了几道题。"""
    if name == "search_kb":
        return {"tool": name, "label": "查知识库",
                "query": (args or {}).get("query") or "",
                "found": result.get("found", 0)}
    if name == "get_learner_state":
        return {"tool": name, "label": "看学情",
                "coverage": result.get("coverage")}
    if name == "generate_quiz":
        return {"tool": name, "label": "出题",
                "count": result.get("count", 0),
                "quiz_id": result.get("quiz_id", "")}
    if name == "submit_answers":
        if result.get("error"):
            return {"tool": name, "label": "评阅", "error": result["error"][:60]}
        return {"tool": name, "label": "评阅",
                "score": result.get("score"),
                "correct": result.get("correct"), "total": result.get("total")}
    return {"tool": name, "label": name}


def _history_messages(history):
    """把前端带来的上文转成 messages；只认 user/assistant，避免注入 system。"""
    out = []
    for m in (history or [])[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:HISTORY_CHARS]})
    return out


def agent_answer(question, idx, learner_mod, history=None, session_id=""):
    """带工具调用的问答。返回 dict；任何失败都返回 None 让上层降级。

    history 是最近几轮 [{"role","content"}]，拼在 system 之后、本次提问之前——
    这样「它怎么打」里的「它」才能指回上一句说的字。
    """
    messages = [{"role": "system", "content": SYSTEM}]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": question})

    citations, called, trace = [], [], []
    rounds = 0

    for _ in range(MAX_ROUNDS):
        msg, _ = chat(messages, tools=TOOLS)
        rounds += 1
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text:
                break
            return {"answer": text, "citations": citations, "tools": called,
                    "trace": trace, "rounds": rounds, "mode": "agent"}

        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls})
        for call in calls:
            fn = (call.get("function") or {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            called.append(name)
            result = _exec_tool(name, args, idx, learner_mod, session_id)
            if name == "search_kb":
                for it in result.get("items") or []:
                    citations.append({"id": it["id"], "source": it["source"],
                                      "title": it.get("char") or it["id"],
                                      "snippet": (it.get("text") or "")[:120]})
            trace.append(_trace_entry(name, args, result))
            messages.append({"role": "tool", "tool_call_id": call.get("id"),
                             "name": name,
                             "content": json.dumps(result, ensure_ascii=False)})

    # 轮次用完仍未收口：再要一次纯文本回答，基于已检索到的内容作答。
    # 比直接返回 None 好——否则整段降级成抽取式，用户看不出为什么质量掉了。
    try:
        msg, _ = chat(messages, tools=None)
        text = (msg.get("content") or "").strip()
    except Exception:
        return None
    if not text:
        return None
    return {"answer": text, "citations": citations, "tools": called,
            "trace": trace, "rounds": rounds, "mode": "agent"}


def status():
    c = config()
    return {"ready": c["ready"], "model": c["model"] or "",
            "base": c["base"] or ""}
