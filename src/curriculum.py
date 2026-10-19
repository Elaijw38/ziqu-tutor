# -*- coding: utf-8 -*-
"""四库的静态配置层：课程知识点库 + 诊断干预库。

为什么单独一个模块：
  · 知识点、能力维度、阈值、错因规则是「课程与教学法」的配置，不是某段代码的常量。
    集中放在 data/curriculum.json 与 data/diagnosis.json，教师改配置就能调，页面不写死数字。
  · learner（证据存取）、quiz（题目）、learning（诊断）、server（接口）都要读同一份配置，
    放在这里可以避免互相 import 成环。

四库的其余两库是运行期数据，落在同一个 SQLite（data/learners.db），不新建独立数据库：
  · 题目与评分库  quiz_items 表（item_id 主键，含标准答案、知识点、难度、出处）
  · 学习证据库    attempts 表（attempt_id 主键，指向 item_id 与 knowledge_point_id）
  · 知识点库      curriculum.json（本模块加载，只读）
  · 诊断与干预库  diagnosis.json（本模块加载，规则与文案）

`course_id / knowledge_point_id / item_id / attempt_id` 四个键把四库串起来。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CURRICULUM_PATH = os.path.join(DATA, "curriculum.json")
RULES_PATH = os.path.join(DATA, "diagnosis.json")

# 配置读不出来时的兜底：宁可少几个知识点，也不能让诊断页整页报错。
# 这些默认值只用于兜底，正常运行时以 JSON 为准。
_DEFAULT_CURRICULUM = {
    "course_id": "zzu-hanzi-culture",
    "course_title": "《汉字与中国文化》通识课",
    "goals": [],
    "dimensions": [],
    "knowledge_points": [
        {"knowledge_point_id": "kp.form.pictograph", "name": "象形字辨识",
         "dimension_id": "dim.glyph", "question_types": ["form"], "has_items": True},
        {"knowledge_point_id": "kp.comp.split", "name": "构件拆分",
         "dimension_id": "dim.component", "question_types": ["comp"], "has_items": True},
        {"knowledge_point_id": "kp.glyph.strokes", "name": "甲骨字形笔画",
         "dimension_id": "dim.glyph", "question_types": ["stroke"], "has_items": True},
    ],
    "type_to_kp": {"form": "kp.form.pictograph", "comp": "kp.comp.split",
                   "stroke": "kp.glyph.strokes"},
    "difficulty_by_type": {"form": "intro", "comp": "core", "stroke": "extend"},
    "difficulty_label": {"intro": "入门", "core": "巩固", "extend": "拓展"},
}

_DEFAULT_RULES = {
    "thresholds": {"min_evidence": 3, "solid_evidence": 5, "mastery_acc": 80,
                   "weak_acc": 60, "recent_n": 10, "max_wrong_items": 8, "max_causes": 4},
    "status": {}, "causes": [],
    "unattributed": {"cause_id": "cause.unattributed", "name": "暂无法归因",
                     "why": "仅凭这一次作答无法判断原因。", "hint": "回看题目对应的条目。"},
    "actions": {"no_record": "还没有作答记录，先做一组随堂练习。"},
}

_CACHE = {}


def _load(path, default):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return default
    key = (path, mtime)
    if key in _CACHE:
        return _CACHE[key]
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("配置不是对象")
    except Exception:
        # 配置坏了不能把服务带崩：用兜底值继续，页面上仍能练习与统计
        d = default
    _CACHE[key] = d
    return d


def curriculum():
    return _load(CURRICULUM_PATH, _DEFAULT_CURRICULUM)


def rules():
    return _load(RULES_PATH, _DEFAULT_RULES)


def course_id():
    return curriculum().get("course_id") or "zzu-hanzi-culture"


def knowledge_points():
    return curriculum().get("knowledge_points") or []


def kp_index():
    return {k["knowledge_point_id"]: k for k in knowledge_points()
            if k.get("knowledge_point_id")}


def dimension_name(dim_id):
    for d in curriculum().get("dimensions") or []:
        if d.get("dimension_id") == dim_id:
            return d.get("name") or dim_id
    return dim_id or "未分类"


def kp_for_type(kind):
    return (curriculum().get("type_to_kp") or {}).get(kind) or ""


def kp_name(kp_id):
    k = kp_index().get(kp_id)
    return (k or {}).get("name") or (kp_id or "未归属知识点")


def difficulty_of(kind):
    cfg = curriculum()
    key = (cfg.get("difficulty_by_type") or {}).get(kind) or "core"
    label = (cfg.get("difficulty_label") or {}).get(key) or key
    return key, label


def threshold(name, default=0):
    v = (rules().get("thresholds") or {}).get(name)
    return v if isinstance(v, (int, float)) else default


def status_meta(key):
    """状态文案：模板里的 {answered} 等占位符由调用方填充。"""
    return (rules().get("status") or {}).get(key) or {}


def status_label(key):
    return (status_meta(key).get("label") or key)


def cause_rules():
    out = []
    for c in rules().get("causes") or []:
        if c.get("cause_id") and c.get("applies"):
            out.append(c)
    return out


def cause_by_id(cid):
    for c in cause_rules():
        if c.get("cause_id") == cid:
            return c
    u = rules().get("unattributed") or {}
    return u if u.get("cause_id") == cid else None


def unattributed():
    return rules().get("unattributed") or _DEFAULT_RULES["unattributed"]


def action(key, **kw):
    tpl = (rules().get("actions") or {}).get(key) or ""
    try:
        return tpl.format(**kw)
    except (KeyError, IndexError):
        return tpl


def fill(tpl, **kw):
    """状态模板填充；模板里多写了未提供的占位符时保持原样，不抛异常。"""
    try:
        return (tpl or "").format(**kw)
    except (KeyError, IndexError):
        return tpl or ""
