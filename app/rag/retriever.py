"""检索：查询向量库 top-k，返回文档片段 + 来源文件名"""
from app.rag.vectorstore import embed_texts, get_collection

# cosine 距离超过该值的片段视为不相关（防止无关问题的弱相似片段干扰 LLM）
MAX_DISTANCE = 1.2


def retrieve(query: str, k: int = 5) -> list[dict]:
    """返回 [{'text', 'source', 'distance'}]；库不存在、为空或全部不相关返回空列表"""
    collection = get_collection(create=False)
    if collection is None:
        return []
    if collection.count() == 0:
        return []
    embedding = embed_texts([query])[0]
    result = collection.query(query_embeddings=[embedding],
                              n_results=min(k, collection.count()))
    hits = []
    for doc, meta, dist in zip(result["documents"][0],
                               result["metadatas"][0],
                               result["distances"][0]):
        if dist > MAX_DISTANCE:
            break  # 结果按距离升序，后面只会更差
        hits.append({"text": doc, "source": meta["source"], "distance": dist})
    return hits
