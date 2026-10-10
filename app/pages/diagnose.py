"""🔧 故障诊断页"""
import streamlit as st

from app.diagnostic.engine import diagnose, FALLBACK_WARNING
from app.providers import get_active_chat_fn


def render():
    st.subheader("🔧 故障诊断")
    chat_fn, provider = get_active_chat_fn()
    if chat_fn is None:
        st.error("尚未配置可用的模型供应商，请先到「设置 → 模型」添加并设为当前使用。")
        return
    st.caption(f"当前使用：{provider['name']} · {provider['model']}")

    symptoms = st.text_area(
        "描述现场现象（可附关键参数，如 DO、SV30、氨氮等）",
        placeholder="例：出水氨氮超标，DO只有1.8，MLSS偏高", height=100)
    if st.button("🔍 开始诊断", type="primary", use_container_width=True):
        if not symptoms.strip():
            st.warning("请先描述现场现象")
        else:
            try:
                with st.spinner("诊断中（含故障树匹配 + 相似案例检索）..."):
                    st.session_state["diag_result"] = diagnose(symptoms, chat_fn=chat_fn)
            except Exception as e:
                st.error(f"诊断失败：{e}")
                st.caption("请到「设置 → 模型 → 诊断」测试供应商连通性。")

    if "diag_result" in st.session_state:
        result = st.session_state["diag_result"]
        if result.startswith(FALLBACK_WARNING):
            st.warning(FALLBACK_WARNING)
            with st.expander("🔍 低置信度推理结果（点击展开）", expanded=True):
                st.markdown(result[len(FALLBACK_WARNING):].strip())
        else:
            with st.expander("📋 诊断报告（点击展开/收起）", expanded=True):
                st.markdown(result)
