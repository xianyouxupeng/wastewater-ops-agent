# 污水处理运维 Agent（wastewater-ops-agent）项目大纲

> 定位一句话：面向污水处理厂值班员与工艺工程师的开源运维助手——输入故障现象，输出排查清单与处置建议；支持知识库问答、运维台账生成、参数辅助建议。**只给建议，不自动执行。**

---

## 1. 项目目标与非目标

### 目标
1. **故障诊断**：输入异常现象 + 水质/工艺参数 → 输出可能原因 Top3、分步排查清单、临时处置方案
2. **知识库问答**：基于厂内文档（规范/手册/MSDS/SOP）回答问题，必须带引用来源
3. **运维台账**：按模板自动生成日报/交接班记录，导出 Word
4. **参数辅助建议**：基于规则表给出调整建议，全部标注"仅人工参考"

### 三项硬性要求
| 要求 | 实现方式 |
|---|---|
| ① 服务器启动后**手机可访问** | Streamlit 监听 `0.0.0.0`，手机连同一局域网 Wi-Fi，浏览器打开 `http://服务器IP:8501` 即用；界面按手机屏适配 |
| ② 大模型**本地/在线可切换** | 全部走 OpenAI 兼容接口：`.env` 里 `OPENAI_BASE_URL` 指向 Ollama（本地）或 DeepSeek/Qwen（在线），改一行配置即切换，代码零改动；界面提供下拉切换 |
| ③ 知识库**随时增量添加** | 文档丢进 `data/knowledge/` → 重跑 `ingest.py`（基于文件哈希增量，只处理新增/修改的文件，秒级完成）；界面上也提供"更新知识库"按钮 |

### 非目标（安全红线）
- ❌ 不对接 PLC/阀门/泵/加药设备的**控制**接口（数据采集只读）
- ❌ 不输出可直接自动执行的操作指令
- ❌ 不上传任何真实厂区敏感数据到公开仓库

---

## 2. 总体架构

```
用户（值班员 / 工艺工程师）
   ├─ 电脑浏览器
   └─ 📱 手机浏览器（同一局域网，http://服务器IP:8501）
        ↓
  Streamlit 界面（监听 0.0.0.0，后期可选加 FastAPI）
        ↓
  Agent 路由层 —— LLM function calling 选择能力，不做关键词硬匹配
        ↓
┌─────────────────────────────────────┐
│ 能力层（4 个模块，按此顺序开发）      │
│  ① 故障诊断  ② 知识问答             │
│  ③ 运维台账  ④ 参数建议             │
└─────────────────────────────────────┘
        ↓
  工具层：知识检索 / 案例检索 / 规则匹配 / 模板渲染 / 增量入库
        ↓
┌─────────────────────────────────────┐
│ 知识层（三层分离）                   │
│  规则层：fault_tree.yaml            │
│         param_ranges.yaml          │
│  文档层：data/knowledge/ + 向量库   │
│         （随时增量添加，界面可触发） │
│  案例层：cases.jsonl                │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│ 模型层（OpenAI 兼容接口，一处配置）  │
│  本地：Ollama (http://localhost:11434/v1)  │
│  在线：DeepSeek / Qwen / OpenAI API        │
│  切换方式：改 .env 或界面下拉框             │
└─────────────────────────────────────┘
```

核心设计原则：
- **先规则后 RAG**：诊断先用故障树规则跑通，再叠加知识库检索增强；故障树采用**鉴别式决策树 schema**（假设 + 鉴别检查，非平铺原因清单），故障树未覆盖的长尾故障由 LLM(+RAG) 兜底，输出必须强制明示低置信度
- **可插拔模型**：LLM 和 Embedding 全走 OpenAI 兼容接口，`OPENAI_BASE_URL` + `OPENAI_API_KEY` 环境变量决定本地还是在线，代码零改动
- **知识库热更新**：新增文档 = 丢文件 + 跑一次 ingest（或点界面按钮），不停服务、不全量重建
- **手机优先适配**：界面布局按窄屏设计（大按钮、少分栏），手机是值班场景的主要终端
- **生成物不入库**：向量库、`.env`、私有数据一律不提交 GitHub

---

## 3. 目录结构

```
wastewater-ops-agent/
├─ README.md                  # 项目介绍、运行方式、免责声明
├─ LICENSE                    # MIT
├─ PROJECT_OUTLINE.md         # 本文件
├─ requirements.txt
├─ .env.example               # OPENAI_BASE_URL / OPENAI_API_KEY / MODEL_NAME
├─ .gitignore                 # .env / vector_db/ / storage/ / 私有数据
├─ app/
│  ├─ main.py                 # 入口：streamlit run app/main.py --server.address 0.0.0.0
│  ├─ schemas.py              # Pydantic 输入输出模型
│  ├─ config.py               # 读取 .env：模型源(local/api)、地址、密钥
│  ├─ agent/
│  │  ├─ router.py            # LLM 意图路由
│  │  ├─ prompts.py           # 各能力的 system prompt
│  │  └─ llm.py               # OpenAI 兼容客户端封装（本地/在线统一入口）
│  ├─ diagnostic/
│  │  ├─ rules.py             # 加载故障树、规则匹配
│  │  └─ engine.py            # 诊断主流程：规则 + 案例 + LLM
│  ├─ rag/
│  │  ├─ loader.py            # PDF/Word/MD/TXT 解析
│  │  ├─ vectorstore.py       # Chroma 封装
│  │  └─ retriever.py         # 检索 + 引用来源
│  ├─ ledger/
│  │  └─ report_generator.py  # Jinja2 模板渲染 + docx 导出
│  ├─ params/
│  │  └─ advisor.py           # 参数规则匹配 + 安全声明
│  └─ vision/                 # 多模态镜检模块（P9，独立可插拔）
│     ├─ analyzer.py          # VLM 看镜检图 → 结构化文字描述
│     └─ matcher.py           # 图谱图像检索（以图搜图，可选增强）
├─ data/
│  ├─ rules/
│  │  ├─ fault_tree.yaml      # 故障树（鉴别式决策树 schema，P2 先 Top10，按清单框架增至 ~40 条）
│  │  ├─ param_ranges.yaml    # 参数安全范围（手动维护）
│  │  └─ indicator_species.yaml # 指示生物对照表（P9 镜检模块用）
│  ├─ cases/
│  │  └─ cases.jsonl          # 脱敏历史案例，每行一条
│  ├─ knowledge/              # 用户批量丢文档的目录
│  │  ├─ regulations/         # 排放标准、行业规范
│  │  ├─ equipment/           # 设备手册、保养周期
│  │  ├─ chemicals/           # 药剂 MSDS
│  │  ├─ sop/                 # 厂内 SOP、应急预案
│  │  └─ microscopy/          # 镜检教程文本（P9 镜检模块用）
│  ├─ atlas/                  # 镜检标准图谱图片（P9 图像检索用，gitignore）
│  └─ samples/                # 脱敏样例数据（随仓库公开）
├─ scripts/
│  ├─ ingest.py               # 一键入库：解析→切分→向量化→存 Chroma
│  └─ eval.py                 # 测试用例批量跑分
├─ tests/
│  └─ test_diagnostic.py      # pytest
└─ .github/workflows/ci.yml   # push 时自动跑 pytest
```

---

## 4. 知识库方案（关键决策：不一点点上传）

| 知识类型 | 存放位置 | 维护方式 | 是否手动 |
|---|---|---|---|
| 故障树 | `data/rules/fault_tree.yaml` | 专家手写，~40 条（P2 先 Top10 高频，按清单框架增量补齐） | ✅ 手动（价值最高） |
| 参数范围 | `data/rules/param_ranges.yaml` | 专家手写，10~30 条 | ✅ 手动 |
| 历史案例 | `data/cases/cases.jsonl` | 表格整理后批量导出 | 半自动 |
| 文档资料 | `data/knowledge/**` | 批量放文件 → 跑 `scripts/ingest.py` | ❌ 批量 |

入库命令：

```bash
# 把文档按目录丢进 data/knowledge/ 后执行一次即可
python scripts/ingest.py

# 增量机制：ingest 时记录每个文件的路径+哈希到 vector_db/manifest.json
# 之后随时添加新文档，重跑同一命令，只解析和处理新增/修改的文件，已入库的自动跳过
# 删除文档：python scripts/ingest.py --prune  同步清理已删除文件对应的向量
```

知识库更新还可以在 Streamlit 界面上点"更新知识库"按钮触发，无需命令行。服务运行中添加文档不影响在线使用。

**公开仓库只放 5~10 份脱敏样例文档**。用户克隆后把自己的文档放进 `data/knowledge/`，跑一次 ingest 即可接入私有知识库。

---

## 5. 核心数据流

### 5.1 故障诊断（第一个开发的能力）
```
用户输入现象+水质
  → 规则引擎匹配 fault_tree.yaml（可多条命中）
  → 未命中任何条目 → LLM(+P4后RAG) 兜底推理，输出顶部强制明示低置信度
  → 命中：按 hypotheses 鉴别检查逐个排除，锁定可能原因
  → 检索 cases.jsonl 相似案例
  → 检索向量库相关 SOP/手册段落
  → LLM 汇总，输出结构化结果：
     结论摘要 / 数据可信度 / 可能原因Top3(带置信度)
     分步排查清单(按0-30min、30-120min、2-8h分组)
     临时处置 / 需人工确认项 / 引用来源
```

### 5.2 知识问答
```
问题 → 向量检索 top5 → LLM 仅依据检索内容作答 → 必须引用来源
     → 检索不到则明确回答"知识库暂无，建议转人工"，禁止编造
```

### 5.3 台账生成
```
当日数据(JSON) → Jinja2 模板填充 → 人工确认字段 → 导出 docx
```

### 5.4 参数建议
```
当前水质+工艺参数 → 匹配 param_ranges.yaml → 生成建议卡
  每条包含：目标范围 / 调整动作 / 风险 / 观察指标 / 复测时间
  固定追加：⚠️ 仅人工参考，执行前须经工艺工程师确认
```

### 5.5 多模态镜检诊断（P9 独立模块，发布后增强）
```
镜检图（手机拍显微镜目镜）→ VLM 转结构化文字描述
   {观察描述, 丝状菌丰度, 优势类群, 生物相评价, 图像质量是否足以判断}
        ↓
两条比对路线：
  A. 文字比对（主路径）：描述 → 检索镜检教程知识库 → 生成诊断说明（引用教程依据）
     indicator_species.yaml 匹配指示意义，可直接触发故障树（如丝状菌+++→膨胀分支）
  B. 图像比对（可选增强）：镜检图 embedding → 与 data/atlas/ 标准图谱以图搜图
        ↓
作为额外上下文拼入统一诊断流程（与故障树、案例并列）
```

定位与边界：**辅助描述 + 指示意义提示，不是物种鉴定报告**。VLM 能可靠描述形态（丝状菌丰度、菌胶团状态、可见类群），物种级结论会编造，必须以教程检索结果为准。图像质量不足时如实输出"不足以判断"。

版权红线：真实镜检教程与网络图谱多有版权，公开仓库只放自制/可商用样例；真实教程放 `data/knowledge/private/`、图谱放 `data/atlas/`（均 gitignore）。

---

## 6. 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.11 | |
| LLM | OpenAI 兼容接口 | 本地：Ollama；在线：DeepSeek / Qwen / OpenAI，改 `.env` 即切换 |
| Embedding | 同上 | 本地 Ollama（bge-m3 等）或在线 API |
| Agent | 无框架，函数路由 + LLM function calling | 不引入 LangGraph，够用且好维护 |
| RAG | Chroma + LangChain 切分器 | 支持增量入库；后期量大可换 FAISS/LanceDB |
| 文档解析 | pypdf、python-docx、Markdown | |
| 界面 | Streamlit | `--server.address 0.0.0.0` 监听局域网，手机浏览器直接访问 |
| 数据校验 | Pydantic v2 | |
| 模板 | Jinja2 + python-docx | |
| 测试 | pytest | |
| CI | GitHub Actions | push 自动跑测试 |

---

## 7. 开发阶段（每步结束都可运行）

| 阶段 | 内容 | 完成标志 |
|---|---|---|
| P1 骨架 | git init、目录、.gitignore、requirements、README 框架 | 仓库可克隆 |
| P2 诊断 MVP | fault_tree.yaml（Top10 高频条目，鉴别式 schema + 未命中兜底）+ 诊断 prompt + CLI 可跑 | 命中故障树 → 输出排查清单；未命中 → 输出低置信度声明，不硬编 |
| P3 双模型 | config.py + llm.py，接通本地 Ollama 和在线 API，验证可切换 | 同一问题两种模型都能回答 |
| P4 知识库 | ingest.py（增量）+ retriever.py + 3~5 份脱敏样例文档 | 提问能带引用回答；添加新文档重跑只处理新文件 |
| P5 案例增强 | cases.jsonl 检索接入诊断流程 | 诊断结果引用相似案例 |
| P6 界面 | Streamlit 串起诊断+问答+知识库更新按钮，手机适配 | 📱 手机连局域网打开 http://服务器IP:8501 可完整操作 |
| P7 台账+参数 | 模板渲染 + param_ranges.yaml | 四个能力全部可用 |
| P8 发布 | 测试用例、CI、免责声明、push GitHub | 开源可复现 |
| P9 多模态镜检（独立增强） | vision 模块：VLM 图像描述 + 教程比对诊断说明；路线B图谱检索后做 | 📷 手机传镜检图 → 输出生物相描述 + 指示意义 + 诊断说明 |

---

## 8. 安全与合规

1. **免责声明**（README 显著位置 + 每次参数建议输出末尾）：
   > 本项目仅用于污水处理运维辅助建议，不直接控制 PLC、阀门、泵、加药设备。所有参数建议必须由工艺工程师或值班长确认后方可执行。
2. **密钥管理**：`.env` 不入库，提供 `.env.example`
3. **数据脱敏**：样例文档、案例、台账模板中不得出现真实厂名、坐标、人员、运行数据
4. **引用可溯**：知识问答必须带来源；答不出明确说不知道

---

## 9. 评估（先攒用例，再谈指标）

- 建立 `data/samples/eval_cases.yaml`：20~30 条带标准答案的测试用例
- 诊断：Top3 原因命中率、未命中时低置信度声明覆盖率（红线）；问答：引用正确率、拒答准确率；台账：字段完整率
- 红线指标：自动执行类操作输出次数 = **0**（测试断言）
