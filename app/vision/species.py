"""🧬 指示生物对照表加载与匹配（纯函数，不依赖 LLM/网络）"""
from pathlib import Path

from app.vision.analyzer import RULES_PATH


def load_species(path: Path = RULES_PATH) -> list[dict]:
    """加载 data/rules/indicator_species.yaml；缺失/为空返回 []（容错）"""
    from app.vision.analyzer import load_species_rules
    return load_species_rules(path)


def organism_key(entry: dict) -> str:
    """'钟虫（大量、活跃）' → '钟虫'：取全角'（'前的基础名"""
    name = str(entry.get("organism", ""))
    return name.split("（", 1)[0].strip()


def match_species(text: str, rules: list[dict]) -> list[dict]:
    """基础名与 VLM 描述文本（dominant_organisms + observation）做子串匹配。

    只按名字命中（'大量/优势'等程度词不参与判定，避免 VLM 漏写导致漏报），
    程度词原样透传给解读 prompt。
    """
    if not text:
        return []
    hits = []
    for rule in rules:
        key = organism_key(rule)
        if key and key in text:
            hits.append({"organism": rule.get("organism", key),
                         "meaning": rule.get("meaning", ""),
                         "action": rule.get("action", ""),
                         "fault_tree_ref": rule.get("fault_tree_ref")})
    return hits


def filament_level(abundance) -> int:
    """'+/++/+++/++++' → 1..4；None/异常 → 0"""
    if not abundance:
        return 0
    return str(abundance).count("+")


def bulking_trigger(result: dict, matches: list[dict]) -> dict | None:
    """污泥膨胀触发判定：丝状菌丰度 ≥+++ 或命中带 fault_tree_ref 的条目。

    返回 {'tree_id', 'prefill'}（prefill 用于预填文字诊断，命中故障树 phenomenon
    关键词"污泥膨胀"）；不满足返回 None。
    """
    if not isinstance(result, dict):
        return None
    ref = next((m["fault_tree_ref"] for m in matches if m.get("fault_tree_ref")), None)
    if ref:
        level = filament_level(result.get("filament_abundance"))
        abundance = result.get("filament_abundance") or "未分级"
        return {"tree_id": ref,
                "prefill": f"污泥膨胀：镜检提示丝状菌丰度{abundance}（≥+++），"
                           f"SV30升高，二沉池有漂泥倾向，请按{ref}流程鉴别排查"}
    if filament_level(result.get("filament_abundance")) >= 3:
        return {"tree_id": "sludge_bulking",
                "prefill": "污泥膨胀：镜检丝状菌丰度≥+++，SV30升高，"
                           "二沉池有漂泥倾向，请按污泥膨胀流程鉴别排查"}
    return None
