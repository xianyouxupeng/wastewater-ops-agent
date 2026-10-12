"""L3 运行记忆：台账条目持久化（jsonl）+ 最近参数读取与汇总。

台账页每次生成 Word 时同步落盘到 data/ledger/ledger.jsonl（V1 台账只导出不保存，
诊断时无据可查，这是 V2.1 补上的数据源）。字段映射集中在本文件一处。
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

LEDGER_FILE = Path(__file__).resolve().parents[2] / "data" / "ledger" / "ledger.jsonl"

# 台账表单字段 → 中文名（prompt 展示用）
FIELD_LABELS = {
    "inlet_cod": "进水COD", "outlet_cod": "出水COD",
    "inlet_nh3n": "进水氨氮", "outlet_nh3n": "出水氨氮",
    "outlet_tn": "出水TN", "outlet_tp": "出水TP", "outlet_ss": "出水SS",
    "inlet_ph": "进水pH", "outlet_ph": "出水pH",
    "flow": "处理水量", "temp": "水温", "do": "DO",
    "mlss": "MLSS", "sv30": "SV30", "svi": "SVI",
    "pac": "PAC药耗", "power": "电耗",
}
# 出水指标 → 厂情档案「排放限值」的键（超标判定用）
OUTLET_LIMIT_KEYS = {"outlet_cod": "COD", "outlet_nh3n": "氨氮",
                     "outlet_tn": "TN", "outlet_tp": "TP", "outlet_ss": "SS"}


def append_entry(entry: dict, path: Path = LEDGER_FILE) -> None:
    """追加一条台账到运行记忆（去空字段），供诊断时回读"""
    clean = {k: v for k, v in entry.items()
             if v is not None and str(v).strip() != ""}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(clean, ensure_ascii=False) + "\n")


def load_entries(path: Path = LEDGER_FILE) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 坏行跳过，不阻塞诊断
    return entries


def get_recent_params(days: int = 7, path: Path = LEDGER_FILE,
                      today: date | None = None) -> list[dict]:
    """取最近 N 天台账（按日期升序）。无日期/日期非法的条目跳过"""
    today = today or date.today()
    since = today - timedelta(days=days)
    recent = []
    for e in load_entries(path):
        try:
            if date.fromisoformat(str(e.get("date", ""))) >= since:
                recent.append(e)
        except ValueError:
            continue
    recent.sort(key=lambda e: str(e.get("date", "")))
    return recent


def _as_float(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _base_limit(value) -> float | None:
    """限值取基础数字：50 → 50；\"5(8)\" → 5（括号为季节性限值）"""
    m = re.search(r"\d+(\.\d+)?", str(value))
    return float(m.group()) if m else None


def _trend_line(entries: list[dict], limits: dict) -> str:
    """趋势段：数值字段首→末变化（涨幅≥15% 才显示），+ 超标记录"""
    trends = []
    for key, label in FIELD_LABELS.items():
        points = [(_as_float(e.get(key))) for e in entries]
        points = [p for p in points if p is not None]
        if len(points) >= 2 and points[-1] != points[0] and points[0] != 0:
            pct = (points[-1] - points[0]) / abs(points[0]) * 100
            if abs(pct) >= 15:
                trends.append(f"{label} {points[0]:g}→{points[-1]:g}（{pct:+.0f}%）")
    lines = ["- 趋势：" + "；".join(trends) if trends else ""]

    exceeds = []
    for e in entries:
        for key, limit_key in OUTLET_LIMIT_KEYS.items():
            value = _as_float(e.get(key))
            limit = _base_limit(limits.get(limit_key, ""))
            if value is not None and limit is not None and value > limit:
                exceeds.append(f"{e.get('date', '')} {FIELD_LABELS[key]}={value:g}"
                               f" 超限值 {limit:g}")
    if exceeds:
        lines.append("- 超标：" + "；".join(exceeds[-5:]))  # 最多列 5 条防刷屏
    return "\n".join(line for line in lines if line)


def runtime_block(entries: list[dict] | None = None, days: int = 7,
                  limits: dict | None = None, today: date | None = None) -> str:
    """台账 → prompt 文本块。无数据返回空串（调用方判空跳过注入）。

    entries/limits 可注入替换（纯函数测试不依赖文件与厂情档案）。
    """
    if entries is None:
        entries = get_recent_params(days=days, today=today)
    if not entries:
        return ""
    if limits is None:
        from app.memory.plant import load_plant_profile
        limits = load_plant_profile().get("排放限值") or {}

    lines = [f"【最近运行台账（本厂实录，近 {days} 天）】"]
    for e in entries:
        parts = [f"{label}={e[key]}" for key, label in FIELD_LABELS.items()
                 if e.get(key) not in (None, "")]
        shift = f"/{e['shift']}" if e.get("shift") else ""
        line = f"- {e.get('date', '')}{shift}：" + "，".join(parts)
        note = e.get("abnormal") or e.get("summary") or ""
        if note:
            line += f"；备注：{note[:40]}"
        lines.append(line)
    trend = _trend_line(entries, limits)
    if trend:
        lines.append(trend)
    return "\n".join(lines)
