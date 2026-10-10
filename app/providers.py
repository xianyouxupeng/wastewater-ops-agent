"""模型供应商管理：内置注册表（OpenAI 兼容端点）+ 本地配置存储。

- 注册表只提供"添加供应商"时的默认值；实际生效的供应商列表存 data/models.json（gitignore，含密钥不入库）
- 界面设置页增删改；功能页通过 get_active_chat_fn() 取当前使用供应商的 chat 函数
"""
import json
import os
import time
from pathlib import Path

STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "models.json"

# 添加供应商下拉框的预置项；key_env = 首次添加时从 .env 自动填入的密钥变量名
PROVIDER_REGISTRY = [
    {"name": "Ollama", "base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b"},
    {"name": "LM Studio", "base_url": "http://localhost:1234/v1", "model": ""},
    {"name": "llama.cpp", "base_url": "http://localhost:8080/v1", "model": ""},
    {"name": "vLLM", "base_url": "http://localhost:8000/v1", "model": ""},
    {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
     "model": "deepseek-chat", "key_env": "DEEPSEEK_API_KEY"},
    {"name": "阿里云百炼", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "model": "qwen-plus", "key_env": "DASHSCOPE_API_KEY"},
    {"name": "硅基流动", "base_url": "https://api.siliconflow.cn/v1",
     "model": "deepseek-ai/DeepSeek-V3", "key_env": "SILICONFLOW_API_KEY"},
    {"name": "火山方舟", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "model": "", "key_env": "ARK_API_KEY"},
    {"name": "Moonshot Kimi", "base_url": "https://api.moonshot.cn/v1",
     "model": "moonshot-v1-8k", "key_env": "MOONSHOT_API_KEY"},
    {"name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model": "glm-4-flash", "key_env": "ZHIPU_API_KEY"},
    {"name": "MiniMax", "base_url": "https://api.minimaxi.chat/v1",
     "model": "abab6.5s-chat", "key_env": "MINIMAX_API_KEY"},
    {"name": "百度千帆", "base_url": "https://qianfan.baidubce.com/v2",
     "model": "", "key_env": "QIANFAN_API_KEY"},
    {"name": "腾讯混元", "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
     "model": "", "key_env": "HUNYUAN_API_KEY"},
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1",
     "model": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"},
    {"name": "Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "model": "gemini-2.0-flash", "key_env": "GEMINI_API_KEY"},
    {"name": "Groq", "base_url": "https://api.groq.com/openai/v1",
     "model": "llama-3.3-70b-versatile", "key_env": "GROQ_API_KEY"},
    {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1",
     "model": "", "key_env": "OPENROUTER_API_KEY"},
    {"name": "NVIDIA NIM", "base_url": "https://integrate.api.nvidia.com/v1",
     "model": "", "key_env": "NVIDIA_API_KEY"},
    {"name": "自定义（OpenAI 兼容）", "base_url": "", "model": ""},
]


def _seed_providers() -> list[dict]:
    """首次运行：以注册表播种（Ollama + 有 env 密钥的在线供应商）"""
    seeded = []
    for item in PROVIDER_REGISTRY:
        key = os.getenv(item.get("key_env", ""), "") if item.get("key_env") else ""
        if not item.get("base_url", "").startswith("http"):
            continue  # "自定义"不预置
        if not item.get("key_env") or key:  # 本地服务直接放行；在线的要有密钥才预置
            seeded.append({"name": item["name"], "base_url": item["base_url"],
                           "api_key": key, "model": item["model"],
                           "context_window": None})
    return seeded


def load_store(path: Path = STORE_PATH) -> dict:
    if not path.exists():
        store = {"active": "Ollama", "providers": _seed_providers()}
        save_store(store, path)
        return store
    return json.loads(path.read_text(encoding="utf-8"))


def save_store(store: dict, path: Path = STORE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def list_providers(path: Path = STORE_PATH) -> list[dict]:
    return load_store(path)["providers"]


def get_active_provider(path: Path = STORE_PATH) -> dict | None:
    store = load_store(path)
    name = store.get("active")
    return next((p for p in store["providers"] if p["name"] == name),
                store["providers"][0] if store["providers"] else None)


def set_active(name: str, path: Path = STORE_PATH) -> None:
    store = load_store(path)
    store["active"] = name
    save_store(store, path)


def upsert_provider(entry: dict, path: Path = STORE_PATH) -> None:
    """按名称新增或更新供应商"""
    store = load_store(path)
    for i, p in enumerate(store["providers"]):
        if p["name"] == entry["name"]:
            store["providers"][i] = entry
            break
    else:
        store["providers"].append(entry)
    save_store(store, path)


def delete_provider(name: str, path: Path = STORE_PATH) -> None:
    store = load_store(path)
    store["providers"] = [p for p in store["providers"] if p["name"] != name]
    if store.get("active") == name:
        store["active"] = store["providers"][0]["name"] if store["providers"] else ""
    save_store(store, path)


def get_active_chat_fn():
    """当前使用供应商绑定的 chat 函数；无可用供应商时返回 (None, None)"""
    provider = get_active_provider()
    if provider is None or not provider.get("model"):
        return None, provider
    from app.agent.llm import get_chat_fn
    return get_chat_fn({"base_url": provider["base_url"],
                        "api_key": provider.get("api_key") or "ollama",
                        "model": provider["model"]}), provider


def ping(provider: dict, question: str = "请只回复：OK") -> tuple[bool, float, str]:
    """连通性测试：返回 (是否成功, 耗时秒, 回答或错误摘要)"""
    from openai import OpenAI
    client = OpenAI(base_url=provider["base_url"],
                    api_key=provider.get("api_key") or "ollama", timeout=30)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=provider["model"],
            messages=[{"role": "user", "content": question}],
            max_tokens=16, temperature=0)
        return True, time.time() - t0, (resp.choices[0].message.content or "").strip()[:60]
    except Exception as e:
        return False, time.time() - t0, f"{type(e).__name__}: {e}"
