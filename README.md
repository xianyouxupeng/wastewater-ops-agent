# 污水处理运维助手 (wastewater-ops-agent)

> 厂站运维 AI 助手：故障诊断 · 镜检识图 · 知识问答 · 台账生成 · 参数建议
> 支持本地模型（Ollama，数据不出厂）与在线 API 双通道切换，手机浏览器直接当 App 用。

<!-- TODO: 截图放 .github/screenshots/ 并取消注释
![手机诊断界面](.github/screenshots/mobile.png)
![镜检诊断](.github/screenshots/vision.png)
-->

## 功能

| 功能 | 说明 |
|---|---|
| 🔧 故障诊断 | 鉴别式故障树（Top10 高频故障，含复合条件与鉴别检查）+ LLM 兜底；未命中时明示低置信度，不硬编 |
| 📷 镜检诊断 | 手机拍显微镜目镜 → 视觉模型出结构化描述（丰度分级/优势类群）→ 对照镜检教程给出带引用的解读；丝状菌 ≥+++ 一键转入污泥膨胀排查 |
| 📚 知识问答 | 文档增量入库（md/txt/pdf/docx），回答引用来源文件，知识库没有的明确拒答不编造 |
| 📋 台账生成 | 表单录入当日数据 → Jinja2 模板 → 一键导出 Word |
| ⚙️ 参数建议 | 按规则给目标范围/调整动作/风险/观察指标/复测时间，末尾固定免责声明 |
| 📱 手机访问 | Streamlit 监听局域网，同 Wi-Fi 手机浏览器即用 |
| 🔀 双模型切换 | 界面下拉切换本地 Ollama / 在线 API（DeepSeek、百炼、智谱等 19 家预设），支持视觉模型独立配置 |

## 快速开始

```bash
# 1. 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 2. 配置模型：复制 .env.example 为 .env，按注释填写（本地 Ollama 或在线 API）

# 3. 本地模型（可选，用本地模式时安装）
ollama pull qwen2.5:7b && ollama pull bge-m3 && ollama pull qwen2.5vl:7b

# 4. 启动
streamlit run app/main.py --server.address 0.0.0.0 --server.port 8501
```

手机访问：同 Wi-Fi 浏览器打开 `http://电脑IP:8501`（Windows 需放行防火墙，一条命令见 `使用方法.md`）。

**详细操作手册（面向运行人员）见 [使用方法.md](使用方法.md)**，含每个功能的使用方式与常见问题排查。

## 模型配置（二选一或混搭）

所有供应商走 OpenAI 兼容接口，只换 `BASE_URL / KEY / MODEL`，代码零改动：

```ini
# 在线（例 DeepSeek）
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=deepseek-chat

# 本地 Ollama（数据不出厂）
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:7b

# Embedding（知识库向量化，独立配置可混搭）
EMBED_BASE_URL=http://localhost:11434/v1
EMBED_MODEL=bge-m3
```

也可以在界面「设置 → 模型」里增删切换（存本地 `data/models.json`，密钥不出本机）。
视觉模型在「设置 → 视觉模型」单独配置。DeepSeek 无 embedding 与视觉接口，需要时混搭其他供应商。

## 知识库：随时增量添加

1. 文档拖进界面「知识库 → 上传文档」（或放进 `data/knowledge/` 对应子目录）
2. 自动切割、嵌入、入库；**增量处理**——只处理新增/修改的文件，已有内容秒过
3. 删除文档：界面点删除（文件+向量一并清理），或删文件后跑一次更新
4. 问答自动引用来源文件名；知识库没有的内容明确拒答

> 图片型（扫描）PDF 文字提取不出来，优先用文字版 PDF / Word，或整理成 md/txt。

## 项目结构

```
app/
├── main.py            # Streamlit 入口（st.navigation 多页面）
├── agent/llm.py       # OpenAI 兼容客户端（本地/在线统一）
├── diagnostic/        # 故障树匹配 + 诊断引擎
├── vision/            # P9 镜检诊断（自包含模块，删除不影响其余功能）
├── rag/               # 向量库 + 增量入库 + 检索问答
├── ledger/            # 台账生成（Jinja2 + python-docx）
├── params/            # 参数建议（规则引擎）
└── pages/             # 各功能页面
data/
├── knowledge/         # 知识库文档（private/ 已 gitignore，放内部资料）
├── rules/             # fault_tree.yaml 故障树 / param_ranges.yaml 参数规则 / indicator_species.yaml 指示生物
└── cases/             # 历史案例
tests/                 # pytest 纯函数测试（52 个，不依赖网络/LLM）
```

## 测试

```bash
pytest tests/ -v
```

全部为纯函数测试（LLM/向量库均可注入替换），无网络依赖。

## 免责声明

本工具所有输出（诊断结论、排查清单、处置建议、参数建议、镜检解读）**仅供运行参考**，
不构成操作指令。执行任何现场操作前，必须经工艺工程师或值班长确认。
模型可能出错，请始终以现场实测数据和专业判断为准。

## License

[MIT](LICENSE)
