"""🔧 故障诊断页：文字诊断 + 镜检诊断（P9）双 tab"""
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

    tab_text, tab_vision = st.tabs(["📝 文字诊断", "📷 镜检诊断"])
    with tab_text:
        _render_text(chat_fn)
    with tab_vision:
        _render_vision()


def _render_text(chat_fn):
    symptoms = st.text_area(
        "描述现场现象（可附关键参数，如 DO、SV30、氨氮等）",
        placeholder="例：出水氨氮超标，DO只有1.8，MLSS偏高", height=100,
        key="diag_symptoms")  # 镜检页"转入排查"会预填此 key

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
