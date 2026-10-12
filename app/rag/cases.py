"""历史案例库：jsonl 案例向量化入库（独立 collection）+ 相似案例检索 + 沉淀写入"""
import hashlib
import json
from datetime import date
from pathlib import Path

from app.rag.vectorstore import get_client, embed_texts

CASES_FILE = Path("data/cases/cases.jsonl")
COLLECTION = "cases"
MANIFEST = Path("vector_db/cases_manifest.json")  # {案例id: 内容md5}
K_TEXT = "现象 关键参数 原因 处置"  # 参与向量化的字段


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    if not path.exists():
        return []
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def case_text(case: dict) -> str:
    """拼案例向量化文本：现象+参数+原因+处置最关键，结果与日期作补充"""
    parts = [case.get("id", ""), case.get("现象", ""),
             json.dumps(case.get("关键参数", {}), ensure_ascii=False),
             case.get("原因", ""), case.get("处置", ""),
             case.get("结果", "")]
    return "\n".join(str(p) for p in parts if p)


def _embed_text(case: dict) -> str:
    return "\n".join([case.get("现象", ""),
                      json.dumps(case.get("关键参数", {}), ensure_ascii=False),
                      case.get("原因", ""), case.get("处置", "")])


def ingest_cases(cases_file: Path = CASES_FILE) -> dict:
    """增量入库案例（内容 md5 比对，只处理新增/修改）。返回统计"""
    collection = get_client().get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"})
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) \
        if MANIFEST.exists() else {}

    cases = load_cases(cases_file)
    changed = [c for c in cases
               if manifest.get(c.get("id", "")) != hashlib.md5(
                   case_text(c).encode("utf-8")).hexdigest()]
    valid_ids = {c.get("id", "") for c in cases}
    removed = [cid for cid in manifest if cid not in valid_ids]

    for cid in removed:
        collection.delete(where={"id": cid})
        manifest.pop(cid)

    if changed:
        embeddings = embed_texts([_embed_text(c) for c in changed])
        collection.upsert(
            ids=[c["id"] for c in changed],
            documents=[case_text(c) for c in changed],
            embeddings=embeddings,
            metadatas=[{"id": c["id"], "date": c.get("日期", "")}
                       for c in changed],
        )
        for c in changed:
            manifest[c["id"]] = hashlib.md5(
                case_text(c).encode("utf-8")).hexdigest()

    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return {"changed": [c.get("id") for c in changed], "removed": removed}


def add_case(case: dict, path: Path = CASES_FILE) -> dict:
    """追加一条案例（L4 经验记忆：诊断结论经人工确认后沉淀）。

    缺省字段自动补全：id 沿用 C00X 自动编号、日期默认今天、来源标记"诊断沉淀"。
    只写 jsonl 不向量化——入库后由 更新知识库/下次 ingest_cases 增量嵌入，
    写入失败不影响诊断主流程（调用方负责提示）。
    """
    cases = load_cases(path)
    if not case.get("id"):
        nums = [int(c["id"][1:]) for c in cases
                if str(c.get("id", "")).startswith("C")
                and c["id"][1:].isdigit()]
        case["id"] = f"C{max(nums, default=0) + 1:03d}"
    case.setdefault("日期", date.today().isoformat())
    case.setdefault("来源", "诊断沉淀")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")
    return case


def format_case(case: dict) -> str:
    """单条案例的人类可读摘要（拼入 prompt / 输出段落用）"""
    params = "，".join(f"{k}={v}" for k, v in case.get("关键参数", {}).items())
    return (f"{case['id']}（{case.get('日期', '日期不详')}）"
            f"现象：{case.get('现象', '')}；关键参数：{params}；"
            f"原因：{case.get('原因', '')}；处置：{case.get('处置', '')}；"
            f"结果：{case.get('结果', '')}")


def retrieve_cases(query: str, k: int = 3) -> list[dict]:
    """检索 top-k 相似案例，返回 [{'case': dict, 'distance': float}]"""
    client = get_client()
    try:
        collection = client.get_collection(COLLECTION)
    except Exception:
        return []
    if collection.count() == 0:
        return []
    embedding = embed_texts([query])[0]
    result = collection.query(query_embeddings=[embedding],
                              n_results=min(k, collection.count()))
    hits = []
    for meta, dist in zip(result["metadatas"][0], result["distances"][0]):
        if dist > 0.4:  # 案例库小且条目间相似度高，阈值比知识库(1.2)更严：>0.4 视为不相关
            break
        case = next((c for c in load_cases() if c.get("id") == meta["id"]), None)
        if case:
            hits.append({"case": case, "distance": dist})
    return hits
