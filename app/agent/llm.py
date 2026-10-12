"""OpenAI 兼容客户端封装：本地/在线统一入口，改 .env 即切换"""
from openai import OpenAI

from app.config import BASE_URL, API_KEY, LLM_MODEL


def get_client(base_url: str | None = None, api_key: str | None = None) -> OpenAI:
    return OpenAI(base_url=base_url or BASE_URL, api_key=api_key or API_KEY)


def chat(messages: list, model: str | None = None, base_url: str | None = None,
         api_key: str | None = None) -> str:
    client = get_client(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model or LLM_MODEL,
        messages=messages,
        temperature=0.3,
    )
    if not resp.choices:
        # 模型服务过载/重启时可能返回畸形响应（如 Ollama 忙于加载模型）
        raise RuntimeError("模型返回了空响应，请重试；若持续出现请检查模型服务是否繁忙")
    return resp.choices[0].message.content or ""


def chat_message(messages: list, tools: list | None = None, model: str | None = None,
                 base_url: str | None = None, api_key: str | None = None):
    """消息级 chat（V2.3 Agent 用）：支持 tools 参数，返回原始 message 对象
    （含 .content 与 .tool_calls，结构化输出由 API 层保证）。"""
    client = get_client(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model or LLM_MODEL,
        messages=messages,
        tools=tools,
        temperature=0.3,
    )
    if not resp.choices:
        raise RuntimeError("模型返回了空响应，请重试；若持续出现请检查模型服务是否繁忙")
    return resp.choices[0].message


def get_chat_fn(preset: dict):
    """按模型预设生成绑定了供应商参数的 chat 函数。
    用法：diagnose(text, chat_fn=get_chat_fn(MODEL_PRESETS["本地 Qwen2.5"]))"""
    def _chat(messages: list) -> str:
        return chat(
            messages,
            model=preset["model"],
            base_url=preset["base_url"],
            api_key=preset.get("api_key") or None,
        )
    return _chat


def get_message_fn(preset: dict):
    """绑定供应商参数的消息级函数 fn(messages, tools=None) → message（Agent 循环用）"""
    def _fn(messages: list, tools: list | None = None):
        return chat_message(
            messages,
            tools=tools,
            model=preset["model"],
            base_url=preset["base_url"],
            api_key=preset.get("api_key") or None,
        )
    return _fn
