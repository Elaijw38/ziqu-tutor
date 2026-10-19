# -*- coding: utf-8 -*-
"""Dify 接入层：走 Dify 原生 chat-messages 接口，拿到回答 + 检索来源。

为什么不用 OpenAI 兼容端点：原生接口会返回 `metadata.retriever_resources`，
里面有命中的文档名、分段内容、相似度分数——**引用要信息就靠它**；
兼容端点只有纯文本，等于把"可溯源"丢了。

配置（config.local.env 或环境变量）：
    ZQ_DIFY_BASE=https://api.dify.ai/v1
    ZQ_DIFY_KEY=app-xxxxxxxx
    ZQ_DIFY_TIMEOUT=40

降级：任何异常返回 None，由 ask.py 回退到本地检索或大模型链路。
"""
import io
import json
import os
import urllib.request
import uuid

def _urlopen(req, timeout):
    """本地地址绕过代理，外网地址沿用系统代理。"""
    import urllib.request as _u
    from urllib.parse import urlparse
    host = (urlparse(req.full_url).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        opener = _u.build_opener(_u.ProxyHandler({}))
        return opener.open(req, timeout=timeout)
    return _u.urlopen(req, timeout=timeout)


TIMEOUT = float(os.environ.get("ZQ_DIFY_TIMEOUT") or 40)
LAST_ERROR = ""


import re
def _clean_answer(a):
    """清掉模型自带的杂质：结尾的 // 注释、开头的「答：」、行尾多余符号。

    实测 deepseek-v4-flash-vision-exp 会在回答末尾补一个 "//"，
    换模型也可能有别的怪癖，所以这里做一次统一清洗，前端拿到的就是干净的。
    """
    if not a:
        return a
    lines = []
    for ln in a.splitlines():
        # 整行只有 // 或 // 开头注释的，直接丢掉
        if ln.strip().startswith("//") and len(ln.strip()) <= 40:
            continue
        lines.append(ln.rstrip())
    out = "\n".join(lines).strip()
    # 去掉行尾的 // 及其后的注释
    out = re.sub(r"\s*//\s*[^\n]*$", "", out, flags=re.M).strip()
    # 去掉开头的「答：」「回答：」
    out = re.sub(r"^(答|回答)\s*[:：]\s*", "", out).strip()
    return out


def _load_dotenv():
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
    base = (os.environ.get("ZQ_DIFY_BASE") or "").rstrip("/")
    key = os.environ.get("ZQ_DIFY_KEY") or ""
    return {"base": base, "key": key, "ready": bool(base and key)}


def status():
    c = config()
    return {"ready": c["ready"], "base": c["base"] or ""}


def ask(question, user="zzu-student-demo", conversation_id=""):
    try:
        return _ask_impl(question, user, conversation_id)
    except Exception as e:
        global LAST_ERROR
        LAST_ERROR = "%s: %s" % (type(e).__name__, str(e)[:160])
        return None


def _ask_impl(question, user="zzu-student-demo", conversation_id=""):
    """调 Dify 应用。返回 {answer, citations[], conversation_id} 或 None。"""
    c = config()
    if not c["ready"]:
        return None
    payload = {
        "inputs": {},
        "query": question,
        "response_mode": "blocking",
        "user": user,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    req = urllib.request.Request(
        c["base"] + "/chat-messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + c["key"]})
    try:
        with _urlopen(req, TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        global LAST_ERROR
        LAST_ERROR = "%s: %s" % (type(e).__name__, str(e)[:160])
        return None

    answer = _clean_answer((data.get("answer") or "").strip())
    if not answer:
        return None

    cites, seen = [], set()
    for res in ((data.get("metadata") or {}).get("retriever_resources") or []):
        name = res.get("document_name") or "知识库条目"
        content = (res.get("content") or "").strip()
        key = (name, content[:60])
        if key in seen:
            continue
        seen.add(key)
        # 出处取分段首行（我们的 md 首行就是「## 类型 · 字（区域）」）
        head = content.splitlines()[0].lstrip("# ").strip() if content else name
        cites.append({
            "id": "%s#%d" % (name, len(cites) + 1),
            "source": "%s · %s（相似度 %.2f）"
                      % (name, head, float(res.get("score") or 0)),
            "snippet": content[:200],
        })
    return {"answer": answer, "citations": cites,
            "conversation_id": data.get("conversation_id") or "",
            "mode": "dify"}
