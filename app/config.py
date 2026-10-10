import os

from dotenv import load_dotenv

load_dotenv()

# LLM 与 Embedding 分开配置（见 .env.example），兼容旧 OPENAI_* 写法
BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# Embedding（知识库向量化），默认本地 Ollama bge-m3
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "http://localhost:11434/v1")
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "ollama")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

# ===== 多模型注册表（P3 双通道 / P6 界面下拉框共用）=====
# 在线模型密钥从 .env 读：加一行 DEEPSEEK_API_KEY=sk-xxx 即可启用在线预设
MODEL_PRESETS = {
    "在线 DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "model": "deepseek-chat",
    },
    "本地 Qwen2.5": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",  # 本地不校验，占位
        "model": os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b"),
    },
}
