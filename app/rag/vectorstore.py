"""向量库封装：Chroma 持久化 + Embedding 调用（OpenAI 兼容接口，默认本地 Ollama bge-m3）"""
from openai import OpenAI
import chromadb

from app.config import EMBED_BASE_URL, EMBED_API_KEY, EMBED_MODEL

DB_DIR = "vector_db"
COLLECTION = "knowledge"


def get_client() -> chromadb.api.ClientAPI:
    return chromadb.PersistentClient(DB_DIR)


def get_collection(create: bool = True):
    """返回知识库 collection；create=False 时库不存在返回 None（问答端优雅拒答用）"""
    client = get_client()
    try:
        return client.get_collection(COLLECTION)
    except Exception:
        if create:
            return client.get_or_create_collection(
                COLLECTION, metadata={"hnsw:space": "cosine"})
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化。Ollama /v1/embeddings 支持数组输入；异常时逐条兜底"""
    client = OpenAI(base_url=EMBED_BASE_URL,
                    api_key=EMBED_API_KEY or "ollama")
    try:
        resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [item.embedding for item in resp.data]
    except Exception:
        return [client.embeddings.create(model=EMBED_MODEL, input=[t])
                .data[0].embedding for t in texts]
