"""L1 会话记忆：历史消息裁剪与文本化（问答/诊断共用）。

V1 的问题：界面展示了历史但没喂回模型，每轮互相失忆。
这里统一做两件事：trim 裁出最近 N 条防 prompt 膨胀；history_text 把历史
拼成文本块给一次性对话（如诊断）注入。多轮 messages 注入直接用 trim。
"""
MAX_INJECT = 12  # 注入 prompt 的最近消息条数上限


def trim(history: list[dict] | None, keep: int = MAX_INJECT) -> list[dict]:
    """保留最近 keep 条（原始 messages 列表，注入 chat messages 用）"""
    return list(history[-keep:]) if history else []


def history_text(history: list[dict] | None, keep: int = MAX_INJECT) -> str:
    """历史 → 文本块（拼进 user content 的一次性注入用）。空返回空串"""
    if not history:
        return ""
    role_names = {"user": "用户", "assistant": "助手"}
    lines = [f"{role_names.get(m.get('role'), m.get('role'))}：{m.get('content', '')}"
             for m in trim(history, keep)]
    return "【本轮之前的对话（供上下文衔接，无需逐条回应）】\n" + "\n".join(lines)
