# -*- coding: utf-8 -*-
"""让本机地址绕过系统代理。

症状：请求 http://127.0.0.1:8901 返回 502 Bad Gateway ——
因为环境里设了 http_proxy，urllib 连本机也走代理。
修法：目标是 localhost/127.0.0.1 时用空的 ProxyHandler 打开器；
外网地址（api.dify.ai 等）仍按系统代理走。
"""
import io
import os

HELPER = '''

def _urlopen(req, timeout):
    """本地地址绕过代理，外网地址沿用系统代理。"""
    import urllib.request as _u
    from urllib.parse import urlparse
    host = (urlparse(req.full_url).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        opener = _u.build_opener(_u.ProxyHandler({}))
        return opener.open(req, timeout=timeout)
    return _u.urlopen(req, timeout=timeout)
'''

for name in ("src/dify.py", "src/llm.py"):
    p = os.path.join(r"C:\DSH\ziqu-tutor", name.replace("/", os.sep))
    t = io.open(p, encoding="utf-8").read()
    if "_urlopen" in t:
        print("  %s 已有代理绕过" % name)
        continue
    # 插入 helper（放在最后一个 import 之后）
    t = t.replace("TIMEOUT = ", HELPER.strip() + "\n\n\nTIMEOUT = ", 1)
    # 替换调用点
    t = t.replace("with urllib.request.urlopen(req, timeout=TIMEOUT) as r:",
                  "with _urlopen(req, TIMEOUT) as r:")
    t = t.replace("with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:",
                  "with _urlopen(req, timeout or TIMEOUT) as r:")
    io.open(p, "w", encoding="utf-8", newline="\n").write(t)
    print("  %s 已加代理绕过" % name)
