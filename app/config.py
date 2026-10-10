import os

from dotenv import load_dotenv

load_dotenv()

# LLM 与 Embedding 分开配置（见 .env.example），兼容旧 OPENAI_* 写法
BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
