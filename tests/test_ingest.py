"""知识库增量入库逻辑测试（不依赖 LLM/网络）

文档要求必测：ingest 增量逻辑——第二次跑处理 0 个文件。
用临时 chroma + 固定向量替换真实向量库，不动项目数据。
"""
import chromadb
import pytest

import app.rag.ingest as ingest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """隔离的入库环境：临时文档目录 + 临时向量库 + 固定向量"""
    kb = tmp_path / "knowledge"
    kb.mkdir()
    manifest = tmp_path / "manifest.json"
    col = chromadb.PersistentClient(str(tmp_path / "db")).get_or_create_collection(
        "knowledge", metadata={"hnsw:space": "cosine"})
    monkeypatch.setattr(ingest, "get_collection", lambda create=True: col)
    monkeypatch.setattr(ingest, "embed_texts",
                        lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts])
    return {"kb": kb, "manifest": manifest, "col": col}


def _write(kb, name, content):
    p = kb / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_first_ingest_processes_all(env):
    _write(env["kb"], "a.md", "# 文档A\n" + "内容" * 100)
    stats = ingest.ingest_knowledge(env["kb"], env["manifest"])
    assert len(stats["changed"]) == 1
    assert stats["chunks"] > 0
    assert env["col"].count() > 0


def test_second_ingest_processes_zero(env):
    """必测项：第二次跑同样内容，处理 0 个文件"""
    _write(env["kb"], "a.md", "# 文档A\n" + "内容" * 100)
    ingest.ingest_knowledge(env["kb"], env["manifest"])
    count = env["col"].count()

    stats = ingest.ingest_knowledge(env["kb"], env["manifest"])
    assert stats["changed"] == []
    assert stats["removed"] == []
    assert env["col"].count() == count  # 向量也没有重复写入


def test_modified_file_is_reingested(env):
    p = _write(env["kb"], "a.md", "旧内容" * 100)
    ingest.ingest_knowledge(env["kb"], env["manifest"])
    count = env["col"].count()

    p.write_text("新内容" * 100, encoding="utf-8")  # 内容变化 → md5 变化
    stats = ingest.ingest_knowledge(env["kb"], env["manifest"])
    assert len(stats["changed"]) == 1
    assert env["col"].count() == count  # 旧向量先删后加，总量不变


def test_deleted_file_vectors_pruned(env):
    """必测项延伸：删文件后跑 ingest，对应向量自动清理"""
    p = _write(env["kb"], "a.md", "内容" * 100)
    ingest.ingest_knowledge(env["kb"], env["manifest"])
    assert env["col"].count() > 0

    p.unlink()
    stats = ingest.ingest_knowledge(env["kb"], env["manifest"])
    assert len(stats["removed"]) == 1
    assert env["col"].count() == 0


def test_unsupported_suffix_ignored(env):
    _write(env["kb"], "图片.png", "binary")
    stats = ingest.ingest_knowledge(env["kb"], env["manifest"])
    assert stats["changed"] == []
