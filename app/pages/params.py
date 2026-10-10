"""⚙️ 参数建议页"""
import streamlit as st

from app.params.advisor import suggest


def render():
    st.subheader("⚙️ 参数辅助建议")
    st.caption("输入当前参数或现象（带数值或“偏高/偏低”），逐条生成建议卡。"
               "示例：DO 1.5，氨氮偏高")
    param_text = st.text_area("当前参数/现象", key="param_text", height=80)
    if st.button("💡 生成建议卡", type="primary", use_container_width=True):
        if not param_text.strip():
            st.warning("请先输入参数或现象")
        else:
            with st.expander("📋 建议卡（点击展开/收起）", expanded=True):
                st.markdown(suggest(param_text))
