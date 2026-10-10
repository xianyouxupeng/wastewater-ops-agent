"""知识问答链：检索结果拼进 prompt，仅依据资料回答并引用来源，无结果时明确拒答"""
from app.rag.retriever import retrieve

QA_SYSTEM = """你是污水处理厂的知识问答助手。仅依据给定的【参考资料】回答问题，并标注来源编号，如 [1]。
回答要求：
- 综合多个来源时逐条引用对应编号
- 资料中没有的内容不得编造，明确回答"知识库中暂无相关内容"
- 涉及投药量、工艺调整等操作时提醒：执行前须经工艺工程师确认"""

NO_RESULT_REPLY = "知识库中暂无相关内容。请先将文档放入 data/knowledge/ 并运行 `python scripts/ingest.py`（或在界面点击『更新知识库』）。"


def build_messages(question: str, hits: list[dict]) -> list[dict]:
    contexts = "\n\n".join(
        f"[{i + 1}] 来源: {h['source']}\n{h['text']}" for i, h in enumerate(hits))
    return [
        {"role": "system", "content": QA_SYSTEM},
        {"role": "user", "content": f"【参考资料】\n{contexts}\n\n【问题】\n{question}"},
    ]


def ask(question: str, k: int = 5, chat_fn=None) -> str:
    """知识问答主入口。chat_fn 可注入替换（测试/界面切换模型）"""
    hits = retrieve(question, k=k)
    if not hits:
        return NO_RESULT_REPLY
    if chat_fn is None:
        from app.agent.llm import chat
        chat_fn = chat
    return chat_fn(build_messages(question, hits))
