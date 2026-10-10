"""增量入库：扫描 data/knowledge/，只处理新增/修改的文件（md5 比对），支持清理已删除文件"""
import hashlib
import json
from pathlib import Path

from app.rag.parsers import SUPPORTED_SUFFIXES, parse_file, split_text
from app.rag.vectorstore import get_collection, embed_texts

KNOWLEDGE_DIR = Path("data/knowledge")
MANIFEST = Path("vector_db/manifest.json")  # 记录已入库文件 {路径: md5}
ROOT = Path(__file__).resolve().parents[2]


def store_key(path: Path) -> str:
    """manifest/向量库 metadata 的规范键：相对项目根目录（界面传绝对路径也不产生重复键）"""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:  # 不在项目内（如测试临时目录）
        return str(path)


def _key_exists(key: str) -> bool:
    p = Path(key)
    return (p if p.is_absolute() else ROOT / p).exists()


def file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def ingest_knowledge(knowledge_dir: Path = KNOWLEDGE_DIR,
                     manifest_path: Path = MANIFEST) -> dict:
    """主流程，返回统计。P6 界面"更新知识库"按钮直接调用本函数"""
    manifest = load_manifest(manifest_path)
    collection = get_collection()
    changed: list[tuple[Path, str]] = []
    removed: list[str] = []

    for path in sorted(knowledge_dir.rglob("*.*")):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        digest = file_md5(path)
        if manifest.get(store_key(path)) == digest:
            continue  # 未变化，跳过
        changed.append((path, digest))

    removed = [k for k in manifest if not _key_exists(k)]  # 清理已删除文件的向量

    for key in removed:
        collection.delete(where={"source": key})
        manifest.pop(key)

    total_chunks = 0
    for path, digest in changed:
        key = store_key(path)
        if key in manifest:  # 内容被修改 → 先删旧向量
            collection.delete(where={"source": key})
        chunks = split_text(parse_file(path))
        if not chunks:
            manifest[key] = digest  # 空文档也记账，避免反复重扫
            continue
        embeddings = embed_texts(chunks)
        ids = [f"{key}#{i}" for i in range(len(chunks))]
        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"source": key, "chunk": i} for i in range(len(chunks))],
        )
        manifest[key] = digest
        total_chunks += len(chunks)

    manifest_path.parent.mkdir(exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    return {"changed": [str(p) for p, _ in changed],
            "removed": removed, "chunks": total_chunks}


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    stats = ingest_knowledge()
    print(f"新增/更新 {len(stats['changed'])} 个文件（{stats['chunks']} 个片段），"
          f"清理 {len(stats['removed'])} 个，其余跳过")
    for name in stats["changed"]:
        print(f"  + {name}")
    for name in stats["removed"]:
        print(f"  - {name}")

    from app.rag.cases import ingest_cases
    case_stats = ingest_cases()
    if case_stats["changed"] or case_stats["removed"]:
        print(f"案例库：新增/更新 {len(case_stats['changed'])} 条，"
              f"清理 {len(case_stats['removed'])} 条")
        for cid in case_stats["changed"]:
            print(f"  + 案例 {cid}")


if __name__ == "__main__":
    main()
