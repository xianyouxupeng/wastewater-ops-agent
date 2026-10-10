"""故障诊断引擎：故障树匹配 → 命中拼树生成报告 / 未命中走兜底路径"""
from pathlib import Path

import yaml

from app.agent.llm import chat
from app.agent.prompts import DIAGNOSIS_SYSTEM, FALLBACK_SYSTEM

RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "fault_tree.yaml"

# 未命中兜底声明：禁止硬编，输出顶部必须带此提示（P8 有纯函数测试断言）
FALLBACK_WARNING = "⚠️ 未匹配到故障树条目，以下为低置信度推理，仅供人工参考"


def load_fault_trees(path: Path = RULES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def match_trees(user_input: str, trees: list[dict]) -> list[dict]:
    """现象关键词包含匹配（MVP 用子串匹配，P4 后可叠加语义检索）。
    命中数多的排前，允许多条命中；未命中返回空列表。"""
    scored = []
    for tree in trees:
        score = sum(1 for kw in tree["phenomenon"] if kw in user_input)
        if score:
            scored.append((score, tree))
    scored.sort(key=lambda pair: -pair[0])
    return [tree for _, tree in scored]


def build_messages(user_input: str, matched: list[dict]) -> list[dict]:
    """按命中与否组装 prompt：命中拼树，未命中走兜底 prompt + 知识库检索增强"""
    if matched:
        tree_text = yaml.dump(matched, allow_unicode=True, sort_keys=False)
        content = f"【命中的故障树条目】\n{tree_text}\n\n【用户描述】\n{user_input}"
        system = DIAGNOSIS_SYSTEM
    else:
        # P4 起兜底路径升级为 LLM + RAG：检索到的资料作为参考上下文，
        # 检索失败或无结果时静默退回纯 LLM（保持原行为）
        context = _kb_context(user_input)
        content = user_input if not context else f"{user_input}\n\n{context}"
        system = FALLBACK_SYSTEM
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]


def _kb_context(user_input: str, k: int = 3) -> str:
    """从知识库检索相关片段拼为参考资料段；任何异常静默返回空"""
    try:
        from app.rag.retriever import retrieve
        hits = retrieve(user_input, k=k)
        if not hits:
            return ""
        refs = "\n\n".join(f"[来源: {h['source']}]\n{h['text']}" for h in hits)
        return f"【知识库参考资料（供参考，注意甄别适用性）】\n{refs}"
    except Exception:
        return ""


def diagnose(user_input: str, *, chat_fn=chat) -> str:
    """诊断主入口。chat_fn 可注入替换（测试不依赖LLM、界面可按需切换模型）"""
    matched = match_trees(user_input, load_fault_trees())
    answer = chat_fn(build_messages(user_input, matched))
    if not matched:
        return f"{FALLBACK_WARNING}\n\n{answer}"
    return answer
