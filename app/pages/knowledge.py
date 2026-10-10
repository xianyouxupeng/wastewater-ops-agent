"""📁 知识库页：文档清单（位置/大小/时间）+ 上传入库 + 使用说明"""
import time
from pathlib import Path

import streamlit as st

from app.rag.parsers import SUPPORTED_SUFFIXES
from app.rag.ingest import store_key, ingest_knowledge

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"

SUBDIRS = ["sop", "regulations", "equipment", "chemicals", "uploads"]


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def _ingested_count() -> int:
    manifest = ROOT / "vector_db" / "manifest.json"
    if not manifest.exists():
        return 0
    import json
    try:
        return len(json.loads(manifest.read_text(encoding="utf-8")))
    except Exception:
        return 0


def _chunk_count() -> int | None:
    try:
        from app.rag.vectorstore import get_collection
        collection = get_collection(create=False)
        return collection.count() if collection is not None else None
    except Exception:
        return None


@st.dialog("⬆️ 上传文档", width="large")
def upload_dialog():
    """拖入文件 → 选目标子目录 → 保存并自动切割/嵌入/入库"""
    st.caption("把文档拖进下面框里（md / txt / pdf / docx，可多选），"
               "选好存放目录后自动切割、嵌入并入库")
    uploads = st.file_uploader("拖入文件", accept_multiple_files=True,
                               type=["md", "txt", "pdf", "docx"],
                               label_visibility="collapsed")
    subdir = st.selectbox("存放目录（data/knowledge/ 下）", SUBDIRS,
                          help="sop 规程 / regulations 法规 / equipment 设备 / "
                               "chemicals 药剂 / uploads 其他")

    if st.button("确认上传并入库", type="primary", use_container_width=True,
                 disabled=not uploads):
        target = KNOWLEDGE_DIR / subdir
        target.mkdir(parents=True, exist_ok=True)
        overwritten = []
        for f in uploads:
            dest = target / f.name
            if dest.exists():
                overwritten.append(f.name)
            dest.write_bytes(f.getvalue())
        try:
            with st.spinner("切割 + 嵌入 + 入库..."):
                stats = ingest_knowledge(KNOWLEDGE_DIR,
                                         ROOT / "vector_db" / "manifest.json")
        except Exception as e:  # 常见：embedding 端点未启动
            st.error(f"入库失败：{e}（请检查 embedding 服务，默认本地 Ollama bge-m3）")
            return
        new_files = [Path(n).name for n in stats["changed"]]
        st.success(f"入库完成：本次处理 {len(stats['changed'])} 个文件，"
                   f"切出 {stats['chunks']} 个片段"
                   + (f"；覆盖已存在：{'、'.join(overwritten)}"
                      if overwritten else ""))
        for name in new_files:
            st.caption(f"+ {name}")
        st.caption("点下方“关闭”刷新列表")
        if st.button("关闭", use_container_width=True):
            st.rerun()


def render():
    st.subheader("📁 知识库")

    files = sorted(p for p in KNOWLEDGE_DIR.rglob("*.*")
                   if p.suffix.lower() in SUPPORTED_SUFFIXES)
    total_size = sum(p.stat().st_size for p in files)
    ingested = _ingested_count()
    chunks = _chunk_count()

    stat1, stat2, stat3 = st.columns(3)
    stat1.metric("📄 文档数", len(files))
    stat2.metric("✅ 已入库", ingested)
    stat3.metric("🧩 片段数", chunks if chunks is not None else "未建库")
    st.caption(f"总大小 {_human_size(total_size)}　|　存放位置：`data/knowledge/`"
               f"（子目录：regulations 法规 / equipment 设备 / chemicals 药剂 / "
               f"sop 规程 / uploads 上传）")

    head_l, head_r = st.columns([3, 1])
    head_l.markdown("**已上传文档**")
    if head_r.button("⬆️ 上传文档", type="primary", use_container_width=True):
        upload_dialog()

    if st.button("🔄 刷新列表", use_container_width=True):
        st.rerun()

    if not files:
        st.info("知识库还是空的。点侧边栏「🔄 更新知识库」拖入文件，"
                "或把文档放进 data/knowledge/ 对应子目录。")
        return

    for i in range(0, len(files), 2):
        cols = st.columns(2)
        for col, p in zip(cols, files[i:i + 2]):
            with col:
                with st.container(border=True):
                    stat = p.stat()
                    mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
                    sub = p.parent.relative_to(KNOWLEDGE_DIR)
                    st.markdown(f"**📕 {p.name}**")
                    st.caption(f"{p.suffix.lstrip('.').upper()}"
                               f"　{_human_size(stat.st_size)}　|　{sub}"
                               f"　|　{mtime}")
                    in_db = store_key(p) in _manifest_keys()
                    st.caption("✅ 已入库" if in_db else "⏳ 未入库（待更新知识库）")

    with st.expander("📄 使用说明"):
        st.markdown(
            "1. **添加文档**：点侧边栏「🔄 更新知识库」把文件拖进去，"
            "或直接放入 `data/knowledge/` 对应子目录\n"
            "1. **入库**：上传后自动切割成片段并向量化入库；放目录的文件点一次"
            "「更新知识库」（增量处理，已有内容秒过不动）\n"
            "1. **删除文档**：删掉文件后再跑一次「更新知识库」，对应向量自动清理\n"
            "1. **开始问答**：到「📚 知识问答」页提问，回答会引用来源文件名\n\n"
            "> 问答遵循“仅依据资料回答”：知识库没有的内容会明确说暂无，不编造。")


_MANIFEST_KEYS: set[str] | None = None


def _manifest_keys() -> set[str]:
    """manifest 缓存：一次渲染内只读一次磁盘"""
    global _MANIFEST_KEYS
    if _MANIFEST_KEYS is None:
        manifest = ROOT / "vector_db" / "manifest.json"
        import json
        try:
            _MANIFEST_KEYS = set(json.loads(
                manifest.read_text(encoding="utf-8")))
        except Exception:
            _MANIFEST_KEYS = set()
    return _MANIFEST_KEYS
