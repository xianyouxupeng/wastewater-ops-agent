"""污水处理运维助手 Web 界面：多页面导航（功能页 + 设置页）。

启动（手机可访问需监听局域网）：
    streamlit run app/main.py --server.address 0.0.0.0 --server.port 8501
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

st.set_page_config(page_title="污水处理运维助手", page_icon="💧", layout="centered")

ROOT = Path(__file__).resolve().parents[1]

from app.pages import diagnose, qa, knowledge, ledger, params, settings  # noqa: E402
from app.rag.ingest import ingest_knowledge  # noqa: E402
from app.rag.cases import ingest_cases  # noqa: E402


@st.dialog("🔄 更新知识库", width="large")
def kb_dialog():
    """拖入文件 → 保存到 data/knowledge/uploads/ → 切割 + 嵌入 + 入库"""
    st.caption("把文档拖进下面框里，上传后自动切割、嵌入并入库"
               "（支持 md / txt / pdf / docx，可多选）")
    uploads = st.file_uploader("拖入文件", accept_multiple_files=True,
                               type=["md", "txt", "pdf", "docx"],
                               label_visibility="collapsed")
    if uploads and st.button("⬆️ 上传并入库", type="primary",
                             use_container_width=True):
        target = ROOT / "data" / "knowledge" / "uploads"
        target.mkdir(parents=True, exist_ok=True)
        for f in uploads:
            (target / f.name).write_bytes(f.getvalue())
        try:
            with st.spinner("切割 + 嵌入 + 入库..."):
                stats = ingest_knowledge(ROOT / "data" / "knowledge",
                                         ROOT / "vector_db" / "manifest.json")
            st.success(f"入库完成：本次处理 {len(stats['changed'])} 个文件"
                       f"（{stats['chunks']} 个片段），清理 {len(stats['removed'])} 个")
            for name in stats["changed"]:
                st.caption(f"+ {name}")
        except Exception as e:  # 常见：embedding 端点未启动
            st.error(f"入库失败：{e}（请检查 embedding 服务，默认本地 Ollama bge-m3）")

    st.divider()
    st.caption("也可直接把文件放进 data/knowledge/ 对应子目录，扫描增量入库"
               "（同时更新历史案例库）")
    if st.button("📂 扫描 knowledge 目录", use_container_width=True):
        try:
            with st.spinner("增量入库..."):
                stats = ingest_knowledge(ROOT / "data" / "knowledge",
                                         ROOT / "vector_db" / "manifest.json")
                case_stats = ingest_cases(ROOT / "data" / "cases" / "cases.jsonl")
            st.success(f"新增/更新 {len(stats['changed'])} 个文件"
                       f"（{stats['chunks']} 个片段），清理 {len(stats['removed'])} 个；"
                       f"案例更新 {len(case_stats['changed'])} 条")
            for name in stats["changed"]:
                st.caption(f"+ {name}")
        except Exception as e:
            st.error(f"入库失败：{e}")


nav = st.navigation([
    st.Page(diagnose.render, title="故障诊断", icon="🔧", default=True),
    st.Page(qa.render, title="知识问答", icon="📚"),
    st.Page(knowledge.render, title="知识库", icon="📁"),
    st.Page(ledger.render, title="台账生成", icon="📋"),
    st.Page(params.render, title="参数建议", icon="⚙️"),
    st.Page(settings.render, title="设置", icon="🛠️"),
])

with st.sidebar:
    st.markdown("### 💧 污水处理运维助手")

nav.run()

with st.sidebar:
    st.divider()
    if st.button("🔄 更新知识库", use_container_width=True):
        kb_dialog()
    st.caption("⚠️ 本助手输出仅供运行参考，处置措施须经工艺工程师或值班长确认后执行。")
