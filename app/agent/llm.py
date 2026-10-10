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
    return resp.choices[0].message.content


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
