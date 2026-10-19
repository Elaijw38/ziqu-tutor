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

TIMEOUT = float(os.environ.get("ZQ_LLM_TIMEOUT") or 25)
MAX_ROUNDS = 3


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
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
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
]

SYSTEM = (
    "你是郑州大学汉字通识课的甲骨文助教。规则（必须遵守）：\n"
    "1. 只使用工具返回的知识库内容作答，不得补充事实之外的知识；\n"
    "2. 每条结论尽量对应到检索到的条目，不要编造出处；\n"
    "3. 学生问字形/字义/构件/打法 → 先调 search_kb；问自己学得怎么样 → 先调 get_learner_state；\n"
    "4. 知识库里没有的内容，直接说没有，并建议可以问什么；\n"
    "5. 中文回答，简洁（120 字内），不要开场客套，不要用 Markdown 标题。"
)


def _exec_tool(name, args, idx, learner_mod):
    if name == "search_kb":
        q = (args or {}).get("query") or ""
        hits = idx.search(q, k=4)
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
    return {"error": "unknown tool: %s" % name}


def agent_answer(question, idx, learner_mod):
    """带工具调用的问答。返回 dict；任何失败都返回 None 让上层降级。"""
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": question}]
    citations, called = [], []

    for _ in range(MAX_ROUNDS):
        msg, _ = chat(messages, tools=TOOLS)
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text:
                return None
            return {"answer": text, "citations": citations,
                    "tools": called, "mode": "agent"}

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
            result = _exec_tool(name, args, idx, learner_mod)
            if name == "search_kb":
                for it in result.get("items") or []:
                    citations.append({"id": it["id"], "source": it["source"]})
            messages.append({"role": "tool", "tool_call_id": call.get("id"),
                             "name": name,
                             "content": json.dumps(result, ensure_ascii=False)})

    return None


def status():
    c = config()
    return {"ready": c["ready"], "model": c["model"] or "",
            "base": c["base"] or ""}
