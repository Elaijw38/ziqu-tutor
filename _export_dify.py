# -*- coding: utf-8 -*-
"""把知识库导出成 Dify 能直接上传的 Markdown。

为什么一条一个文件：Dify 的"引用"显示的是**文件名**，
一条一个文件 = 命中哪条、出处是什么，一眼就能看到，答辩时最好讲。
文件名带上"类型-区域-汉字"，等于把出处写进了引用里。

产出：
    out/dify-kb/*.md        170 个条目文件（上传用）
    out/dify-kb.zip         打包，Dify 支持整包上传
    out/dify-prompt.txt     系统提示词（复制到 LLM 节点）
"""
import io
import json
import os
import re
import zipfile

ROOT = r"C:\DSH\ziqu-tutor"
KB = os.path.join(ROOT, "data", "kb.jsonl")
OUT = os.path.join(ROOT, "out", "dify-kb")
os.makedirs(OUT, exist_ok=True)

KIND = {"wangyi": "王邑实物", "boss": "构件讨伐", "codex": "讨伐名录", "glyph": "字形"}


def safe(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s or "")).strip("_")[:40]


def main():
    rows = [json.loads(l) for l in io.open(KB, encoding="utf-8") if l.strip()]
    files = []
    for r in rows:
        ch = r.get("char") or "字"
        kind = KIND.get(r.get("kind"), r.get("kind") or "条目")
        zone = ((r.get("meta") or {}).get("zone")
                or (r.get("meta") or {}).get("tier") or "")
        name = "%s_%s_%s_%s.md" % (kind, safe(zone) or "通用", safe(ch), safe(r["id"].split(".")[-1]))
        body = (
            "# %s · %s %s\n\n"
            "%s\n\n"
            "> 出处：%s\n"
        ) % (kind, ch, ("（" + zone + "）") if zone else "", r["text"], r["source"])
        p = os.path.join(OUT, name)
        io.open(p, "w", encoding="utf-8", newline="\n").write(body)
        files.append(name)

    zip_path = os.path.join(ROOT, "out", "dify-kb.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in files:
            z.write(os.path.join(OUT, n), arcname=n)

    print("  条目文件 %d 个 → %s" % (len(files), OUT))
    print("  压缩包 → %s  %.0f KB" % (zip_path, os.path.getsize(zip_path) / 1024))

    prompt = """你是「龟宝」，郑州大学汉字通识课的甲骨文 AI 助教，形象是一只背着行囊的甲骨小向导。
自称用「我」，语气亲切但不卖萌，不要用颜文字。

规则（必须遵守）：
1. 只使用下面检索到的课程资料作答，不得补充资料之外的知识；
2. 每条结论尽量对应到资料，不要编造出处；
3. 资料里没有的内容，直接说没有，并提示可以问什么；
4. 中文回答，简洁（120 字内），不要开场客套；
5. 不要用 Markdown 标题，可以用短句分点。

【检索到的课程资料】
{{#context#}}
"""
    pp = os.path.join(ROOT, "out", "dify-prompt.txt")
    io.open(pp, "w", encoding="utf-8", newline="\n").write(prompt)
    print("  系统提示词 → %s" % pp)
    print("  样例文件：", files[:3])


if __name__ == "__main__":
    main()
