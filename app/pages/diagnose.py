"""🔧 故障诊断页：文字诊断（Agent 多轮循环 / V1 一次性降级）+ 镜检诊断（P9）双 tab"""
import streamlit as st

from app.diagnostic.agent import MODE_LABELS, AgentSession, build_agent_context, detect_mode
from app.diagnostic.engine import FALLBACK_WARNING, diagnose
from app.providers import get_active_chat_fn, get_active_message_fn

QUICK_ANSWERS = [("✅ 是", "是"), ("❌ 否", "否"), ("🤔 不确定", "不确定")]


def render():
    st.subheader("🔧 故障诊断")
    chat_fn, provider = get_active_chat_fn()
    if chat_fn is None:
        st.error("尚未配置可用的模型供应商，请先到「设置 → 模型」添加并设为当前使用。")
        return
    st.caption(f"当前使用：{provider['name']} · {provider['model']}")

    tab_text, tab_vision = st.tabs(["📝 文字诊断", "📷 镜检诊断"])
    with tab_text:
        _render_text(chat_fn, provider)
    with tab_vision:
        _render_vision()


def _render_text(chat_fn, provider):
    mode = detect_mode(provider.get("model"))
    from app.memory.plant import is_profile_filled
    if not is_profile_filled():
        st.info("👋 首次使用建议先到左侧「🏭 厂情档案」填写本厂工艺、排放限值、"
                "设计参数等（一次即可）。之后诊断会自动结合本厂工况；不填也能用，按通用工艺推理。")
    symptoms = st.text_area(
        "描述现场现象（可附关键参数，如 DO、SV30、氨氮等）",
        placeholder="例：出水氨氮有点高", height=100,
        key="diag_symptoms")  # 镜检页"转入排查"会预填此 key

    if mode == "off":
        st.caption("ℹ️ 当前模型参数量较小，多轮工具调用不稳定，已自动使用 V1 一次性诊断。"
                   "换用 14B+ 本地模型或在线模型即可启用 Agent 多轮诊断"
                   "（设置 → 模型；也可在 .env 设 AGENT_MODE 强制指定）。")
        _render_oneshot(chat_fn, symptoms)
        return

    st.caption(f"🤖 Agent 多轮诊断：{MODE_LABELS[mode]}——系统会自动查台账/规程/案例，"
               f"并像老师傅一样追问关键鉴别问题，信息足够才下结论。")
    _render_agent(mode, symptoms)


def _render_oneshot(chat_fn, symptoms):
    """V1 一次性诊断（off 模式降级路径，逻辑保持不变）"""
    run = st.button("🔍 开始诊断", type="primary", use_container_width=True)
    if not run and st.session_state.pop("diag_autorun", False):
        run = bool(symptoms.strip())  # 镜检页转入：预填后自动执行

    if run:
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
        _render_case_save()


def _render_agent(mode, symptoms):
    """Agent 多轮诊断 UI：开始 → 工具轮自动续跑 → 问题卡等回答 → 报告"""
    start = st.button("🔍 开始诊断", type="primary", use_container_width=True)
    if not start and st.session_state.pop("diag_autorun", False):
        start = bool(symptoms.strip())  # 镜检页转入：预填后自动执行
    if start:
        if not symptoms.strip():
            st.warning("请先描述现场现象")
        else:
            _start_session(symptoms, mode)

    sess = st.session_state.get("agent_session")
    if sess is None:
        return

    answer = st.session_state.pop("agent_answer", None)
    chat_answer = st.session_state.pop("agent_chat_input", None)
    try:
        if answer is not None or chat_answer:
            _drive(sess, answer if answer is not None else chat_answer)
        elif not st.session_state.get("agent_pending") \
                and "agent_report" not in st.session_state:
            _drive(sess, None)  # 新会话首轮 / 工具轮续跑
    except Exception as e:
        st.error(f"诊断中断：{e}")
        st.caption("请到「设置 → 模型 → 诊断」测试供应商连通性；"
                   "若提示不支持 tools，可在 .env 设 AGENT_MODE=text 改用文本解析模式。")
        _reset_agent()
        return

    _render_trace()
    _render_pending_or_report()


def _set_answer(value):
    st.session_state["agent_answer"] = value


def _start_session(symptoms, mode):
    llm_fn, _ = get_active_message_fn()
    st.session_state["agent_session"] = AgentSession(
        symptoms, llm_fn, mode, context=build_agent_context(symptoms))
    st.session_state["agent_trace"] = []
    for key in ("agent_pending", "agent_pending_thought",
                "agent_report", "diag_result"):
        st.session_state.pop(key, None)


def _drive(sess, answer):
    """推到下一个需要人/结束的节点：工具轮自动续跑并记录轨迹"""
    ev = sess.step(answer)
    trace = st.session_state.setdefault("agent_trace", [])
    while ev["type"] == "tool":
        trace.append(ev)
        ev = sess.step()
    if ev["type"] == "ask":
        st.session_state["agent_pending"] = ev["question"]
        st.session_state["agent_pending_thought"] = ev.get("thought", "")
    elif ev["type"] == "conclude":
        st.session_state.pop("agent_pending", None)
        st.session_state["agent_report"] = ev["report"]
        st.session_state["diag_result"] = ev["report"]  # 复用案例沉淀入口


def _render_trace():
    trace = st.session_state.get("agent_trace") or []
    if trace:
        with st.expander(f"🧰 Agent 已自动查证 {len(trace)} 次（点击展开）"):
            for t in trace:
                if t.get("thought"):
                    st.caption(f"💡 {t['thought']}")
                st.markdown(f"**{t['name']}**　`{t.get('args') or {}}`")
                st.text(t["result"])


def _render_pending_or_report():
    question = st.session_state.get("agent_pending")
    if question:
        with st.chat_message("assistant"):
            st.markdown(f"**需要你确认一个关键鉴别问题：**\n\n{question}")
            cols = st.columns(len(QUICK_ANSWERS))
            for col, (label, value) in zip(cols, QUICK_ANSWERS):
                # 回调只置状态，统一由下一轮 _render_agent 驱动循环，避免重复调 LLM
                col.button(label, key=f"agent_quick_{value}",
                           on_click=_set_answer, args=(value,))
        st.chat_input("或在此输入回答…", key="agent_chat_input")
        return
    report = st.session_state.get("agent_report")
    if report:
        with st.expander("📋 诊断报告（点击展开/收起）", expanded=True):
            st.markdown(report)
        if st.button("🔄 重新开始一轮诊断", use_container_width=True):
            _reset_agent()
            st.rerun()
        _render_case_save()


def _reset_agent():
    for key in ("agent_session", "agent_trace", "agent_pending",
                "agent_pending_thought", "agent_report", "diag_result"):
        st.session_state.pop(key, None)


def _render_case_save():
    """L4 经验记忆：本次诊断的"现象→结论→处置"经人工确认后沉淀为案例。

    人工确认闭环防脏数据：LLM 结论只能预填草稿，点头才写库；写入只落 jsonl，
    向量入库延后到下次「更新知识库」（embedding 服务不在时不阻塞）。
    """
    symptoms = st.session_state.get("diag_symptoms", "")
    with st.expander("💾 沉淀为案例（处置见效后填写，本厂下次诊断自动引用）"):
        st.caption("请确认处置已验证有效后再入库；内容会作为本厂真实案例被相似诊断检索。")
        with st.form("case_save_form"):
            phen = st.text_area("现象（含关键参数）", value=symptoms, height=80,
                                key="case_phen")
            cause = st.text_area("结论/原因", placeholder="例：进水负荷冲击导致硝化不足",
                                 key="case_cause")
            action = st.text_area("处置", placeholder="例：减泥+提DO至3.0，48h恢复",
                                  key="case_action")
            outcome = st.text_input("结果", placeholder="例：出水达标",
                                    key="case_outcome")
            saved = st.form_submit_button("✅ 确认无误，写入案例库",
                                          use_container_width=True)
        if saved:
            if not (phen.strip() and cause.strip()):
                st.warning("现象与结论/原因必填")
            else:
                from app.rag.cases import add_case
                case = add_case({"现象": phen.strip(), "原因": cause.strip(),
                                 "处置": action.strip(), "结果": outcome.strip()})
                st.success(f"已写入案例库（{case['id']}），"
                           f"下次「更新知识库」时自动向量化生效")


def _render_vision():
    try:
        from app.rag.retriever import retrieve
        from app.vision import analyzer, species
    except ImportError:  # app/vision/ 模块被移除时降级
        st.caption("镜检诊断模块未安装（app/vision/ 不存在）")
        return

    vlm_cfg = analyzer.get_vlm_config()
    st.caption(f"视觉模型：{vlm_cfg['model']} @ {vlm_cfg['base_url']}"
               f"（设置 → 视觉模型 可更换）")
    st.caption("📷 拍摄指引：擦净目镜 → 手机镜头贴近日镜 → 对好焦再拍；"
               "图片过糊将如实提示无法判断。")

    cam = st.camera_input("拍摄镜检照片")
    up = st.file_uploader("或上传图片", type=["png", "jpg", "jpeg", "webp"])
    img_file = cam or up

    if img_file and st.button("🔬 分析镜检图", type="primary", use_container_width=True):
        try:
            with st.spinner("VLM 读图中（本地模型首次加载较慢）..."):
                st.session_state["vision_ana"] = analyzer.analyze_image(
                    img_file.getvalue(), vlm_cfg)
            st.session_state.pop("vision_report", None)  # 换图后清旧报告
        except Exception as e:
            st.error(f"视觉模型调用失败：{e}")
            st.caption("请到「设置 → 视觉模型」做连通性测试。")

    ana = st.session_state.get("vision_ana")
    if not ana:
        return

    result = ana["result"]
    if not analyzer.is_quality_ok(result):
        st.warning("⚠️ 图像质量不足以判断（或模型返回无法解析），请擦净目镜、对焦后重拍。")
        with st.expander("模型原始返回（仅供排查）"):
            st.text(ana["raw"][:800])
        return

    _render_vision_result(result, analyzer, species, retrieve)


def _render_vision_result(result, analyzer, species, retrieve):
    # 结构化描述摘要
    st.markdown(
        f"**丝状菌丰度：{result.get('filament_abundance')}** ｜ "
        f"菌胶团：{result.get('floc_structure')}")
    st.markdown("优势类群：" + "、".join(result.get("dominant_organisms") or []))
    with st.expander("观察描述（VLM 原文）"):
        st.text(result.get("observation"))

    # 指示生物匹配
    obs_text = (result.get("observation") or "") + " " + \
               "、".join(result.get("dominant_organisms") or [])
    matches = species.match_species(obs_text, species.load_species())
    trigger = species.bulking_trigger(result, matches)

    # 教程 RAG 解读（用文字诊断的语言模型生成，只调一次并缓存）
    if "vision_report" not in st.session_state:
        try:
            hits = analyzer._prefer_microscopy(retrieve(obs_text, k=6))
            chat_fn, _ = get_active_chat_fn()
            with st.spinner("结合镜检教程解读中..."):
                st.session_state["vision_report"] = analyzer.explain(obs_text, hits, chat_fn)
            st.session_state["vision_sources"] = [h["source"] for h in hits]
        except Exception as e:
            st.session_state["vision_report"] = f"（教程解读生成失败：{e}）"
            st.session_state["vision_sources"] = []

    with st.expander("📋 诊断说明（含教程引用）", expanded=True):
        st.markdown(st.session_state["vision_report"])
    srcs = st.session_state.get("vision_sources") or []
    if srcs:
        st.caption("实际检索命中来源：" + "；".join(srcs))

    with st.expander("🧬 指示生物对照"):
        if matches:
            for m in matches:
                ref = f"（关联排查流程：{m['fault_tree_ref']}）" if m["fault_tree_ref"] else ""
                st.markdown(f"- **{m['organism']}**{ref}：{m['meaning']}"
                            + (f"　→ {m['action']}" if m["action"] else ""))
        else:
            st.caption("未命中指示生物条目")

    if trigger:
        st.error(f"⚠️ 镜检提示污泥膨胀倾向（{trigger['tree_id']}），建议转入故障树排查流程。")
        if st.button("🧭 转入污泥膨胀排查", type="primary", use_container_width=True):
            st.session_state["diag_symptoms"] = trigger["prefill"]
            st.session_state["diag_autorun"] = True
            st.session_state.pop("diag_result", None)
            st.toast("已填入文字诊断，正在切换到「文字诊断」标签页")
            st.rerun()
