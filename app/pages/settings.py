"""⚙️ 设置页：模型供应商管理（卡片 + 添加/编辑弹窗 + 连通性诊断）"""
import os

import streamlit as st

from app import providers
from app.providers import PROVIDER_REGISTRY, STORE_PATH


def render():
    st.title("⚙️ 设置")
    tab_llm, tab_vlm, tab_about = st.tabs(["🤖 模型", "👁️ 视觉模型", "ℹ️ 关于"])

    with tab_llm:
        _render_llm()
    with tab_vlm:
        try:
            from app.vision.settings_ui import render_vlm_settings
            render_vlm_settings()
        except ImportError:  # app/vision/ 模块被移除时降级
            st.caption("镜检诊断模块未安装（app/vision/ 不存在）")
    with tab_about:
        st.markdown(
            "### 污水处理运维助手\n"
            "故障诊断 · 知识问答 · 台账生成 · 参数建议\n\n"
            "⚠️ 所有输出仅供运行参考，处置措施须经工艺工程师或值班长确认后执行。\n\n"
            "模型供应商配置保存在本地 `data/models.json`（已 gitignore，密钥不出本机）。")


def _render_llm():
    st.subheader("LLM")
    st.caption("配置语言模型。当前激活的模型用于故障诊断、知识问答等全部推理。")

    store = providers.load_store(STORE_PATH)
    active = store.get("active", "")

    active_p = providers.get_active_provider(STORE_PATH)
    if active_p and active_p.get("model"):
        from app.diagnostic.agent import MODE_LABELS, detect_mode
        mode = detect_mode(active_p["model"])
        st.caption(f"Agent 诊断能力（{active_p['model']}）：{MODE_LABELS[mode]}"
                   f"　—— 可在 .env 设 AGENT_MODE=native/text/off 强制覆盖自动判定")

    head_l, head_r = st.columns([3, 1])
    head_l.markdown("**供应商**")
    if head_r.button("➕ 添加供应商", use_container_width=True):
        add_provider_dialog()

    items = store["providers"]
    for i in range(0, len(items), 2):
        cols = st.columns(2)
        for col, p in zip(cols, items[i:i + 2]):
            with col:
                _provider_card(p, p["name"] == active)

    with st.expander("🩺 诊断（供应商连通性测试）"):
        if st.button("▶️ 运行测试", use_container_width=True):
            for p in items:
                ok, secs, detail = providers.ping(p)
                if ok:
                    st.success(f"✓ {p['name']} · {p['model']}　{secs:.1f}s　{detail}")
                else:
                    st.error(f"✗ {p['name']}　{secs:.1f}s　{detail}")


def _provider_card(p: dict, is_active: bool):
    with st.container(border=True):
        st.markdown(f"**{p['name']}**")
        st.caption(p["base_url"] or "未配置接口地址")
        st.caption(f"模型：{p['model'] or '未填写'}")
        btn_l, btn_r = st.columns(2)
        if is_active:
            btn_l.button("✅ 当前使用", key=f"use_{p['name']}",
                         use_container_width=True, disabled=True)
        else:
            if btn_l.button("设为当前使用", key=f"use_{p['name']}",
                            use_container_width=True):
                providers.set_active(p["name"], STORE_PATH)
                st.rerun()
        if btn_r.button("编辑", key=f"edit_{p['name']}", use_container_width=True):
            edit_provider_dialog(p["name"])


@st.dialog("➕ 添加供应商", width="large")
def add_provider_dialog():
    names = [r["name"] for r in PROVIDER_REGISTRY]
    choice = st.selectbox("提供方", names)
    preset = next(r for r in PROVIDER_REGISTRY if r["name"] == choice)
    default_key = os.getenv(preset.get("key_env", ""), "") if preset.get("key_env") else ""

    base_url = st.text_input("接口地址（Base URL，OpenAI 兼容）",
                             value=preset["base_url"],
                             placeholder="https://.../v1")
    api_key = st.text_input("API Key（本地服务留空即可）", value=default_key,
                            type="password")
    model = st.text_input("模型 ID", value=preset["model"],
                          placeholder="例：deepseek-chat / qwen2.5:7b")
    ctx = st.text_input("上下文窗口（可选）", placeholder="例：65536")

    c1, c2 = st.columns(2)
    if c1.button("取消", use_container_width=True):
        st.rerun()
    if c2.button("完成", type="primary", use_container_width=True):
        if not base_url.strip() or not model.strip():
            st.error("接口地址和模型 ID 必填")
        else:
            providers.upsert_provider({
                "name": choice, "base_url": base_url.strip(),
                "api_key": api_key.strip(), "model": model.strip(),
                "context_window": int(ctx) if ctx.strip().isdigit() else None,
            }, STORE_PATH)
            st.rerun()


@st.dialog("✏️ 编辑供应商", width="large")
def edit_provider_dialog(name: str):
    p = next((x for x in providers.list_providers(STORE_PATH)
              if x["name"] == name), None)
    if p is None:
        st.rerun()
    store = providers.load_store(STORE_PATH)
    if store.get("active") == name:
        st.caption("✅ 当前使用")

    st.text_input("提供方", value=name, disabled=True)
    base_url = st.text_input("接口地址（Base URL，OpenAI 兼容）", value=p["base_url"])
    api_key = st.text_input("API Key（本地服务留空即可）", value=p.get("api_key", ""),
                            type="password")
    model = st.text_input("模型 ID", value=p["model"])
    ctx = st.text_input("上下文窗口（可选）",
                        value=str(p["context_window"] or ""))

    st.divider()
    del_l, _, done_r = st.columns([1, 1, 1])
    if del_l.button("🗑️ 删除供应商", type="primary", use_container_width=True):
        providers.delete_provider(name, STORE_PATH)
        st.rerun()
    if done_r.button("完成", use_container_width=True):
        if not base_url.strip() or not model.strip():
            st.error("接口地址和模型 ID 必填")
        else:
            providers.upsert_provider({
                "name": name, "base_url": base_url.strip(),
                "api_key": api_key.strip(), "model": model.strip(),
                "context_window": int(ctx) if ctx.strip().isdigit() else None,
            }, STORE_PATH)
            st.rerun()
