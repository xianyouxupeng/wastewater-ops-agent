"""📚 知识问答页（带会话历史）"""
import streamlit as st

from app.rag.qa import ask
from app.providers import get_active_chat_fn

MAX_HISTORY = 50  # 界面保留的最近消息条数


def _write_sources(sources: list):
    """展示回答引用编号 [n] 对应的实际来源文件"""
    st.caption("📎 本次引用编号对应的来源：" + "；".join(
        f"[{i + 1}] {s}" for i, s in enumerate(sources)))


def render():
    st.subheader("📚 知识问答")
    chat_fn, provider = get_active_chat_fn()
    if chat_fn is None:
        st.error("尚未配置可用的模型供应商，请先到「设置 → 模型」添加并设为当前使用。")
        return
    st.caption(f"当前使用：{provider['name']} · {provider['model']}"
               f"（会话历史仅保留在本页面，刷新/重启后清空）")

    if "qa_history" not in st.session_state:
        st.session_state["qa_history"] = []

    # 渲染历史消息
    for msg in st.session_state["qa_history"]:
        st.chat_message(msg["role"]).markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            _write_sources(msg["sources"])

    question = st.chat_input("向知识库提问，例：PAC的投加量范围是多少？")
    if question:
        st.session_state["qa_history"].append({"role": "user", "content": question})
        st.chat_message("user").write(question)
        try:
            with st.spinner("检索知识库并生成回答..."):
                answer, hits = ask(question, chat_fn=chat_fn, return_sources=True)
                sources = [h["source"] for h in hits]
        except Exception as e:
            answer = f"⚠️ 问答失败：{e}"
            sources = []
            with st.expander("🔧 错误详情（排查用）"):
                st.exception(e)
        st.chat_message("assistant").markdown(answer)
        if sources:
            _write_sources(sources)
        st.session_state["qa_history"].append(
            {"role": "assistant", "content": answer, "sources": sources})
        # 只保留最近 N 条，防止 session 膨胀
        del st.session_state["qa_history"][:-MAX_HISTORY]

    col_l, _, col_r = st.columns([1, 3, 1])
    with col_r:
        if st.session_state["qa_history"] and st.button("🗑️ 清空会话", use_container_width=True):
            st.session_state["qa_history"] = []
            st.rerun()
