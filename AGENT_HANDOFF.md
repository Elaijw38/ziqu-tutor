# 交接说明 · 甲骨文 AI 助教（龟宝）

> 给接手的智能体/开发者：这份文档假设你**没有任何上下文**。
> 读完你应该能：把服务跑起来、看懂每个文件在干什么、知道哪些坑已经踩过、知道下一步做什么。
> 结构化版本见同目录 `workbuddy.handoff.json`（程序可直接解析）。

---

## 1. 这是什么

郑州大学首届 AI 智能体创新应用大赛的参赛作品原型（对应附件1 的 **A2：AI 助教 · 教、学、评闭环**）。

一句话：**面向汉字通识课的 AI 助教**，学生问字形/字义/打法，它只依据课程知识库作答并给出处；
再读学习记录做学情诊断，按薄弱点组卷，评阅后回写画像 —— 形成「问 → 诊 → 练 → 评」闭环。

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
  llm.py         OpenAI 兼容客户端 + 工具调用 agent（search_kb / get_learner_state）
  build_kb.py    从 ../字趣 只读导出知识库
web/
  index.html     单文件前端（三页签、整身龟宝、出处折叠条）
  assets/        校徽、龟宝
data/
  kb.jsonl       知识库 170 条（每条带 source）
  learner.json   学习记录（删掉即重置演示状态）
out/
  dify-kb-merged.md   Dify 用单文件知识库（170 段，分隔符 ---）
  dify-prompt-v3.txt  Dify LLM 节点提示词（含少样本示例）
  dify-appearance.txt Dify 开场白与建议问题文案
 申报表-郑大甲骨文AI助教.docx  已填写的申报表（个人信息留空待填）
```

---

## 4. 接口契约（前端只依赖这五个）

| 方法 | 路径 | request | response 关键字段 |
|---|---|---|---|
| GET | `/api/health` | — | `kb_rows, chars, llm, model, dify, dify_error` |
| GET | `/api/diagnose` | — | `coverage, level, zones[], weak_comps[], wrong_top[], suggestions[]` |
| POST | `/api/ask` | `{question}` | `answer, citations[{id,source}], mode(dify/agent/extractive/refuse), refused` |
| POST | `/api/quiz` | `{n,seed}` | `items[{char,type,question,options[],answer,answer_index}]` |
| POST | `/api/grade` | `{quiz,answers[{char,choice}]}` | `score, results[{ok,your,right,why}], advice`（并写入 attempts） |

完整示例见 `workbuddy.handoff.json` 的 `api` 段。

---

## 5. 已踩过的坑（**别再踩一遍**）

| 坑 | 症状 | 处理 |
|---|---|---|
| 系统代理拦本机 | 请求 127.0.0.1 返回 **502** | `dify.py`/`llm.py` 用空 ProxyHandler；并设 `no_proxy=127.0.0.1,localhost` |
| Dify 上下文没绑定 | 回答永远“资料为空”，却仍显示引用 | 在 LLM 节点 SYSTEM 末尾用 `{x}` 插入**上下文蓝块**；有黄色警告即未绑定 |
| Dify 免费版单文件上传 | 170 个 md 无法批量传 | 用 `out/dify-kb-merged.md` 单文件；分段标识符 `---`、长度 512、重叠 0 |
| 模型结尾吐 `//` | 回答末尾多两个斜杠 | `dify.py::_clean_answer` 统一清洗；提示词再加约束 |
| 视觉模型做文本 RAG | 有资料却反问用户 | 换 `deepseek-chat`/`qwen-plus`；提示词加少样本示例 |
| 知识库缺会意解释 | “家为什么是屋顶下有猪”只答构件 | `_enrich_kb.py` 补 12 字「常见解释」，措辞不冒充定论 |
| 两个知识库要同步 | 改了 kb 却忘了 Dify 那份 | 改完依次跑 `src/build_kb.py` → `_enrich_kb.py` → `_merge_kb.py` |
| 测试用同进程假服务 | Windows 下连接被重置 | 假服务改成**独立进程**（见 `tests/mock_dify_server.py`） |

---

## 6. 设计决策（为什么这么做）

1. **三级降级**：Dify → 直连模型 → 本地抽取式。赛场网络抖动、额度用尽都不能白屏。
2. **引用来源分两条**：Dify 用 `metadata.retriever_resources`；直连模型用工具返回的知识库条目。两者都归一成 `citations[{id,source}]`，前端只认一种结构。
3. **不编造**：答案只来自知识库；超纲问题返回固定拒答句；知识库没有的会意解释，宁可补“常见解释”并注明学界另有讨论。
4. **诊断落到构件颗粒度**：因为合体字的构件正是字趣第三关 Boss 的破防部位——诊断能直接指导练什么，而不是只报一个覆盖率。
5. **题库由知识库生成**：不预置题库，知识库一换，题目和讲解同步变化，换课程只需换知识库。

---

## 7. 现在能做什么 / 还不能做什么

**能**：
- 三页签完整可用；真实 DeepSeek 已验证（工具调用、约 3 秒/问、4 条出处）
- 超纲问题拒答；学情诊断与组卷评阅闭环
- Dify 链路已用假服务验证通过（含出处转换与清洗）

**不能**：
- 未部署上线（仅 `127.0.0.1`）；无登录、无多用户、无班级汇总
- Dify 真实应用 key（`app-` 开头）尚未接入
- 未接教务系统；课程/班级在界面上标注为“示例”
- 真实班级前后测未做

---

## 8. 下一步（按优先级）

1. 拿到 Dify `app-` key → 填 `config.local.env` → 验证 `dify:true` 与真实引用
2. 把 Dify 的 `retriever_resources` 渲染成与本地一致的出处折叠条（前端结构已就绪）
3. 部署（校内服务器/容器）+ 邀请码式轻认证
4. 对接一学期真实学习记录，做前后测，补申报表“效果验证”数据
5. 教师端：班级汇总与薄弱点排行

---

## 9. 合规与署名（**不要删**）

- 字形数据：hanzi-glyphs-svg / Zenodo，**CC BY 4.0**，DOI `10.5281/zenodo.22467946`，界面与文档均署名
- 王邑地图、Boss 形象：教学示意，**非考古复原**
- 校徽：版权归郑州大学；龟宝形象为本项目原创
- **不使用**学校内部数据与个人信息；界面中课程名与班级标为“示例，可配置”
- 模型 key 只放 `config.local.env`（已在 `.gitignore`），**任何情况下不要提交**

---

## 10. 给接手智能体的开场提示（可直接复制）

```
你在接手项目 ziqu-tutor（甲骨文 AI 助教·龟宝），路径 C:\DSH\ziqu-tutor。
先读 workbuddy.handoff.json 了解接口与文件职责，再读 AGENT_HANDOFF.md 了解已踩过的坑。
约束：只改本仓库，不动 C:\DSH\字趣；答案不得编造，只用知识库内容并给出处；
任何新增外部依赖需先说明理由。启动：python src/server.py 8770。
```
