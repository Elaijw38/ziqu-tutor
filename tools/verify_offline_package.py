# -*- coding: utf-8 -*-
"""离线包验收：解压 → 查敏感信息 → 查绝对路径 → 真跑起来 → 自检 → 清理。

用法：
    python tools/verify_offline_package.py out/ziqu-tutor-离线版.zip
    python tools/verify_offline_package.py <zip> --port 8791

检查项：
  1. 体积是否合理（< 30 MB）
  2. 有没有混进密钥/数据库/截图/临时脚本/.git
  3. 有没有写死 C:\\DSH 这类本机绝对路径（换电脑会崩）
  4. 解压到临时目录后能否独立启动（不依赖原仓库）
  5. /api/health、/api/ask、/api/glyph 是否可用
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

BAD_NAME = re.compile(r"(config\.local\.env|\.db$|^\.git/|_shots/|_probe|_fix|_p\d*\.py|__pycache__|\.pyc$)")
SECRET = re.compile(r"sk-[A-Za-z0-9]{16,}")
ABS_PATH = re.compile(r"C:\\\\DSH|C:/DSH")
TEXT_EXT = (".py", ".js", ".html", ".css", ".md", ".json", ".jsonl", ".bat", ".env", ".txt")


def free_port(start=8791):
    for p in range(start, start + 40):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("找不到空闲端口")


def get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip_path")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()

    z = os.path.abspath(args.zip_path)
    if not os.path.exists(z):
        print("  ✗ 找不到：%s" % z)
        return 2
    size_mb = os.path.getsize(z) / 1048576
    ok = True
    print("  包：%s（%.1f MB）" % (os.path.basename(z), size_mb))
    if size_mb > 30:
        ok = False
        print("  ✗ 体积过大（> 30 MB），检查是否把数据集或截图打进去了")

    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    print("  条目数：%d" % len(names))

    # 1) 不该出现的文件
    bad = [n for n in names if BAD_NAME.search(n)]
    if bad:
        ok = False
        print("  ✗ 包含不该发布的文件：")
        for b in bad[:8]:
            print("      " + b)
    else:
        print("  ✓ 无密钥/数据库/截图/临时脚本/.git")

    # 2) 密钥与绝对路径
    secret_hits, abs_hits = [], []
    with zipfile.ZipFile(z) as zf:
        for n in names:
            if not n.lower().endswith(TEXT_EXT):
                continue
            try:
                txt = zf.read(n).decode("utf-8", "replace")
            except Exception:
                continue
            if SECRET.search(txt):
                secret_hits.append(n)
            if ABS_PATH.search(txt):
                abs_hits.append(n)
    if secret_hits:
        ok = False
        print("  ✗ 疑似密钥：%s" % secret_hits[:5])
    if abs_hits:
        print("  ⚠ 写死了本机路径（换盘可能崩）：%s" % abs_hits[:6])
    if not secret_hits and not abs_hits:
        print("  ✓ 无密钥、无本机绝对路径")

    # 3) 解压并独立启动
    tmp = tempfile.mkdtemp(prefix="zq-pkg-")
    port = args.port or free_port()
    proc = None
    try:
        with zipfile.ZipFile(z) as zf:
            zf.extractall(tmp)
        roots = [os.path.join(tmp, d) for d in os.listdir(tmp)]
        base = tmp
        for r in roots:
            if os.path.isdir(r) and os.path.exists(os.path.join(r, "src", "server.py")):
                base = r
                break
        server = os.path.join(base, "src", "server.py")
        if not os.path.exists(server):
            print("  ✗ 包里没有 src/server.py，结构不对")
            return 1

        env = dict(os.environ)
        env.pop("ZQ_LLM_KEY", None)          # 模拟评委：没有任何 key
        env["PORT"] = str(port)
        errlog = os.path.join(tmp, "_server.err")
        _errf = open(errlog, "wb")
        proc = subprocess.Popen([sys.executable, server], cwd=base, env=env,
                                stdout=subprocess.DEVNULL, stderr=_errf)
        t0 = time.time()
        health = None
        for _ in range(60):
            time.sleep(0.4)
            try:
                st, body = get("http://127.0.0.1:%d/api/health" % port)
                health = json.loads(body)
                break
            except Exception:
                continue
        if not health:
            ok = False
            print("  ✗ 解压后起不来（等了 %.0f 秒）" % (time.time() - t0))
            return 1
        print("  ✓ 独立启动成功（%.1f 秒）" % (time.time() - t0))
        print("     health：kb_rows=%s glyph_chars=%s course_chars=%s llm=%s"
              % (health.get("kb_rows"), health.get("glyph_chars"),
                 health.get("course_chars"), health.get("llm")))
        if not health.get("kb_rows"):
            ok = False
            print("  ✗ 知识库没打进去（kb_rows 为空）")

        # 4) 关键接口
        try:
            import urllib.parse as _up
            st, body = get("http://127.0.0.1:%d/api/glyph/%s?size=120"
                           % (port, _up.quote("日")))
            print("  ✓ /api/glyph/日 → HTTP %s，%d 字节" % (st, len(body)))
        except Exception as e:
            ok = False
            print("  ✗ /api/glyph 失败：%s" % e)

        try:
            req = urllib.request.Request(
                "http://127.0.0.1:%d/api/ask" % port,
                data=json.dumps({"question": "家为什么是屋顶下有猪"}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                a = json.loads(r.read())
            print("  ✓ /api/ask 回答（mode=%s）：%s"
                  % (a.get("mode"), (a.get("answer") or "")[:60].replace("\n", " ")))
            if not (a.get("citations") or []):
                print("     ⚠ 没有出处（无 key 时应走抽取式，仍应有出处）")
        except Exception as e:
            ok = False
            print("  ✗ /api/ask 失败：%s" % e)
            try:
                tail = open(errlog, "rb").read().decode("utf-8", "replace")[-800:]
                print("     服务端错误：\n" + "\n".join("       " + l for l in tail.splitlines()[-12:]))
            except Exception:
                pass
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n  结论：%s" % ("✓ 可以直接发" if ok else "✗ 先修上面的问题"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
