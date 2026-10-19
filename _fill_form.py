# -*- coding: utf-8 -*-
"""按附件3 的七条评审维度，填写附件2 申报表，产出可提交的 docx。

原则：
  1. **只填事实**：原型能跑就说能跑，未接入大模型就写"可选接入"，不吹已经上线的能力。
  2. 不知道的个人信息（姓名/学号/电话）一律留空，由本人补——绝不编造。
  3. 尽量沿用原表格式：写入单元格第一个段落，字号字体跟该格已有 run 对齐。
"""
import copy
import os

from docx import Document
from docx.shared import Pt

SRC = r"C:\Users\32058\Downloads\附件2：郑州大学首届AI智能体创新应用大赛项目申报表.docx"
OUT_DIR = r"C:\DSH\ziqu-tutor\out"
os.makedirs(OUT_DIR, exist_ok=True)
DST = os.path.join(OUT_DIR, "申报表-郑大甲骨文AI助教.docx")

# ---------- 文案 ----------
INTRO = (
    "本项目面向郑州大学汉字类通识课，解决三个具体问题：一是学生课后问字形来源，教师无法逐一答复；"
    "二是教师难以掌握每个学生到底卡在哪个构件上；三是练习与评讲依赖人工。"
    "我们做了一个「甲骨文 AI 助教」：学生用自然语言提问，助教只依据课程知识库作答，并给出可核对的原文出处；"
    "再读取学习记录生成学情诊断（覆盖率、分片掌握、构件短板、错题），按薄弱点自动组卷，"
    "交卷后评讲并把结果回写画像，形成「问—诊—练—评」闭环。"
    "目标用户是修读汉字文化类通识课的本科生与任课教师。"
)

PLAN = (
    "主要功能四个：①带出处的问答；②学情诊断；③按学情自动组卷；④评阅与回写。"
    "智能体方案：本地知识库（170 条、覆盖 146 个汉字，均由课程内容与公开字形数据集导出，每条带出处）"
    "+ 中文检索（字符 1-gram/2-gram + TF-IDF，可解释、无需下载模型）；"
    "问答阶段先检索、再按字去重、再组织答案，超出知识库范围直接拒答或反问，避免编造；"
    "组卷阶段按「构件 / 字义 / 打法」三种题型轮转，并优先考答错过的字；"
    "评阅阶段逐题讲解、写入学习记录。系统预留大模型接入位（ZQ_LLM_KEY/BASE/MODEL），"
    "提示词约束为「只允许使用给定事实作答」，接入后仍然是可溯源的；未配置时退化为抽取式回答，"
    "保证断网或未申请额度也能演示。服务用 Python 标准库实现，不依赖第三方框架。"
)

INNOV = (
    "① 答案可溯源，且以「不编造」为硬约束：每条回答附知识库原文条目，问不到就明说没有；"
    "字形数据来自 CC BY 4.0 公开数据集（带 DOI），王邑地图明确标注为教学示意而非考古复原。"
    "② 诊断落到可教学的颗粒度：不只报「覆盖率」，而是给出构件短板——因为合体字的构件正是拆字练习与 "
    "Boss 战的破防部位，学生缺哪个构件，直接对应练什么。"
    "③ 题库不预置而由知识库生成：知识库扩充，题目与讲解同步变化，教师换一门课只需换知识库。"
)

BASE = (
    "已完成：知识库导出（170 条 / 146 字，每条带出处）；中文检索与问答（含拒答、去重、意图分流）；"
    "学情诊断、按学情组卷、评阅回写三个接口；前端三页签界面（问答 / 学情诊断 / 随堂练习），"
    "已在本地跑通完整闭环并逐屏验证。"
    "比赛期间计划：①接入大模型，提升表述自然度；②对接真实课堂：导入一学期的学习记录，做前后测；"
    "③教师端：班级汇总与薄弱点排行；④补充字形数据集，把覆盖字表从 146 扩到通识课教学大纲的字量。"
)

RESULT = (
    "拟形成：一个可离线部署的助教系统（含知识库、检索、诊断、组卷、评阅）与一套可复用的课程配置方式。"
    "验证方式：①任务完成率——给定 30 个课程相关问题，统计答对率与出处正确率；"
    "②诊断有效性——对比教师人工判断的薄弱点与系统诊断结果的一致性；"
    "③学习效果——选取一个教学班做前后测，比较使用助教与未使用组的测验得分；"
    "④可用性——课堂试用后收集学生与教师的简短反馈。"
    "当前已有的初步数据：知识库 170 条、覆盖 146 字；拒答与出处核对已逐条人工验证。"
)

LINK = (
    "原型本地运行：python src/server.py 8770（无需联网、无需安装依赖）。"
    "演示截图与逐屏验证记录随申报材料提供；如评审需要可现场演示。"
)

TESTED = (
    "本地完整跑通「提问→诊断→组卷→评阅→画像更新」闭环；已逐屏截图核验；"
    "对超出知识库范围的问题（如「今天天气」）验证为拒答，不产生编造内容。"
)

OTHER = (
    "对应附件1 的 A2「AI 助教 · 教、学、评闭环与个性化学习」。"
    "数据合规：仅使用公开数据集（CC BY 4.0，DOI 10.5281/zenodo.22467946）与本项目自建内容，"
    "不使用学校内部数据与个人信息；课程名与班级在界面中标注为「示例课程，可配置」。"
    "与已有作品的关系：本项目独立开发，复用本人另一件作品（汉字文化互动游戏）的自有内容，只读导出，不修改原作品。"
)

# ---------- 写入工具 ----------
def put(cell, text, size=9.5):
    """写进单元格：**先清空原有段落与文字**（表里那些"可填写 Demo、视频…"
    的占位说明必须清掉，否则会和填入内容混在一起），再按段落写入。"""
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    p = cell.paragraphs[0]
    for r in list(p.runs):
        r._element.getparent().remove(r._element)
    run = p.add_run(text)
    run.font.size = Pt(size)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)


def tick(cell, label):
    """把"标签前面那个 □"换成 ☑。

    原表一行里有多个勾选项（□ AI+学习科研  □ 校园真实需求挑战 ...），
    不能简单替换该段第一个 □——必须找到标签前最近的那个。
    """
    for p in cell.paragraphs:
        txt = p.text
        if label not in txt:
            continue
        pos = txt.index(label)
        box = txt.rfind("□", 0, pos)
        if box < 0:
            continue
        new_txt = txt[:box] + "☑" + txt[box + 1:]
        for r in list(p.runs):
            r._element.getparent().remove(r._element)
        p.add_run(new_txt)
        return True
    return False


def main():
    doc = Document(SRC)
    t1, t2 = doc.tables[0], doc.tables[1]
    t_intro, t_plan, t_innov, t_base, t_result = doc.tables[2:7]
    t_data, t_more, t_pledge = doc.tables[7], doc.tables[8], doc.tables[9]

    # 基本信息
    put(t1.cell(0, 1), "郑大汉字通识课 AI 助教（甲骨文智能助教）", size=10)
    tick(t1.cell(0, 3), "校园真实需求挑战")
    tick(t1.cell(1, 1), "赛事发布任务")
    tick(t1.cell(1, 3), "已有初步原型")

    # 申报内容
    put(t_intro.cell(1, 0), INTRO)
    put(t_plan.cell(1, 0), PLAN)
    put(t_innov.cell(1, 0), INNOV)

    # 基础与计划
    put(t_base.cell(1, 0), BASE)
    put(t_result.cell(1, 0), RESULT)

    # 数据使用：公开/自建数据
    tick(t_data.cell(0, 0), "仅使用公开数据或自建数据")

    # 已有成果
    put(t_more.cell(0, 1), LINK)
    put(t_more.cell(1, 1), TESTED)
    put(t_more.cell(2, 1), OTHER)

    doc.save(DST)
    print("  已生成：", DST)
    print("  大小：%.0f KB" % (os.path.getsize(DST) / 1024))


if __name__ == "__main__":
    main()
