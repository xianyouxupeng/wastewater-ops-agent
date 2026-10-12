"""知识问答链：检索结果拼进 prompt，仅依据资料回答并引用来源，无结果时明确拒答。
V2.1 起注入厂情档案（L2）与会话历史（L1），回答可结合本厂工况与上文。"""
from app.memory.plant import plant_profile_block
from app.memory.session import trim
from app.rag.retriever import retrieve

QA_SYSTEM = """你是污水处理厂的知识问答助手。仅依据给定的【参考资料】回答问题，并标注来源编号，如 [1]。
回答要求：
- 综合多个来源时逐条引用对应编号
- 资料中没有的内容不得编造，明确回答"知识库中暂无相关内容\"
- 若输入含【本厂档案】或【本轮之前的对话】，回答时结合本厂工况与上下文；
  本厂信息不需要来源编号，但知识性结论仍须标注来源"""

# 操作类提醒由代码按关键词判断（LLM 判断不稳定），宁可误加不可漏加
OP_KEYWORDS = ("投加", "投药", "加药", "药剂", "剂量", "药耗", "启停", "开机",
               "停机", "启机", "调节", "调大", "调小", "设定", "开度", "阀门",
               "频率", "排泥", "回流比", "怎么调", "如何操作", "操作步骤")
OP_REMINDER = "\n\n⚠️ 涉及现场操作，执行前须经工艺工程师或值班长确认。"


def _needs_op_reminder(*texts: str) -> bool:
    return any(k in t for t in texts for k in OP_KEYWORDS)

NO_RESULT_REPLY = "知识库中暂无相关内容。请先将文档放入 data/knowledge/ 并运行 `python scripts/ingest.py`（或在界面点击『更新知识库』）。"


def build_messages(question: str, hits: list[dict],
                   plant_block: str = "",
                   history: list[dict] | None = None) -> list[dict]:
    contexts = "\n\n".join(
        f"[{i + 1}] 来源: {h['source']}\n{h['text']}" for i, h in enumerate(hits))
    content = f"【参考资料】\n{contexts}\n\n【问题】\n{question}"
    if plant_block:
        content = f"{content}\n\n{plant_block}"
    # 历史 messages 插在 system 与本轮 user 之间，裁剪防 prompt 膨胀
    return [
        {"role": "system", "content": QA_SYSTEM},
        *trim(history),
        {"role": "user", "content": content},
    ]


def ask(question: str, k: int = 5, chat_fn=None,
        return_sources: bool = False,
        history: list[dict] | None = None) -> str | tuple[str, list[dict]]:
    """知识问答主入口。chat_fn 可注入替换（测试/界面切换模型）。

    return_sources=True 时返回 (回答, 检索片段列表)，界面据此展示 [n] 对应的来源文件。
    history 为本轮之前的会话消息列表（注入模型，仅保留最近若干条）。
    """
    hits = retrieve(question, k=k)
    if not hits:
        answer = NO_RESULT_REPLY
    else:
        if chat_fn is None:
            from app.agent.llm import chat
            chat_fn = chat
        try:  # 档案加载失败不中断问答，静默跳过注入
            plant = plant_profile_block()
        except Exception:
            plant = ""
        answer = chat_fn(build_messages(question, hits,
                                        plant_block=plant, history=history))
        if _needs_op_reminder(question, answer):
            answer += OP_REMINDER
    return (answer, hits) if return_sources else answer
