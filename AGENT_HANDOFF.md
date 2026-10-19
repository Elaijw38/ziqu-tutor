# 交接说明 · 甲骨文 AI 助教（龟宝）

> 给接手的智能体/开发者：这份文档假设你**没有任何上下文**。
> 读完你应该能：把服务跑起来、看懂每个文件在干什么、知道哪些坑已经踩过、知道下一步做什么。
> 结构化版本见同目录 `workbuddy.handoff.json`（程序可直接解析）。

---

## 1. 这是什么

郑州大学首届 AI 智能体创新应用大赛的参赛作品原型（对应附件1 的 **A2：AI 助教 · 教、学、评闭环**）。

一句话：**独立的甲骨文 AI 助教**，学生问字形、读音、笔画、字义与甲骨文通识，它只依据知识库作答并给出处；
再读学习记录做学情诊断，按薄弱点组卷，评阅后回写画像 —— 形成「问 → 诊 → 练 → 评」闭环。

> **定位（改过一次，别再改回去）**：这不是字趣的游戏配套。
> 字趣的课程内容只是知识来源之一（146 字）；助教的覆盖面由上游字形库（1,168 字）
> 与甲骨文通识层决定。任何“只会答游戏里出现过的字”的写法都是倒退。

- 助教形象：**龟宝**（背行囊的甲骨小向导，取自本人另一件作品「字趣」）
- 界面语言：**郑大校园应用**（校徽、深宝蓝、双语校名、求是担当水印）
- 技术约束：**零第三方依赖**（Python 标准库 + 原生 JS），断网可跑，便于赛场演示

---

## 2. 30 秒跑起来

```bash
cd C:\DSH\ziqu-tutor
python src/server.py 8770
# 浏览器打开 http://127.0.0.1:8770
# 自检：http://127.0.0.1:8770/api/health
```

要接大模型（可选）：

```bash
copy config.example.env config.local.env
# 填三行：ZQ_LLM_BASE / ZQ_LLM_KEY / ZQ_LLM_MODEL
# 例：https://api.deepseek.com/v1 , sk-*** , deepseek-chat
```

`/api/health` 里 `llm:true` 即接入成功；`dify:true` 表示走 Dify 工作流。

---

## 3. 目录与职责

```
src/
  server.py      HTTP 服务（标准库），5 个接口 + 静态页
  ask.py         问答编排：Dify → 大模型 agent → 本地抽取式 → 拒答（逐级降级）
  retrieval.py   中文检索：字 1-gram + 2-gram + TF-IDF；get_kb_meta 供诊断
  learner.py     学情：存取 + 诊断（覆盖率/分片/构件短板/错题/建议）
  quiz.py        出题（题型轮转、错题优先）+ 评阅（讲解 + 回写）
  dify.py        Dify 接入（原生 chat-messages，解析 retriever_resources）
  llm.py         OpenAI 兼容客户端 + 工具调用 agent：search_kb / get_learner_state / generate_quiz / submit_answers
  build_kb.py    三源合并知识库：上游字形全集 + 通识/字源 + 课程案例（字趣只读）
web/
  index.html     单文件前端（三页签；空对话欢迎区→首条消息后收起；回答旁 38px 小头像；出处折叠条）
  assets/        校徽、龟宝
data/
  kb.jsonl       知识库 1,391 条 / 1,179 字（每条带 source）
  upstream/      上游 1,203 字形数据集 + ATTRIBUTION.md（CC BY 4.0）
  general.jsonl  通识 24 条 + 字源 29 条（人工整理，逐条标出处）
  learner.json   学习记录（删掉即重置演示状态）
out/
  dify-kb-merged.md   Dify 用单文件知识库（1,391 段，分隔符 ---）
  dify-prompt-v3.txt  Dify LLM 节点提示词（v4，含通识与字形示例）
  dify-appearance.txt Dify 开场白与建议问题文案
 申报表-郑大甲骨文AI助教.docx  已填写的申报表（个人信息留空待填）
```

---

## 4. 接口契约（前端只依赖这五个）

| 方法 | 路径 | request | response 关键字段 |
|---|---|---|---|
| GET | `/api/health` | — | `kb_rows, chars, course_chars, llm, model, dify, dify_error, store{attempts,learned,error}` |
| GET | `/api/diagnose` | — | `coverage, level, total_chars(课程字表), lexicon_chars(总字表), zones[], weak_comps[], wrong_top[], suggestions[]` |
| POST | `/api/ask` | `{question, history?, conversation_id?, session_id?}` | `answer, citations[{id,source,title?,snippet?}], status(answer/refuse/clarify), refused, trace[], rounds, mode(dify/agent/extractive/refuse)` |
| POST | `/api/quiz` | `{n,seed}` | `items[{char,type,question,options[],answer,answer_index}]` |
| POST | `/api/grade` | `{quiz,answers[{char,choice}]}` | `score, results[{ok,your,right,why}], advice`（并写入 attempts） |

完整示例见 `workbuddy.handoff.json` 的 `api` 段。

---

## 5. 已踩过的坑（**别再踩一遍**）

| 坑 | 症状 | 处理 |
|---|---|---|
| 系统代理拦本机 | 请求 127.0.0.1 返回 **502** | `dify.py`/`llm.py` 用空 ProxyHandler；并设 `no_proxy=127.0.0.1,localhost` |
| Dify 上下文没绑定 | 回答永远“资料为空”，却仍显示引用 | 在 LLM 节点 SYSTEM 末尾用 `{x}` 插入**上下文蓝块**；有黄色警告即未绑定 |
| Dify 免费版单文件上传 | 上百个 md 无法批量传 | 用 `out/dify-kb-merged.md` 单文件；分段标识符 `---`、长度 512、重叠 0 |
| 模型结尾吐 `//` | 回答末尾多两个斜杠 | `dify.py::_clean_answer` 统一清洗；提示词再加约束 |
| 视觉模型做文本 RAG | 有资料却反问用户 | 换 `deepseek-chat`/`qwen-plus`；提示词加少样本示例 |
| 知识库缺会意解释 | “家为什么是屋顶下有猪”只答构件 | `_enrich_kb.py` 补 12 字「常见解释」，措辞不冒充定论 |
| 两个知识库要同步 | 改了 kb 却忘了 Dify 那份 | 改完依次跑 `src/build_kb.py` → `_enrich_kb.py` → `_merge_kb.py` |
| 测试用同进程假服务 | Windows 下连接被重置 | 假服务改成**独立进程**（见 `tests/mock_dify_server.py`） |
| 死的 `import numpy` | `python src/server.py` 直接 `ModuleNotFoundError: numpy`，起不来 | `retrieval.py` 里既没用到 numpy 也不该依赖它（零依赖是卖点），已删该 import |
| Dify 出处显示文件名 | 折叠条里写着 `dify-kb-merged.md`，等于没署名 | `dify.py::_split_segment` 取分段末尾 `出处：` 行作 source，标题/摘录/相似度另存 |
| Dify 拒答仍报未拒答 | `refused=false`，还挂着无关出处 | `_looks_refused()` 认固定拒答句 → `refused=true` 且清空 citations |
| 出题后下一句评阅不上 | 模型下一轮手里没有 `quiz_id`（它在上一轮的工具返回里） | `llm.py::_SESSION_QUIZ` 按 `session_id` 记住本会话最近一套题；`submit_answers` 的 `quiz_id` 改为可省略 |
| 并发交卷丢记录 | 两个人几乎同时提交，先交的那份记录消失 | 学情是「读-改-写」，服务多线程且无锁（实测 8 并发只剩 1 条）。写路径必须走 `learner.transaction()`，不要自己 `load()` 改完再 `save()` |
| 学情突然全空且无报错 | 覆盖度归零，`learner.json` 内容只剩半截 | `save` 直接覆写，崩在中途就留下半截 JSON，`load` 捕获异常后静默返回空。现改为 `.tmp` + `os.replace` 原子写；损坏时留 `.corrupt` 并写 `LAST_LOAD_ERROR`，`/api/health` 的 `store.error` 可见 |
| 作答记录无限增长 | 一学期后 `learner.json` 持续变大、诊断变慢 | `learner.MAX_ATTEMPTS` 保留最近 500 条（只用于错题排行，不需要全量） |
| 字形层整层丢失（历史） | 知识库里 `kind=glyph` 一条都没有，“这个字几笔”永远答不出 | 根因是数据集 v0.3 把 `App.glyphs` 的字段从 `glyphs` 改成 `parts`，旧解析器取到空 `{}` 却不报错。现已**不再从字趣转手**，直接读上游 `data/upstream/jgw_1203_labeled.json`，并在 `build_kb` 里检查字数（<1000 会告警） |
| 字库扩容把诊断打穿 | 覆盖率从 20% 掉到 2%，学生一学期也“未入门” | 学情分母不能是全部字表。`learner.course_chars()` 只取课程层（146 字），`diagnose` 另给 `lexicon_chars` 表示能力边界 |
| 笔画数说错 | 学生问“日几笔”，答 4 笔；甲骨字形其实是 3 画 | 上游 `n_strokes` 是**甲骨字形**笔画数，与现代通行笔画不同。文案必须写“甲骨字形 N 画”，不能冒充现代笔画 |
| 简体字查不到繁体字形 | 问“龟几画”查不到「龜」的条目 | 上游 203 个字标为繁体/异体。`build_kb.SIMPLIFIED` 收常见无争议的简繁对应，写进 `meta.aliases`；`retrieval` 用别名建 `char_to_docs` 索引 |
| 部分可答被判成拒答 | 模型说“知识库里只有尊的字形，字义没有”，前端标成拒答还把出处清空 | `_classify(text, question, cites)`：若问题指向的那个字确实在检索结果里，判 `answer` 保留出处；问字表（“有哪些”）或该字根本不在库里才判 `refuse` |
| 上下文被前端塞脏 | 有人往 `history` 里塞 `system` 或超长文本 | `_history_messages()` 只认 `user/assistant`，最多 6 条、每条 600 字；`server.py` 再校验一次类型 |
| agent 说“知识库里没有”却报 `refused=false` | 前端显示成“答了但不给出处” | `ask.py::_classify` 统一 answer/refuse/clarify 三态，非 answer 一律清空出处 |
| 工具轮次用尽后整段降级 | 答案质量突然掉到抽取式，用户无感 | `agent_answer` 收口时再要一次纯文本回答（不带 tools），尽量不出降级 |
| 学情诊断被误判成拒答 | 问“我学得怎么样”，回答标成 `refuse`、出处被清空 | `get_learner_state` 的正常回答里有“暂时没有明显短板”，撞上 `_REFUSE_WORDS`。`_settle()` 里凡调用过 `get_learner_state/generate_quiz/submit_answers` 的一律 `answer`（这三类工具本来就不产出检索出处） |
| 裸答（答了但没有出处） | 模型凭记忆答完，`citations=[]`，前端显示“答了却不给出处” | `_settle()` 硬约束：既无出处、又没调过任何工具 → 降级 `refuse`。本项目承诺“只用知识库内容并给出处”，宁可拒答 |
| 出题考“打法”，考卷全是游戏黑话 | 选项出现“止封走位、口封印技能、先断枝再斩根” | 课程层 `play`/`tier_note` 是游戏攻略，**不能当考题**。第三种题型由 `play` 改为 `stroke`（甲骨字形几画，选项取邻近数字），`TYPE_LABEL` 同步改「笔画」 |
| 出题数量翻倍 | `make_quiz(3)` 返回 6 题，`make_quiz(5)` 也只返回 6 题 | 变量遮蔽：`_pool`/`stroke` 分支里用 `n` 存笔画数，覆盖了同为 `n` 的题量参数，`len(items) >= n` 的退出条件失效。局部变量改名为 `cnt`（两次踩到，改完先跑 `make_quiz(1/2/3/5)` 验题量） |
| 提示词只管“别编”，不管“怎么讲” | 回答没有固定层次，证据与推测混在一段里 | SYSTEM 升到 v5（证据分级 / 先回答-看字形-怎么理解-学习提示 / 学情诊断 / 练习 / 图片边界 / 隐私边界），同步 `out/dify-prompt-v3.txt`（内容 v5） |
| 欢迎区收起失效 | 发出第一条消息后，龟宝欢迎块仍然占着聊天区顶部 | `.hide{display:none}` 写在 `.welcome{display:flex}` 之前，同权重后者胜。补 `.welcome.hide{display:none}`（以后新增带 display 的块都要注意这条） |
| 空对话永远看不到 | 页面一加载就跑 `ask('日为什么写成圆的')`，欢迎区直接被顶掉 | 删掉自动首问；`input.focus()` 改 `focus({preventScroll:true})`，否则加载完浏览器自动滚到底部，首屏结构看不见 |
| 连按 Enter 发两遍 | 同一句问题在对话里出现两次 | `ask()` 加 `BUSY` 锁（`send.disabled` 只挡鼠标，挡不住表单重复提交），请求结束才放开 |

---

## 6. 设计决策（为什么这么做）

1. **三级降级**：Dify → 直连模型 → 本地抽取式。赛场网络抖动、额度用尽都不能白屏。
2. **引用来源分两条**：Dify 用 `metadata.retriever_resources`；直连模型用工具返回的知识库条目。两者都归一成 `citations[{id,source}]`，前端只认一种结构。
3. **不编造**：答案只来自知识库；超纲问题返回固定拒答句；知识库没有的会意解释，宁可补“常见解释”并注明学界另有讨论。
4. **诊断落到构件颗粒度**：合体字的构件正是辨形的基础——诊断能直接指导练什么，而不是只报一个覆盖率。
5. **题库由知识库生成，但只在课程层出题**：不预置题库，课程层一换，题目和讲解同步变化；
   字形库的 1,168 字多数只有形/音/笔画，拿它出“本义/构件”题会变成无意义填空；
   但笔画题的材料（`meta.strokes`）来自字形层，按课程字去取，所以题目仍不越界。
6. **agent 的工具边界就是能力边界**：四个工具分别对应「查知识 / 看学情 / 出题 / 评阅」，
   学生的四类诉求全落在工具上，模型只负责决定调哪个、调几次（上限 4 轮）。
7. **答案与题目分开存**：`generate_quiz` 只把题目和选项交给模型，答案留在服务端进程里，
   所以模型没有机会“顺手把答案念出来”；评阅只能通过 `submit_answers` 走服务端算分。

---

## 7. 现在能做什么 / 还不能做什么

**能**：
- 三页签完整可用；真实 DeepSeek 已验证（工具调用、2.3 秒/问、5 条出处、`trace` 可看调了什么）
- **知识面独立**：1,168 个字的字形/读音/笔画（上游 CC BY 4.0 数据集）+ 24 条甲骨文通识 + 29 条字源，
  问“甲骨文是什么”“谁发现的”“六书是哪六种”“日怎么读”“龟几画”都有出处
- **多轮对话**：前端带最近 3 轮，问「那它怎么打」能接住上一句的字（已实测）
- **教学闭环进对话**：学生说「出两道题」→ agent 调 `generate_quiz` 出题（不含答案）→
  学生口述选项 → `submit_answers` 评阅并把错题写回学情（已实测 50 分、逐题错因）
- 三态口径统一：`answer / refuse / clarify`，拒答与反问都不挂出处
- 学情诊断与组卷评阅闭环（页签版照旧可用）
- Dify 链路已用假服务验证通过：回答、去重、`//` 清洗、**真署名出处**（标题 + `出处：` 行 + 摘录 + 相似度）、
  拒答标记 `refused=true` 且不挂无关出处

**不能**：
- 未部署上线（仅 `127.0.0.1`）；无登录、无多用户、无班级汇总
- Dify 真实应用 key（`app-` 开头）尚未接入——**这是唯一卡住 Dify 真跑的一步**
- 未接教务系统；课程/班级在界面上标注为“示例”
- 真实班级前后测未做

---

## 8. 下一步（按优先级）

1. 拿到 Dify `app-` key → 填 `config.local.env`（`ZQ_DIFY_BASE` / `ZQ_DIFY_KEY`）→
   重启后 `GET /api/health` 应为 `dify:true`，再问一句看折叠条是不是 `字趣《…》` 署名行
2. ~~把 Dify 的 `retriever_resources` 渲染成与本地一致的出处折叠条~~ **已完成**：
   `dify.py::_split_segment/_citations` 出 `title/source/snippet/score`，前端按有无 title 兼容两种结构
3. 部署（校内服务器/容器）+ 邀请码式轻认证
4. 对接一学期真实学习记录，做前后测，补申报表“效果验证”数据
5. 教师端：班级汇总与薄弱点排行

---

## 9. 合规与署名（**不要删**）

- 字形数据：**Oracle Bone Glyphs: Parametric Vector Dataset v0.3**（Li & Bian, npj Heritage Science 2026），
  **CC BY 4.0**，DOI `10.5281/zenodo.22467946`；署名与字段口径见 `data/upstream/ATTRIBUTION.md`
- 通识与字源：逐条标注文献（王宇信《甲骨学通论》、裘锡圭《文字学概要》、董作宾《甲骨文断代研究例》、
  许慎《说文解字·叙》、《周礼·地官·保氏》、郭沫若主编《甲骨文合集》），转述不改原意
- 王邑地图、Boss 形象：教学示意，**非考古复原**
- 校徽：版权归郑州大学；龟宝形象为本项目原创
- **不使用**学校内部数据与个人信息；界面中课程名与班级标为“示例，可配置”
- 模型 key 只放 `config.local.env`（已在 `.gitignore`），**任何情况下不要提交**

---

## 10. 给接手智能体的开场提示（可直接复制）

```
你在接手项目 ziqu-tutor（甲骨文 AI 助教·龟宝），路径 C:\DSH\ziqu-tutor。
先读 workbuddy.handoff.json 了解接口与文件职责，再读 AGENT_HANDOFF.md 了解已踩过的坑。
这是一个**独立**的甲骨文助教，不是字趣的配套：知识面由上游字形库（1168 字）与通识层决定，
字趣只作为课程案例来源（146 字，只读，不改 C:\DSH\字趣）。
约束：只改本仓库；答案不得编造，只用知识库内容并给出处；任何新增外部依赖需先说明理由。
启动：python src/server.py 8770。
```
