"""L2 厂情档案：data/plant_profile.yaml 加载/保存 → 注入 prompt 的文本块。

注入策略：结构化数据直接拼文本全量注入，不走向量检索（数据量小且每次都要用）。
缺失处理：文件缺失 / 内容为空 / 单字段留空 → 对应部分不注入，不报错。
填写方式：推荐「设置 → 厂情档案」界面表单（save_plant_profile 落盘），也可手改本文件。
"""
import re
from pathlib import Path

import yaml

PROFILE_PATH = Path(__file__).resolve().parents[2] / "data" / "plant_profile.yaml"

# 档案文件中可能出现的顶层字段（按注入顺序）
_PROFILE_FIELDS = ("厂名", "工艺", "设计规模", "排放标准", "排放限值",
                   "设计参数", "常用药剂", "主要设备", "特殊说明")


def load_plant_profile(path: Path = PROFILE_PATH) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def save_plant_profile(profile: dict, path: Path = PROFILE_PATH) -> None:
    """厂情档案落盘（设置页表单保存用）。空字段不写入，保持"缺什么补什么"语义"""
    clean = {}
    for k, v in profile.items():
        if isinstance(v, dict):
            v = {sk: sv for sk, sv in v.items() if sv not in (None, "")}
            if v:
                clean[k] = v
        elif v not in (None, ""):
            clean[k] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(clean, f, allow_unicode=True, sort_keys=False)


def is_profile_filled(profile: dict | None = None) -> bool:
    """厂名+工艺 已填视为完成首次配置（诊断/问答页首次使用引导的判断依据）"""
    if profile is None:
        profile = load_plant_profile()
    return bool(_filled(profile.get("厂名")) and _filled(profile.get("工艺")))


def parse_limit(value) -> tuple[str, str]:
    """限值拆解："5(8)" → ("5", "8")；50 → ("50", "")；无 → ("", "")"""
    text = str(value or "").strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:[（(]\s*(\d+(?:\.\d+)?)\s*[）)])?$", text)
    if not m:
        return ("", "")
    return (m.group(1), m.group(2) or "")


def _filled(value) -> bool:
    """空值判断：None / 空串 / 全空白视为未填写"""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _format_mapping(mapping: dict) -> str:
    """{除磷: PAC, 碳源: 乙酸钠} → '除磷=PAC；碳源=乙酸钠'（空子项跳过）"""
    return "；".join(f"{k}={v}" for k, v in mapping.items() if _filled(v))


def plant_profile_block(profile: dict | None = None) -> str:
    """厂情档案 → prompt 文本块。档案为空返回空串（调用方判空即可跳过注入）"""
    if profile is None:
        profile = load_plant_profile()
    lines = []
    for field in _PROFILE_FIELDS:
        value = profile.get(field)
        if not _filled(value):
            continue
        if isinstance(value, dict):
            text = _format_mapping(value)
            if not text:
                continue
        elif field == "特殊说明":
            text = value.strip()
        else:
            text = str(value).strip()
        lines.append(f"- {field}：{text}")
    if not lines:
        return ""
    return "【本厂档案（诊断/回答请结合本厂工况）】\n" + "\n".join(lines)
