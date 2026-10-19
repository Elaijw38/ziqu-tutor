# -*- coding: utf-8 -*-
"""把全部条目合并成**一个** Markdown，供 Dify 免费版一次上传。

Dify 免费版限制「每批 1 个文件」，所以不能一条一个文件。
但引用时只显示文件名，出处会丢——解决方法是：
**把"出处"写进每条的正文里**，并用固定分隔符划线，Dify 按分隔符分段后，
每个分段的文本自带出处，引用点开仍然能核对。

分隔符用单独一行 `---`（Markdown 水平线），在 Dify 里填同样的分隔符即可。
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(ROOT, "data", "kb.jsonl")
OUT = os.path.join(ROOT, "out", "dify-kb-merged.md")
KIND = {"wangyi": "王邑实物", "boss": "构件讨伐", "codex": "讨伐名录",
        "glyph": "甲骨字形", "general": "甲骨文通识", "etymology": "字源"}
SEP = "\n---\n"


def main():
    rows = [json.loads(l) for l in io.open(KB, encoding="utf-8") if l.strip()]
    parts = []
    for r in rows:
        ch = r.get("char") or ""
        kind = KIND.get(r.get("kind"), r.get("kind") or "条目")
        meta = r.get("meta") or {}
        zone = meta.get("zone") or meta.get("tier") or meta.get("topic") or ""
        if ch:
            head = "## %s · %s%s" % (kind, ch, ("（%s）" % zone) if zone else "")
        else:
            head = "## %s%s" % (kind, ("（%s）" % zone) if zone else "")
        parts.append("%s\n\n%s\n\n出处：%s" % (head, r["text"], r["source"]))
    text = ("# 甲骨文 AI 助教 · 知识库\n\n"
            "三个来源相互独立：甲骨字形数据集（CC BY 4.0）、甲骨文通识与字源（标注文献）、"
            "课程教学案例。\n每条一个分段，以单独一行 --- 分隔；每段末尾带出处。\n"
            + SEP.join(parts) + "\n")
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(text)

    chunks = [c for c in text.split("\n---\n") if c.strip()]
    print("  写出 %s  %.0f KB" % (OUT, os.path.getsize(OUT) / 1024))
    print("  按分隔符切分 → %d 段（知识库 %d 条）" % (len(chunks), len(rows)))
    print("  最长段 %d 字，最短段 %d 字"
          % (max(len(c) for c in chunks), min(len(c) for c in chunks)))
    print("\n  第一段开头：")
    for line in chunks[1].strip().splitlines()[:5]:
        print("    " + line[:90])


if __name__ == "__main__":
    main()
