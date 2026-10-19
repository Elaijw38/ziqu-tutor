# -*- coding: utf-8 -*-
"""① 给 Dify 回答加清洗：去掉结尾 // 、答：前缀、多余符号。
   ② 排查假 Dify 测试为什么没走通（打印真实异常）。"""
import io
import json
import os
import sys
import threading
import time
import urllib.request

ROOT = r"C:\DSH\ziqu-tutor"
sys.path.insert(0, os.path.join(ROOT, "src"))

# ---------- ① 清洗函数 ----------
P = os.path.join(ROOT, "src", "dify.py")
t = io.open(P, encoding="utf-8").read()
if "_clean_answer" not in t:
    helper = '''

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
    out = "\\n".join(lines).strip()
    # 去掉行尾的 // 及其后的注释
    out = re.sub(r"\\s*//\\s*[^\\n]*$", "", out, flags=re.M).strip()
    # 去掉开头的「答：」「回答：」
    out = re.sub(r"^(答|回答)\\s*[:：]\\s*", "", out).strip()
    return out
'''
    t = t.replace("def _load_dotenv():", "import re\n" + helper.strip() + "\n\n\ndef _load_dotenv():")
    t = t.replace('    answer = (data.get("answer") or "").strip()',
                  '    answer = _clean_answer((data.get("answer") or "").strip())')
    io.open(P, "w", encoding="utf-8", newline="\n").write(t)
    print("  ✓ dify.py 已加 _clean_answer，并在返回前清洗")

# ---------- ② 排查 ----------
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_dify import Mock  # noqa: E402
from http.server import ThreadingHTTPServer

port = 8903
mock = ThreadingHTTPServer(("127.0.0.1", port), Mock)
threading.Thread(target=mock.serve_forever, daemon=True).start()
time.sleep(0.4)

os.environ["ZQ_DIFY_BASE"] = "http://127.0.0.1:%d/v1" % port
os.environ["ZQ_DIFY_KEY"] = "app-test"

import dify  # noqa: E402

print("  dify.status():", dify.status())

# 手工复现一次请求，看真实错误
url = os.environ["ZQ_DIFY_BASE"] + "/chat-messages"
req = urllib.request.Request(
    url, data=json.dumps({"inputs": {}, "query": "家", "response_mode": "blocking",
                          "user": "t"}, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": "Bearer app-test"})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read().decode("utf-8")
    print("  裸请求 OK，长度", len(body))
except Exception as e:
    print("  裸请求失败：", type(e).__name__, e)

got = dify.ask("家为什么是屋顶下有猪")
print("  dify.ask ->", "None" if not got else (got["answer"][:50], len(got["citations"])))
mock.shutdown()
