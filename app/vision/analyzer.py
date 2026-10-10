"""🔬 P9 镜检诊断（路线A）：VLM 看图 → 结构化JSON → 质量门 → 教程RAG + 指示生物匹配。

本模块自包含：整个 app/vision/ 删除不影响其余功能
（页面侧 import 均有 ImportError 兜底）。
"""
import base64
import io
import json
import os
import time
from pathlib import Path

import yaml
from PIL import Image

from app.providers import STORE_PATH, load_store, save_store

RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "indicator_species.yaml"
MICROSCOPY_PREFIX = "data/knowledge/microscopy"

# 默认本地 Ollama；可被 data/models.json 的 "vlm" 字段或 .env 的 VLM_* 覆盖
DEFAULT_VLM = {"base_url": "http://localhost:11434/v1",
               "api_key": "ollama", "model": "qwen2.5vl:7b"}
MAX_SIDE = 1024  # 手机原图太大，统一压到最长边 1024 再传 VLM

ANALYZE_PROMPT = """你是活性污泥镜检助手。仔细观察这张显微镜照片，仅输出一个JSON对象，不要输出任何其他文字：
{
  "image_quality": "足以判断 / 模糊 / 有眩光 / 有气泡干扰 之一",
  "observation": "形态描述（菌胶团、丝状菌、原生/后生动物）",
  "filament_abundance": "+ / ++ / +++ / ++++ 之一（按镜检教程丰度分级）",
  "dominant_organisms": ["类群1", "类群2"],
  "floc_structure": "菌胶团状态描述"
}
红线：
- 生物只写到类群级（钟虫类/轮虫类/丝状菌/游离细菌等），禁止编造具体物种名；
- 图像质量不足以判断时，image_quality 如实填写，其余四个字段一律填 null，不得猜测。"""

MICROSCOPY_SYSTEM = """你是污水处理厂的资深工艺工程师助手，基于镜检观察结果做生物相分析。
输入包含：VLM 对镜检图像的结构化描述，以及检索到的镜检教程参考资料。

请按以下结构输出（Markdown）：
## 生物相解读
依据教程资料说明各观察对象的指示意义，逐条标注来源文件名。
## 处置方向
给出可操作的处置建议，每条注明"执行前须经工艺工程师或值班长确认"。
## 依据来源
列出引用的教程片段，格式：[来源: 文件名]

红线：参考资料未覆盖的内容可用通用工艺知识补充，并注明"（通用经验）"；
不得编造观察描述中不存在的生物；不得与教程资料矛盾。"""


# ===================== 配置 =====================

def get_vlm_config(path: Path = STORE_PATH) -> dict:
    """视觉模型配置：.env 的 VLM_* > store['vlm'] > DEFAULT_VLM"""
    cfg = dict(DEFAULT_VLM)
    try:
        cfg.update(load_store(path).get("vlm") or {})
    except Exception:
        pass  # store 读取失败时用默认配置，不阻塞诊断页
    for env_key, cfg_key in (("VLM_BASE_URL", "base_url"),
                             ("VLM_API_KEY", "api_key"),
                             ("VLM_MODEL", "model")):
        if os.getenv(env_key):
            cfg[cfg_key] = os.getenv(env_key)
    return cfg


def save_vlm_config(cfg: dict, path: Path = STORE_PATH) -> None:
    store = load_store(path)
    store["vlm"] = {"base_url": cfg.get("base_url", ""),
                    "api_key": cfg.get("api_key", ""),
                    "model": cfg.get("model", "")}
    save_store(store, path)


# ===================== 纯函数（可测） =====================

def downscale_image(img_bytes: bytes, max_side: int = MAX_SIDE) -> bytes:
    """手机大图 → 最长边 max_side 的 JPEG（质量85）；解析失败原样返回"""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.load()
    except Exception:
        return img_bytes
    img.thumbnail((max_side, max_side))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def to_data_url(img_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()


def build_image_message(prompt: str, data_url: str) -> list:
    """OpenAI 兼容的视觉消息（llm.chat 原样透传）"""
    return [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]


def build_vlm_fn(cfg: dict):
    """绑定视觉模型预设的 vlm_fn(messages) -> str"""
    from app.agent.llm import chat

    def _vlm(messages: list) -> str:
        return chat(messages, model=cfg["model"], base_url=cfg["base_url"],
                    api_key=cfg.get("api_key") or None)

    return _vlm


def parse_vlm_json(text: str) -> dict | None:
    """容错解析 VLM 输出：剥 ```json 围栏 → 取首个 '{' 到配对 '}' → json.loads"""
    if not text:
        return None
    candidates = [text.strip()]
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
    for cand in candidates:
        cand = cand.strip()
        if cand.startswith("```"):
            cand = cand.strip("`").lstrip("json").strip()
        try:
            data = json.loads(cand)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return None


def is_quality_ok(result: dict | None) -> bool:
    """质量门：image_quality 含'足以' 且 其余四字段全部非空才放行（防硬编）"""
    if not isinstance(result, dict):
        return False
    if "足以" not in str(result.get("image_quality") or ""):
        return False
    for key in ("observation", "filament_abundance",
                "dominant_organisms", "floc_structure"):
        if not result.get(key):
            return False
    return True


def _prefer_microscopy(hits: list[dict], limit: int = 5) -> list[dict]:
    """教程库命中排前，其余（SOP 等含镜检段落的文档）按距离跟随，截 limit 条"""
    micro = [h for h in hits if h.get("source", "").startswith(MICROSCOPY_PREFIX)]
    rest = [h for h in hits if not h.get("source", "").startswith(MICROSCOPY_PREFIX)]
    return (micro + rest)[:limit]


# ===================== 主流程 =====================

def analyze_image(img_bytes: bytes, cfg: dict, vlm_fn=None) -> dict:
    """VLM 看图 → {'result': dict|None, 'raw': str}；解析失败 result=None（走质量不足提示）"""
    if vlm_fn is None:
        vlm_fn = build_vlm_fn(cfg)
    small = downscale_image(img_bytes)
    messages = build_image_message(ANALYZE_PROMPT, to_data_url(small))
    raw = vlm_fn(messages)
    return {"result": parse_vlm_json(raw), "raw": raw or ""}


def explain(obs_desc: str, hits: list[dict], chat_fn) -> str:
    """VLM 描述 + 教程检索片段 → 带引用的生物相解读（用文字诊断的语言模型）"""
    refs = "\n\n".join(
        f"【资料片段 {i}】（来源: {h['source']}）\n{h['text']}"
        for i, h in enumerate(hits, 1)) or "（知识库暂无命中，请基于通用工艺知识解读并注明）"
    user = f"【VLM镜检观察】\n{obs_desc}\n\n【教程参考资料】\n{refs}"
    return chat_fn([{"role": "system", "content": MICROSCOPY_SYSTEM},
                    {"role": "user", "content": user}])


def vision_ping(cfg: dict) -> tuple[bool, float, str]:
    """视觉模型连通性测试：发一张 8x8 纯色小图（模仿 providers.ping 的返回签名）"""
    from openai import OpenAI

    img = Image.new("RGB", (8, 8), (200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    messages = build_image_message("图中是什么颜色？只回答颜色词。",
                                   to_data_url(buf.getvalue()))
    client = OpenAI(base_url=cfg["base_url"],
                    api_key=cfg.get("api_key") or "ollama", timeout=60)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(model=cfg["model"],
                                              messages=messages, max_tokens=16)
        return True, time.time() - t0, (resp.choices[0].message.content or "").strip()[:60]
    except Exception as e:
        return False, time.time() - t0, f"{type(e).__name__}: {e}"


def load_species_rules(path: Path = RULES_PATH) -> list[dict]:
    """指示生物对照表；文件缺失/为空返回 []（容错，不阻塞）"""
    if not path.exists():
        return []
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []
