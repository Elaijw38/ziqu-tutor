# -*- coding: utf-8 -*-
"""把 comps_extra.json 的构件合并进知识库（幂等）。

做法：
  · 已有该字的行 → 写入 meta.comps，并在正文补一句「构件：A+B（教学口径）」，附置信度说明；
  · 没有该字的行 → 新增一条 kind=comp 的条目（带 source）；
  · 先备份 kb.jsonl 到 data/_kb.before_comps.jsonl，方便回滚。
不会删除任何既有内容，只在需要时追加。
"""
import io
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(ROOT, "data", "kb.jsonl")
EXTRA = os.path.join(ROOT, "data", "comps_extra.json")
BACKUP = os.path.join(ROOT, "data", "_kb.before_comps.jsonl")
DEFAULT_SRC = ("构件按甲骨字形结构拆分（参《说文解字》形义分析；"
               "裘锡圭《文字学概要》，商务印书馆，1988）")


def main():
    extra = json.loads(io.open(EXTRA, encoding="utf-8").read())
    chars = extra["chars"]
    src_default = extra.get("_source_default") or DEFAULT_SRC

    rows = [json.loads(l) for l in io.open(KB, encoding="utf-8") if l.strip()]
    if not os.path.exists(BACKUP):
        shutil.copy2(KB, BACKUP)

    by_char = {}
    for r in rows:
        by_char.setdefault(r.get("char"), []).append(r)

    added, updated, skipped = 0, 0, []
    for ch, info in chars.items():
        comps = [c for c in (info.get("comps") or []) if c]
        if len(comps) < 2:
            skipped.append((ch, "构件不足两个"))
            continue
        conf = info.get("confidence") or "通行"
        note = info.get("note") or ""
        gloss = info.get("gloss") or ""
        tail = "构件：%s。%s%s" % ("+".join(comps), gloss, ("；" + note) if note else "")
        if conf != "通行":
            tail += "（此拆分%s，属常见但有讨论的释读）" % conf

        exist = by_char.get(ch) or []
        # 优先挂到已经有 comps 的行，其次挂到字形/字源类，最后任意一行
        target = None
        for r in exist:
            if (r.get("meta") or {}).get("comps"):
                target = r
                break
        if not target:
            for k in ("etymology", "glyph", "wangye", "wangyi", "boss", "codex"):
                for r in exist:
                    if r.get("kind") == k:
                        target = r
                        break
                if target:
                    break
        if not target and exist:
            target = exist[0]

        # 始终保证有一条 kind=comp 的练习条目：课程层的行可能被组卷池过滤掉
        has_comp_row = any(r.get("kind") == "comp" for r in exist)
        if not has_comp_row:
            rows.append({
                "id": "comp.%s" % ch,
                "char": ch,
                "kind": "comp",
                "text": "「%s」%s" % (ch, tail),
                "source": src_default,
                "meta": {"comps": comps, "comps_note": note,
                         "comps_confidence": conf, "comps_source": src_default},
            })
            added += 1

        if target is not None:
            meta = target.setdefault("meta", {})
            meta["comps"] = comps
            meta["comps_note"] = note
            meta["comps_confidence"] = conf
            meta["comps_source"] = src_default
            if "构件：" not in (target.get("text") or ""):
                target["text"] = (target.get("text") or "").rstrip() + " " + tail
            updated += 1
        else:
            rows.append({
                "id": "comp.%s" % ch,
                "char": ch,
                "kind": "comp",
                "text": "「%s」%s" % (ch, tail),
                "source": src_default,
                "meta": {"comps": comps, "comps_note": note,
                         "comps_confidence": conf, "comps_source": src_default},
            })
            added += 1

    with io.open(KB, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_comps = sum(1 for r in rows if (r.get("meta") or {}).get("comps"))
    print("  更新 %d 条，新增 %d 条，跳过 %d 条" % (updated, added, len(skipped)))
    for ch, why in skipped:
        print("    跳过 %s：%s" % (ch, why))
    print("  知识库共 %d 条；有构件信息的字 %d 个" % (len(rows), total_comps))
    print("  备份：%s" % BACKUP)


if __name__ == "__main__":
    main()
