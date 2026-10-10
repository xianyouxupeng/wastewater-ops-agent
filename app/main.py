"""污水处理运维助手 Web 界面（P6）。

启动（手机可访问需监听局域网）：
    streamlit run app/main.py --server.address 0.0.0.0 --server.port 8501
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.config import MODEL_PRESETS
from app.agent.llm import get_chat_fn
from app.diagnostic.engine import diagnose, FALLBACK_WARNING
from app.rag.qa import ask
from app.rag.ingest import ingest_knowledge
from app.rag.cases import ingest_cases, format_case

st.set_page_config(page_title="污水处理运维助手", page_icon="💧", layout="centered")

ROOT = Path(__file__).resolve().parents[1]


# ===== 侧边栏：模型切换（要求②）+ 知识库更新（要求③）=====
with st.sidebar:
    st.header("⚙️ 设置")
    model_choice = st.selectbox("模型", list(MODEL_PRESETS.keys()))
    chat_fn = get_chat_fn(MODEL_PRESETS[model_choice])
    st.caption(f"当前端点：`{MODEL_PRESETS[model_choice]['base_url']}`")

    if st.button("🔄 更新知识库", use_container_width=True,
                 help="扫描 data/knowledge/ 与案例库，只处理新增/修改的文件"):
        try:
            with st.spinner("正在增量入库..."):
                stats = ingest_knowledge(ROOT / "data" / "knowledge",
                                         ROOT / "vector_db" / "manifest.json")
                case_stats = ingest_cases(ROOT / "data" / "cases" / "cases.jsonl")
            st.success(f"新增/更新 {len(stats['changed'])} 个文件"
                       f"（{stats['chunks']} 个片段），清理 {len(stats['removed'])} 个；"
                       f"案例更新 {len(case_stats['changed'])} 条")
            for name in stats["changed"]:
                st.caption(f"+ {name}")
        except Exception as e:  # 常见：embedding 端点未启动
            st.error(f"入库失败：{e}（请检查 embedding 服务，默认本地 Ollama bge-m3）")

    st.divider()
    st.caption("⚠️ 本助手输出仅供运行参考，处置措施须经工艺工程师或值班长确认后执行。")


# ===== 故障诊断 =====
tab_diag, tab_qa, tab_ledger, tab_params = st.tabs(
    ["🔧 故障诊断", "📚 知识问答", "📋 台账生成", "⚙️ 参数建议"])

with tab_diag:
    st.subheader("故障诊断")
    symptoms = st.text_area(
        "描述现场现象（可附关键参数，如 DO、SV30、氨氮等）",
        placeholder="例：出水氨氮超标，DO只有1.8，MLSS偏高",
        height=100)
    if st.button("🔍 开始诊断", type="primary", use_container_width=True):
        if not symptoms.strip():
            st.warning("请先描述现场现象")
        else:
            try:
                with st.spinner("诊断中（含故障树匹配 + 相似案例检索）..."):
                    result = diagnose(symptoms, chat_fn=chat_fn)
                st.session_state["diag_result"] = result
            except Exception as e:
                st.error(f"诊断失败：{e}")
                st.caption("本地模型请确认已运行 `ollama serve`；"
                           "在线模型请检查 .env 中的 API Key。")

    if "diag_result" in st.session_state:
        result = st.session_state["diag_result"]
        if result.startswith(FALLBACK_WARNING):
            st.warning(FALLBACK_WARNING)
            body = result[len(FALLBACK_WARNING):].strip()
            with st.expander("🔍 低置信度推理结果（点击展开）", expanded=True):
                st.markdown(body)
        else:
            with st.expander("📋 诊断报告（点击展开/收起）", expanded=True):
                st.markdown(result)

with tab_qa:
    st.subheader("知识问答")
    question = st.chat_input("向知识库提问，例：PAC的投加量范围是多少？")
    if question:
        st.chat_message("user").write(question)
        try:
            with st.spinner("检索知识库并生成回答..."):
                answer = ask(question, chat_fn=chat_fn)
            st.chat_message("assistant").markdown(answer)
        except Exception as e:
            st.error(f"问答失败：{e}")

with tab_ledger:
    st.info("📋 台账生成将在 P7 实现：表单录入当日数据 → 导出 Word 台账。")

with tab_params:
    st.info("⚙️ 参数建议将在 P7 实现：输入当前参数 → 生成带风险提示的调整建议卡。")
