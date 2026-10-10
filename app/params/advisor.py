"""参数辅助建议：解析输入中的参数与方向 → 规则匹配 → 生成建议卡。

纯规则、确定性输出（不依赖LLM），P8 有纯函数测试断言免责声明。
免责声明已含 P8 测试要求的"仅人工参考"字样。
"""
import re
from pathlib import Path

import yaml

RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules" / "param_ranges.yaml"

DISCLAIMER = ("⚠️ 以上仅为辅助建议，仅供人工参考，"
              "执行前必须经工艺工程师或值班长确认，禁止直接自动执行。")

NO_MATCH_REPLY = "未匹配到参数规则。可尝试描述如“DO 1.5，氨氮偏高”。"

# 参数别名（长词优先匹配，避免"进水COD"被拆成"COD"）
PARAM_ALIASES = {
    "进水COD": ["进水COD", "进水cod"],
    "出水COD": ["出水COD", "出水cod"],
    "COD": ["COD", "cod"],
    "DO": ["DO", "溶解氧"],
    "MLSS": ["MLSS", "污泥浓度"],
    "SV30": ["SV30", "沉降比"],
    "SVI": ["SVI"],
    "氨氮": ["氨氮", "NH3-N", "NH4+"],
    "TN": ["TN", "总氮"],
    "TP": ["TP", "总磷"],
    "pH": ["pH", "PH"],
}

HIGH_HINTS = ("偏高", "过高", "超标", "升高", "上涨", "骤升", "高")
LOW_HINTS = ("偏低", "过低", "不足", "下降", "骤降", "降低", "低")

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_COND_RE = re.compile(r"(>=|<=|>|<)\s*(\d+(?:\.\d+)?)")


def load_rules(path: Path = RULES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_params(text: str) -> dict[str, dict]:
    """从输入中提取 {规范参数名: {"value": float|None, "direction": "high"|"low"|None}}"""
    # 按 alias 长度降序扫描并遮盖已占用区间（"进水COD"优先于"COD"）
    found: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    aliases = sorted(((a, p) for p, alist in PARAM_ALIASES.items() for a in alist),
                     key=lambda pair: -len(pair[0]))
    for alias, param in aliases:
        for m in re.finditer(re.escape(alias), text):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in occupied):
                continue  # 与更长别名重叠，跳过
            occupied.append(span)
            found.append((*span, param))
    found.sort()

    facts: dict[str, dict] = {}
    for (start, end, param), (_, next_start, _) in zip(
            found, found[1:] + [(len(text), len(text), "")]):
        segment = text[end:next_start]
        value = _NUM_RE.search(segment)
        direction = _detect_direction(segment)
        facts[param] = {"value": float(value.group()) if value else None,
                        "direction": direction}
    return facts


def _detect_direction(text: str) -> str | None:
    """多字方向词优先于单字（"超标"先于"高"）"""
    for hint in HIGH_HINTS:
        if hint in text:
            return "high"
    for hint in LOW_HINTS:
        if hint in text:
            return "low"
    return None


def _condition_met(value: float, condition: str) -> bool:
    m = _COND_RE.fullmatch(condition.strip())
    op, threshold = m.group(1), float(m.group(2))
    return {">": value > threshold, "<": value < threshold,
            ">=": value >= threshold, "<=": value <= threshold}[op]


def match_rules(facts: dict[str, dict], rules: list[dict]) -> list[dict]:
    """数值输入按 condition 判断；方向输入按 direction 匹配；两者任一命中即命中"""
    hits = []
    for rule in rules:
        fact = facts.get(rule["param"])
        if not fact:
            continue
        hit = (fact["value"] is not None and rule.get("condition")
               and _condition_met(fact["value"], rule["condition"]))
        if not hit and fact["direction"] and rule.get("direction") == fact["direction"]:
            hit = True
        if hit:
            hits.append(rule)
    return hits


def format_advice(rule: dict) -> str:
    """单条建议卡（markdown）"""
    lines = [f"### 💡 {rule['title']}",
             f"- **目标范围**：{rule['target']}"]
    lines.append("- **调整动作**：")
    lines += [f"  {i}. {a}" for i, a in enumerate(rule["actions"], 1)]
    lines.append("- **风险提示**：")
    lines += [f"  - {r}" for r in rule["risks"]]
    lines.append(f"- **观察指标**：{'、'.join(rule['watch'])}")
    lines.append(f"- **复测时间**：{rule['recheck']}")
    return "\n".join(lines)


def suggest(text: str, rules: list[dict] | None = None) -> str:
    """参数建议主入口：建议卡（可能多条）+ 固定免责声明"""
    if rules is None:
        rules = load_rules()
    hits = match_rules(parse_params(text), rules)
    if not hits:
        return f"{NO_MATCH_REPLY}\n\n{DISCLAIMER}"
    cards = "\n\n---\n\n".join(format_advice(r) for r in hits)
    return f"{cards}\n\n---\n\n{DISCLAIMER}"
