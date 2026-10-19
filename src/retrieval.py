# -*- coding: utf-8 -*-
"""本地检索：零第三方依赖的中文检索（字符 1-gram + 2-gram + TF-IDF）。

为什么不用向量库：初赛阶段要的是"可演示、可复现、离线能跑"。这个检索器
只用 Python 标准库，答案可解释（能指出命中了哪几个词），也不需要下载模型。
后面要换 Chroma/Faiss，只需替换 search() 的内部实现，对外接口不变。
"""
import io
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(os.path.dirname(HERE), "data", "kb.jsonl")

_CJK = re.compile(r"[\u3400-\u9fff]")
_ASCII = re.compile(r"[a-zA-Z0-9]+")


def load_kb(path=KB_PATH):
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def tokenize(text):
    """中文取单字 + 相邻二字；英文数字按词。返回列表（保留重复，交给 TF 用）。"""
    toks = []
    cjk = _CJK.findall(text)
    toks.extend(cjk)
    for a, b in zip(cjk, cjk[1:]):
        toks.append(a + b)
    toks.extend(w.lower() for w in _ASCII.findall(text))
    return toks


class Index:
    def __init__(self, rows):
        self.rows = rows
        self.postings = {}          # token -> {doc_idx: tf}
        self.doc_len = []
        self.char_to_docs = {}      # 单字 -> [doc_idx]（用于"用户直接问了某个字"）
        for i, r in enumerate(rows):
            m = r.get("meta") or {}
            bits = [r.get("text") or "", r.get("char") or "",
                    m.get("topic") or ""]
            bits.extend(m.get("aliases") or [])
            toks = tokenize(" ".join(b for b in bits if b))
            self.doc_len.append(len(toks) or 1)
            tf = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            for t, c in tf.items():
                self.postings.setdefault(t, {})[i] = c
            ch = r.get("char")
            if ch:
                self.char_to_docs.setdefault(ch, []).append(i)
                # 繁体字形的简体别名也建索引：学生打「龟」，要能命中「龜」
                for alias in (r.get("meta") or {}).get("aliases") or []:
                    self.char_to_docs.setdefault(alias, []).append(i)
        n = len(rows)
        self.idf = {t: math.log(1 + n / (1 + len(p))) for t, p in self.postings.items()}
        self.avg_len = sum(self.doc_len) / max(1, n)

    def search(self, query, k=6):
        q = tokenize(query)
        if not q:
            return []
        scores = {}
        k1, b = 1.2, 0.72
        for t in q:
            if t not in self.postings:
                continue
            idf = self.idf[t]
            for i, tf in self.postings[t].items():
                dl = self.doc_len[i]
                s = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / self.avg_len))
                scores[i] = scores.get(i, 0.0) + s
        # 用户问的字若正好是某条目的字，直接加权（问答里最常见的意图）
        qchars = set(_CJK.findall(query))
        for ch in qchars:
            for i in self.char_to_docs.get(ch, []):
                scores[i] = scores.get(i, 0.0) + 6.0

        # 意图加权：问读音/笔画时，字形层的字段本身就是答案，
        # 不该让课程案例（打法、形象）抢在它前面。只在问题涉及的字上加。
        want_read = any(w in query for w in ("读", "拼音", "发音", "念"))
        want_stroke = any(w in query for w in ("几画", "几笔", "多少画", "多少笔", "笔画"))
        if want_read or want_stroke:
            for ch in qchars:
                for i in self.char_to_docs.get(ch, []):
                    m = self.rows[i].get("meta") or {}
                    if want_read and m.get("pinyin"):
                        scores[i] = scores.get(i, 0.0) + 9.0
                    if want_stroke and m.get("strokes"):
                        scores[i] = scores.get(i, 0.0) + 9.0
        top = sorted(scores.items(), key=lambda x: -x[1])[:k]
        return [(self.rows[i], round(s, 3)) for i, s in top if s > 0]


_SHARED = {}


def get_index(path=KB_PATH):
    if path not in _SHARED:
        _SHARED[path] = Index(load_kb(path))
    return _SHARED[path]


if __name__ == "__main__":
    idx = get_index()
    for q in ["日和月为什么这么写", "「家」为什么是屋顶下有猪", "构件讨伐里虎怎么打", "休这个字怎么来的"]:
        print("\n问：", q)
        for r, s in idx.search(q, k=3):
            print("  [%.2f] %-12s %s" % (s, r["id"], r["text"][:70]))

_META_CACHE = {}


def get_kb_meta(path=KB_PATH):
    """分区与构件统计，给学情诊断用（懒构建，只算一次）。"""
    if path in _META_CACHE:
        return _META_CACHE[path]
    rows = load_kb(path)
    zones, zone_chars, comp_chars = [], {}, {}
    seen_zone = set()
    for r in rows:
        m = r.get("meta") or {}
        zid, zname = m.get("zone_id"), m.get("zone")
        if zid and zid not in seen_zone:
            seen_zone.add(zid)
            zones.append((zid, zname or zid))
        if zid and r.get("char"):
            zone_chars.setdefault(zid, []).append(r["char"])
        for c in (m.get("comps") or []):
            if r.get("char"):
                comp_chars.setdefault(c, [])
                if r["char"] not in comp_chars[c]:
                    comp_chars[c].append(r["char"])
    out = {"zones": zones, "zone_chars": zone_chars, "comp_chars": comp_chars}
    _META_CACHE[path] = out
    return out
