"""👁️ 视觉模型设置（设置页「视觉模型」tab 的渲染，独立于 providers 注册表）"""
import os

import streamlit as st

from app.vision.analyzer import get_vlm_config, save_vlm_config, vision_ping

# VLM 预设（与 providers.PROVIDER_REGISTRY 独立：视觉模型不需要 embedding/上下文窗口字段）
VLM_PRESETS = [
    {"name": "Ollama 本地", "base_url": "http://localhost:11434/v1",
     "api_key": "ollama", "model": "qwen2.5vl:7b"},
    {"name": "阿里云百炼", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "model": "qwen-vl-plus", "key_env": "DASHSCOPE_API_KEY"},
    {"name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "model": "glm-4v-flash", "key_env": "ZHIPU_API_KEY"},
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1",
     "model": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"},
]


def render_vlm_settings():
    st.caption("视觉模型仅用于「故障诊断 → 镜检诊断」的图像识别；"
               "不配置时默认本地 Ollama qwen2.5vl:7b。")
    cfg = get_vlm_config()
    st.caption(f"当前生效：**{cfg['model']}** @ `{cfg['base_url']}`")

    names = [p["name"] for p in VLM_PRESETS] + ["自定义"]
    default_idx = next((i for i, p in enumerate(VLM_PRESETS)
                        if p["base_url"] == cfg["base_url"]), len(VLM_PRESETS))
    choice = st.selectbox("提供方", names, index=default_idx)

    if choice != "自定义":
        preset = VLM_PRESETS[names.index(choice)]
        default_key = os.getenv(preset.get("key_env", ""), "") if preset.get("key_env") else ""
        st.caption(f"预设模型：{preset['model']}")
    else:
        preset, default_key = {"base_url": "", "model": ""}, ""

    base_url = st.text_input("接口地址（Base URL，OpenAI 兼容）",
                             value=preset["base_url"] or cfg["base_url"],
                             placeholder="http://localhost:11434/v1")
    api_key = st.text_input("API Key（本地服务留空即可）",
                            value=cfg.get("api_key", "") or default_key,
                            type="password")
    model = st.text_input("模型 ID",
                          value=preset.get("model") or cfg["model"],
                          placeholder="例：qwen2.5vl:7b / qwen-vl-plus")

    c1, c2 = st.columns(2)
    if c1.button("💾 保存配置", type="primary", use_container_width=True):
        if not base_url.strip() or not model.strip():
            st.error("接口地址和模型 ID 必填")
        else:
            save_vlm_config({"base_url": base_url.strip(),
                             "api_key": api_key.strip(), "model": model.strip()})
            st.success("已保存，镜检诊断页即可使用")

    if c2.button("🩺 连通性测试", use_container_width=True):
        if not base_url.strip() or not model.strip():
            st.error("接口地址和模型 ID 必填")
        else:
            with st.spinner("发送测试图片中（本地模型首次加载较慢）..."):
                ok, secs, detail = vision_ping({"base_url": base_url.strip(),
                                                "api_key": api_key.strip(),
                                                "model": model.strip()})
        if ok:
            st.success(f"✓ 视觉接口正常　{secs:.1f}s　{detail}")
        else:
            st.error(f"✗ {secs:.1f}s　{detail}")
            st.caption("常见原因：模型 ID 不存在（先 ollama pull）、Ollama 版本过旧"
                       "（需支持 OpenAI 兼容视觉接口）、服务未启动。")
