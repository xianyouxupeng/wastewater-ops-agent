"""🏭 厂情档案：首次使用填一次本厂情况，诊断/问答自动引用。

主页面之一（不藏在设置里）：档案未配置时诊断/问答页也会提示来此填写。
保存到 data/plant_profile.yaml；空字段不落盘（缺失不注入，不影响使用）。
"""
import re

import streamlit as st

from app.memory.plant import (is_profile_filled, load_plant_profile,
                              parse_limit, save_plant_profile)

# 常见工艺单元：多选组合（实际污水厂多为组合工艺），按处理顺序选择
PROCESS_UNITS = [
    "厌氧水解", "UASB厌氧", "A/O", "A²/O", "多级AO", "SBR", "氧化沟", "MBR",
    "AB法", "BIOLAK", "气浮", "混凝沉淀", "高效沉淀池", "BAF曝气生物滤池",
    "反硝化滤池", "V型滤池", "紫外消毒", "次氯酸钠消毒", "芬顿氧化", "臭氧氧化",
    "板框压滤", "带式脱水", "离心脱水",
]
STANDARDS = ["一级A", "一级B", "二级标准", "其他"]

# 单元别名：用户手写习惯 → 下拉单元（大小写不敏感匹配，命中即选中该单元）
_UNIT_ALIASES = {
    "芬顿氧化": ["芬顿"], "UASB厌氧": ["UASB"], "BAF曝气生物滤池": ["BAF"],
    "板框压滤": ["板框压滤机"], "带式脱水": ["带式脱水机"], "离心脱水": ["离心脱水机"],
}


def _unit_patterns(unit: str) -> list[str]:
    """单元的匹配串 = 本名 + 别名"""
    return [re.escape(unit)] + [re.escape(a) for a in _UNIT_ALIASES.get(unit, [])]


def _match_units(text: str) -> list[str]:
    """从自由文本里识别已有工艺单元（大小写不敏感），用于回显默认勾选"""
    low = (text or "").lower()
    return [u for u in PROCESS_UNITS
            if any(re.search(p, low, flags=re.IGNORECASE) for p in _unit_patterns(u))]


def _remove_units(text: str) -> str:
    """从自由文本里删掉已识别的单元（含别名），返回剩余部分。
    单元名后紧随的"机/池/器"等设备后缀一并去除（如删"板框压滤"连"板框压滤机"的"机"）。"""
    leftover = text or ""
    for u in PROCESS_UNITS:
        for p in _unit_patterns(u):
            leftover = re.sub(p + r"[机池器]?", "", leftover, flags=re.IGNORECASE)
    return leftover


def render():
    st.subheader("🏭 厂情档案")
    st.caption("首次使用填一次即可：诊断/问答会自动结合本厂工况"
               "（工艺、排放限值、设计参数、药剂、设备），无需每次重复输入。"
               "留空的字段不影响使用。")

    profile = load_plant_profile()
    if is_profile_filled(profile):
        st.success(f"已配置：{profile.get('厂名')}（{profile.get('工艺')}）")
    else:
        st.warning("尚未完成配置——建议现在填写，让诊断更懂你厂。")

    limits = profile.get("排放限值") or {}
    design = profile.get("设计参数") or {}
    chems = profile.get("常用药剂") or {}
    nh3_base, nh3_season = parse_limit(limits.get("氨氮", ""))

    with st.form("plant_profile_form"):
        st.markdown("##### 基本信息")
        name = st.text_input("厂名 *", value=profile.get("厂名", ""),
                             placeholder="例：XX市污水处理厂")
        cur_proc = profile.get("工艺", "")
        selected = st.multiselect(
            "污水处理工艺 *（可多选组合，按处理流程顺序）",
            PROCESS_UNITS,
            default=_match_units(cur_proc),
            help="实际工艺多为组合：如 A²/O+高效沉淀池+反硝化滤池。"
                 "下拉列表没有的单元写在下方补充里。")
        proc_custom = st.text_input(
            "其他工艺单元 / 补充说明（与多选拼接，可留空）",
            value=_leftover_process(cur_proc),
            placeholder="例：如需备注写成 \"多级AO（两点进水）+ 高效沉淀池\"")
        c1, c2 = st.columns(2)
        scale = c1.text_input("设计规模（处理水量）",
                              value=profile.get("设计规模", ""),
                              placeholder="例：2 万吨/日")
        cur_std = profile.get("排放标准") or STANDARDS[0]
        std = c2.selectbox("排放标准", STANDARDS,
                           index=STANDARDS.index(cur_std)
                           if cur_std in STANDARDS else STANDARDS.index("其他"))
        std_custom = st.text_input(
            "其他标准（排放标准选「其他」时填写）",
            value=cur_std if cur_std not in STANDARDS else "",
            placeholder="例：当地 DBxx/xxx 一级标准")

        st.markdown("##### 排放限值（mg/L，留空表示不限/未定）")
        l1, l2, l3, l4, l5, l6 = st.columns(6)
        cod = l1.text_input("COD", value=str(limits.get("COD", "") or ""))
        nh3 = l2.text_input("氨氮", value=nh3_base, placeholder="5")
        nh3_s = l3.text_input("氨氮·季节", value=nh3_season,
                              placeholder="8（水温≤12℃）")
        tn = l4.text_input("TN", value=str(limits.get("TN", "") or ""))
        tp = l5.text_input("TP", value=str(limits.get("TP", "") or ""))
        ss = l6.text_input("SS", value=str(limits.get("SS", "") or ""))

        st.markdown("##### 设计/运行控制参数（可填区间）")
        d1, d2 = st.columns(2)
        d3, d4 = st.columns(2)
        mlss = d1.text_input("MLSS（mg/L）", value=str(design.get("MLSS", "") or ""),
                             placeholder="3000-4500")
        srt = d2.text_input("泥龄（天）", value=str(design.get("泥龄", "") or ""),
                            placeholder="10-15")
        do = d3.text_input("DO（mg/L）", value=str(design.get("DO", "") or ""),
                           placeholder="2-3.5")
        recirc = d4.text_input("内回流比", value=str(design.get("内回流比", "") or ""),
                               placeholder="100%")

        st.markdown("##### 常用药剂")
        m1, m2, m3 = st.columns(3)
        chem_p = m1.text_input("除磷药剂", value=str(chems.get("除磷", "") or ""),
                               placeholder="PAC")
        chem_c = m2.text_input("碳源", value=str(chems.get("碳源", "") or ""),
                               placeholder="乙酸钠")
        chem_d = m3.text_input("消毒药剂", value=str(chems.get("消毒", "") or ""),
                               placeholder="次氯酸钠")

        equipment = st.text_area(
            "主要设备（鼓风机、水泵、脱水机等，一两句话即可）",
            value=profile.get("主要设备", ""),
            placeholder="例：罗茨鼓风机3台（2用1备）、潜污泵4台、带式脱水机2台")
        note = st.text_area("特殊说明（上游风险企业、季节性问题等）",
                            value=profile.get("特殊说明", ""),
                            placeholder="例：进水以生活污水为主，上游有一家印染厂（毒性冲击风险源）")
        submitted = st.form_submit_button("💾 保存厂情档案", type="primary",
                                          use_container_width=True)

    if not submitted:
        return

    parts = selected + ([proc_custom.strip()] if proc_custom.strip() else [])
    final_proc = "+".join(parts)
    final_std = std_custom.strip() if std == "其他" else std
    if not name.strip() or not final_proc:
        st.error("厂名和工艺为必填项（工艺至少选一个单元或在补充里填写）")
        return
    nh3_value = nh3.strip()
    if nh3_value and nh3_s.strip():
        nh3_value = f"{nh3_value}({nh3_s.strip()})"
    save_plant_profile({
        "厂名": name.strip(),
        "工艺": final_proc,
        "设计规模": scale.strip(),
        "排放标准": final_std,
        "排放限值": {"COD": cod.strip(), "氨氮": nh3_value, "TN": tn.strip(),
                     "TP": tp.strip(), "SS": ss.strip()},
        "设计参数": {"MLSS": mlss.strip(), "泥龄": srt.strip(), "DO": do.strip(),
                     "内回流比": recirc.strip()},
        "常用药剂": {"除磷": chem_p.strip(), "碳源": chem_c.strip(),
                     "消毒": chem_d.strip()},
        "主要设备": equipment.strip(),
        "特殊说明": note.strip(),
    })
    st.success("✅ 厂情档案已保存，诊断/问答即刻生效")


def _leftover_process(cur_proc: str) -> str:
    """已保存的组合工艺里，减去能识别的单元，剩下的放补充栏（避免回显丢失）。
    括号注释（如 "A/O（厌氧/好氧）" 的 "（厌氧/好氧）"）视为说明文字去除，不进补充栏。"""
    if not cur_proc:
        return ""
    leftover = _remove_units(cur_proc)
    leftover = re.sub(r"[（(][^（）()]*[）)]", "", leftover)  # 去括号注释
    return re.sub(r"[\s+＋/、，,\-]+", " ", leftover).strip()
