"""OpenAI 兼容客户端封装：本地/在线统一入口，改 .env 即切换"""
from openai import OpenAI

from app.config import BASE_URL, API_KEY, LLM_MODEL


def get_client(base_url: str | None = None, api_key: str | None = None) -> OpenAI:
    return OpenAI(base_url=base_url or BASE_URL, api_key=api_key or API_KEY)


def chat(messages: list, model: str | None = None, base_url: str | None = None) -> str:
    client = get_client(base_url=base_url)
    resp = client.chat.completions.create(
        model=model or LLM_MODEL,
        messages=messages,
        temperature=0.3,
    )
    return resp.choices[0].message.content
