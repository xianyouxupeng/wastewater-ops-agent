"""增量入库：扫描 data/knowledge/，只处理新增/修改的文件（md5 比对），支持清理已删除文件"""
import hashlib
import json
from pathlib import Path

from app.rag.parsers import SUPPORTED_SUFFIXES, parse_file, split_text
from app.rag.vectorstore import get_collection, embed_texts

KNOWLEDGE_DIR = Path("data/knowledge")
MANIFEST = Path("vector_db/manifest.json")  # 记录已入库文件 {路径: md5}


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
        if manifest.get(str(path)) == digest:
            continue  # 未变化，跳过
        changed.append((path, digest))

    removed = [k for k in manifest if not Path(k).exists()]  # 清理已删除文件的向量

    for key in removed:
        collection.delete(where={"source": key})
        manifest.pop(key)

    total_chunks = 0
    for path, digest in changed:
        if str(path) in manifest:  # 内容被修改 → 先删旧向量
            collection.delete(where={"source": str(path)})
        chunks = split_text(parse_file(path))
        if not chunks:
            manifest[str(path)] = digest  # 空文档也记账，避免反复重扫
            continue
        embeddings = embed_texts(chunks)
        ids = [f"{path}#{i}" for i in range(len(chunks))]
        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"source": str(path), "chunk": i} for i in range(len(chunks))],
        )
        manifest[str(path)] = digest
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


if __name__ == "__main__":
    main()
