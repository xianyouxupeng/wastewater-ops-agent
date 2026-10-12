"""诊断 Agent 的工具箱（V2.3 MVP 四工具）：schema 定义 + 执行分发。

设计红线：
- 所有计算类操作必须走工具内的硬编码逻辑，LLM 只决定"调什么、怎么解释结果"
- ask_user 不是可执行工具——agent.py 循环里把它拦截成向用户提问（Streamlit 问题卡），
  不在本文件执行
- 每加一个工具 = 注册一个 schema + run_tool 分支，循环本体不动
"""
from app.memory import runtime as runtime_mem

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "query_runtime",
        "description": "查询本厂最近运行台账（实测参数、趋势、超标记录）。"
                       "系统已自动注入近 7 天摘要，仅当需要更早数据或特定参数细节时调用。",
        "parameters": {"type": "object", "properties": {
            "params": {"type": "array", "items": {"type": "string"},
                       "description": "关注的参数名，如 [\"出水氨氮\", \"DO\"]；留空返回全部"},
            "days": {"type": "integer", "description": "回看天数，默认 7"}},
        }}},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "检索厂内知识库（规程/SOP/教程），返回相关片段及来源文件名。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "检索关键词或问题"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "search_cases",
        "description": "检索本厂历史相似案例（现象→原因→处置→结果实录）。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "现象描述"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "ask_user",
        "description": "向用户提一个最关键的鉴别问题。一次只问一个；"
                       "问题必须优先来自命中故障树的鉴别检查项（distinguishing_tests）。",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "具体的鉴别问题"}},
            "required": ["question"]}}},
]

TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}
EXECUTABLE = TOOL_NAMES - {"ask_user"}


def run_tool(name: str, args: dict | None, *, runtime_fn=None,
             knowledge_fn=None, cases_fn=None) -> str:
    """执行工具并返回文本结果。检索类失败不抛异常——返回提示文本让模型自行换路。
    各 fn 可注入替换（测试不依赖台账文件/向量库）。"""
    args = args or {}
    try:
        if name == "query_runtime":
            fn = runtime_fn or _default_runtime
            return fn(args.get("params") or [], int(args.get("days") or 7))
        if name == "search_knowledge":
            fn = knowledge_fn or _default_knowledge
            return fn(str(args.get("query", "")))
        if name == "search_cases":
            fn = cases_fn or _default_cases
            return fn(str(args.get("query", "")))
    except Exception as e:  # 常见：embedding 服务未启动、文件损坏
        return f"工具执行失败：{type(e).__name__}: {e}（请改用其他方式获取该信息）"
    return f"未知工具：{name}（可用工具：{', '.join(sorted(TOOL_NAMES))}）"


def _default_runtime(params: list, days: int) -> str:
    entries = runtime_mem.get_recent_params(days=days)
    if not entries:
        return "台账暂无最近运行数据。"
    if not params:
        return runtime_mem.runtime_block(entries=entries, days=days)
    # 按参数名过滤：中文标签子串匹配（"氨氮" 命中 进水氨氮/出水氨氮）
    wanted = [k for k, label in runtime_mem.FIELD_LABELS.items()
              if any(p.strip() in label for p in params if p.strip())]
    lines = [f"【最近 {days} 天台账（参数：{'、'.join(params)}）】"]
    for e in entries:
        parts = [f"{runtime_mem.FIELD_LABELS[k]}={e[k]}" for k in wanted if e.get(k)]
        if parts:
            lines.append(f"- {e.get('date', '')}：" + "，".join(parts))
    return "\n".join(lines) if len(lines) > 1 else "台账中未找到所查参数。"


def _default_knowledge(query: str) -> str:
    from app.rag.retriever import retrieve
    hits = retrieve(query, k=3)
    if not hits:
        return "知识库中无相关内容。"
    return "\n\n".join(f"[来源: {h['source']}]\n{h['text']}" for h in hits)


def _default_cases(query: str) -> str:
    from app.rag.cases import format_case, retrieve_cases
    hits = retrieve_cases(query, k=3)
    if not hits:
        return "无相似历史案例。"
    return "\n".join(f"- {format_case(h['case'])}" for h in hits)
