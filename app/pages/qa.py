"""📚 知识问答页"""
import streamlit as st

from app.rag.qa import ask
from app.providers import get_active_chat_fn


def render():
    st.subheader("📚 知识问答")
    chat_fn, provider = get_active_chat_fn()
    if chat_fn is None:
        st.error("尚未配置可用的模型供应商，请先到「设置 → 模型」添加并设为当前使用。")
        return
    st.caption(f"当前使用：{provider['name']} · {provider['model']}")

    question = st.chat_input("向知识库提问，例：PAC的投加量范围是多少？")
    if question:
        st.chat_message("user").write(question)
        try:
            with st.spinner("检索知识库并生成回答..."):
                answer = ask(question, chat_fn=chat_fn)
            st.chat_message("assistant").markdown(answer)
        except Exception as e:
            st.error(f"问答失败：{e}")
