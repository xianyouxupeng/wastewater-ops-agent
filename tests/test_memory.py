"""V2.1 记忆系统测试（全纯函数注入，不依赖 LLM/文件外的外部状态）

文档要求必测：记忆注入的 prompt 构造、案例沉淀写入。
"""
import json
from datetime import date

from app.diagnostic import engine
from app.memory import runtime, session
from app.memory.plant import plant_profile_block
from app.rag import cases as cases_mod


# ---------- L2 厂情档案 ----------

def test_plant_block_contains_fields():
    """档案块含已填关键字段（厂内信息以用户填写为准，不依赖仓库预置数据）"""
    block = plant_profile_block({"工艺": "A/O", "排放限值": {"COD": 50},
                                 "常用药剂": {"除磷": "PAC"}})
    assert block.startswith("【本厂档案")
    for field in ("工艺", "排放限值", "常用药剂"):
        assert field in block


def test_plant_block_skips_empty_fields():
    block = plant_profile_block({"厂名": "", "工艺": "A/O", "排放限值": {}})
    assert "厂名" not in block
    assert "A/O" in block
    assert "排放限值" not in block  # 空字典不注入


def test_plant_block_missing_file_returns_empty(tmp_path):
    from app.memory.plant import load_plant_profile
    assert load_plant_profile(tmp_path / "nope.yaml") == {}
    assert plant_profile_block({}) == ""


def test_plant_block_empty_profile_returns_empty(tmp_path):
    assert plant_profile_block({}) == ""


# ---------- L3 运行记忆 ----------

def _entry(d, **kw):
    return {"date": d, **kw}


def test_runtime_block_empty_when_no_entries():
    assert runtime.runtime_block(entries=[]) == ""


def test_runtime_block_contains_params_and_exceedance():
    limits = {"氨氮": "5(8)"}
    entries = [_entry("2026-10-10", outlet_nh3n="6.2", do="3.1"),
               _entry("2026-10-11", outlet_nh3n="7.5", do="3.0")]
    block = runtime.runtime_block(entries=entries, limits=limits)
    assert "2026-10-10" in block and "出水氨氮=6.2" in block
    assert "超限值 5" in block  # "5(8)" 取基础限值 5


def test_runtime_block_trend_shown_above_threshold():
    entries = [_entry("2026-10-09", inlet_nh3n="28"),
               _entry("2026-10-11", inlet_nh3n="45")]
    block = runtime.runtime_block(entries=entries, limits={})
    assert "进水氨氮 28→45" in block and "+61%" in block


def test_runtime_block_trend_hidden_below_threshold():
    entries = [_entry("2026-10-09", do="3.0"),
               _entry("2026-10-11", do="3.1")]
    block = runtime.runtime_block(entries=entries, limits={})
    assert "趋势" not in block  # +3% 不到 15% 阈值，不刷屏


def test_get_recent_params_filters_by_days(tmp_path):
    f = tmp_path / "ledger.jsonl"
    today = date(2026, 10, 12)
    rows = [_entry("2026-10-01", do="2.0"),       # 15 天前，应被过滤
            _entry("2026-10-10", do="3.0"),
            _entry("bad-date", do="9.9"),          # 非法日期跳过
            _entry("2026-10-11", do="3.2")]
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                 encoding="utf-8")
    recent = runtime.get_recent_params(days=7, path=f, today=today)
    assert [e["date"] for e in recent] == ["2026-10-10", "2026-10-11"]


def test_append_entry_drops_empty_and_loads_back(tmp_path):
    f = tmp_path / "ledger.jsonl"
    runtime.append_entry({"date": "2026-10-12", "do": "3.1", "sv30": ""}, path=f)
    loaded = runtime.load_entries(f)
    assert loaded == [{"date": "2026-10-12", "do": "3.1"}]


# ---------- L1 会话记忆 ----------

def test_session_trim_keeps_recent():
    hist = [{"role": "user", "content": str(i)} for i in range(20)]
    trimmed = session.trim(hist, keep=5)
    assert len(trimmed) == 5
    assert trimmed[-1]["content"] == "19"


def test_session_trim_empty():
    assert session.trim(None) == []
    assert session.trim([]) == []


def test_history_text_format():
    hist = [{"role": "user", "content": "出水氨氮高"},
            {"role": "assistant", "content": "建议查DO"}]
    text = session.history_text(hist)
    assert "用户：出水氨氮高" in text
    assert "助手：建议查DO" in text
    assert session.history_text(None) == ""


# ---------- 注入 prompt 构造 ----------

def test_build_messages_injects_memory_blocks():
    msgs = engine.build_messages(
        "出水氨氮高", [{"id": "nh3n_exceed"}],
        plant_block="【本厂档案】\n- 工艺：A/O",
        runtime="【最近运行台账】\n- 2026-10-11：出水氨氮=7.5",
        history=[{"role": "user", "content": "昨天也偏高"}])
    content = msgs[1]["content"]
    assert "【命中的故障树条目】" in content
    assert "【本厂档案" in content
    assert "【最近运行台账】" in content
    assert "【本轮之前的对话" in content and "昨天也偏高" in content


def test_diagnose_injects_profile(monkeypatch):
    """端到端（无LLM）：diagnose 应把厂情档案注入 prompt（注入合成档案，不依赖仓库文件）"""
    monkeypatch.setattr(engine, "plant_profile_block",
                        lambda *a, **k: "【本厂档案】\n- 工艺：A/O")
    captured = {}

    def fake_chat(messages):
        captured["content"] = messages[1]["content"]
        return "（模拟回复）"

    engine.diagnose("出水氨氮超标", chat_fn=fake_chat)
    assert "【本厂档案" in captured["content"]


def test_diagnose_memory_failure_degrades_silently(monkeypatch):
    monkeypatch.setattr(engine, "plant_profile_block",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    monkeypatch.setattr(engine, "runtime_block",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    out = engine.diagnose("出水氨氮超标", chat_fn=lambda m: "ok")
    assert "ok" in out  # 记忆挂掉不阻塞诊断


# ---------- L4 案例沉淀 ----------

def test_add_case_auto_id_and_defaults(tmp_path):
    f = tmp_path / "cases.jsonl"
    c1 = cases_mod.add_case({"现象": "氨氮高", "原因": "负荷冲击"}, path=f)
    assert c1["id"] == "C001"
    assert c1["日期"] == date.today().isoformat()
    assert c1["来源"] == "诊断沉淀"
    c2 = cases_mod.add_case({"现象": "SV30高", "原因": "丝状菌"}, path=f)
    assert c2["id"] == "C002"  # 沿既有编号递增
    assert len(cases_mod.load_cases(f)) == 2


def test_add_case_keeps_explicit_fields(tmp_path):
    f = tmp_path / "cases.jsonl"
    c = cases_mod.add_case({"id": "X9", "现象": "s", "日期": "2026-01-01"}, path=f)
    assert c["id"] == "X9" and c["日期"] == "2026-01-01"


def test_add_case_minimal_fields_still_retrievable_text(tmp_path):
    """沉淀案例的字段要能被 case_text/format_case 正常消费"""
    f = tmp_path / "cases.jsonl"
    c = cases_mod.add_case({"现象": "泡沫多", "原因": "放线菌",
                            "处置": "降低MLSS", "结果": "消退"}, path=f)
    assert "放线菌" in cases_mod.case_text(c)
    assert "放线菌" in cases_mod.format_case(c)


# ---------- 问答注入 ----------

def test_qa_build_messages_with_plant_and_history():
    from app.rag import qa
    hits = [{"text": "片段", "source": "a.md"}]
    hist = [{"role": "user", "content": "之前的问题"}]
    msgs = qa.build_messages("钟虫尺寸", hits,
                             plant_block="【本厂档案】\n- 工艺：A/O", history=hist)
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "之前的问题"}  # 历史插在中间
    user = msgs[2]["content"]
    assert "[1] 来源: a.md" in user and "【本厂档案】" in user


# ---------- 厂情档案界面保存（设置页表单落盘） ----------

def test_save_plant_profile_roundtrip(tmp_path):
    from app.memory.plant import load_plant_profile, save_plant_profile
    f = tmp_path / "plant_profile.yaml"
    save_plant_profile({"厂名": "测试厂", "工艺": "A²/O（厌氧/缺氧/好氧）",
                        "排放限值": {"COD": "50", "氨氮": "5(8)", "TN": ""},
                        "主要设备": "罗茨鼓风机3台"}, path=f)
    loaded = load_plant_profile(f)
    assert loaded["厂名"] == "测试厂"
    assert loaded["排放限值"]["氨氮"] == "5(8)"
    assert "TN" not in loaded["排放限值"]  # 空子项不写入（缺失不注入）
    assert loaded["主要设备"] == "罗茨鼓风机3台"


def test_is_profile_filled():
    from app.memory.plant import is_profile_filled
    assert not is_profile_filled({})                       # 空档案
    assert not is_profile_filled({"厂名": "", "工艺": "A/O"})  # 模板默认（厂名未填）
    assert is_profile_filled({"厂名": "XX厂", "工艺": "A/O"})
    assert not is_profile_filled({"厂名": "  ", "工艺": "A/O"})  # 全空白


def test_parse_limit_variants():
    from app.memory.plant import parse_limit
    assert parse_limit("5(8)") == ("5", "8")
    assert parse_limit("5（8）") == ("5", "8")  # 全角括号
    assert parse_limit("50") == ("50", "")
    assert parse_limit("") == ("", "")
    assert parse_limit(None) == ("", "")
