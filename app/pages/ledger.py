"""📋 台账生成页：表单录入当日数据 → 导出 Word + 存入运行记忆（V2.1）"""
import streamlit as st

from app.ledger.report_generator import generate_report
from app.memory.runtime import append_entry


def render():
    st.subheader("📋 台账生成")
    with st.form("ledger_form"):
        st.text_input("厂名", key="ledger_plant_name", placeholder="例：XX污水处理厂")
        c1, c2 = st.columns(2)
        with c1:
            ledger_date = st.date_input("日期", format="YYYY-MM-DD")
        with c2:
            ledger_shift = st.selectbox("班次", ["白班", "中班", "夜班"])
        st.text_input("记录人", key="ledger_op")

        st.markdown("**进出水水质（mg/L，可留空）**")
        for key, label in [("inlet_cod", "进水COD"), ("outlet_cod", "出水COD"),
                           ("inlet_nh3n", "进水氨氮"), ("outlet_nh3n", "出水氨氮"),
                           ("outlet_tn", "出水TN"), ("outlet_tp", "出水TP"),
                           ("outlet_ss", "出水SS"), ("inlet_ph", "进水pH"),
                           ("outlet_ph", "出水pH")]:
            st.text_input(label, key=f"ledger_{key}")

        st.markdown("**生化运行参数**")
        for key, label in [("flow", "处理水量（m³/d）"), ("temp", "水温（℃）"),
                           ("do", "DO（mg/L）"), ("mlss", "MLSS（mg/L）"),
                           ("sv30", "SV30（%）"), ("svi", "SVI"),
                           ("pac", "PAC药耗（kg）"), ("power", "电耗（kWh）")]:
            st.text_input(label, key=f"ledger_{key}")

        st.text_area("运行小结", key="ledger_summary",
                     placeholder="例：系统运行稳定，各指标达标")
        st.text_area("异常情况与处置", key="ledger_abnormal",
                     placeholder="例：下午进水COD短暂升高，已减泥提DO，2h后恢复")

        submitted = st.form_submit_button("📝 生成台账", use_container_width=True)

    if submitted:
        data = {k.removeprefix("ledger_"): str(v)
                for k, v in st.session_state.items()
                if k.startswith("ledger_") and k != "ledger_op" and v is not None}
        data["operator"] = st.session_state.get("ledger_op", "")
        data["date"] = ledger_date.isoformat()
        data["shift"] = ledger_shift
        docx_bytes = generate_report(data)
        # V2.1 运行记忆：台账落盘后诊断/问答才能自动引用近况
        save_memory = st.checkbox("💾 同时存入运行记忆（诊断/问答时自动参考近况）",
                                  value=True)
        if save_memory:
            try:
                append_entry(data)
                st.success(f"已存入运行记忆（{ledger_date} {ledger_shift}），"
                           f"诊断时将自动引用")
            except Exception as e:
                st.warning(f"存入运行记忆失败（不影响台账导出）：{e}")
        st.download_button("⬇️ 下载 Word 台账", docx_bytes,
                           file_name=f"运行台账_{ledger_date}.docx",
                           mime="application/vnd.openxmlformats-officedocument"
                                ".wordprocessingml.document",
                           use_container_width=True)
