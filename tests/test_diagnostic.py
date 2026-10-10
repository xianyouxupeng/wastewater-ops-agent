"""故障树匹配与未命中兜底的纯函数测试（不依赖LLM）"""
from app.diagnostic.engine import (
    FALLBACK_WARNING,
    diagnose,
    load_fault_trees,
    match_trees,
)


def fake_chat(messages):
    return "（模拟LLM回复）"


def test_load_trees():
    trees = load_fault_trees()
    assert len(trees) == 10
    ids = {t["id"] for t in trees}
    assert "nh3n_exceed" in ids
    assert "instrument_drift" in ids


def test_match_single_hit():
    trees = load_fault_trees()
    matched = match_trees("出水氨氮超标，DO偏低，MLSS偏高", trees)
    assert matched[0]["id"] == "nh3n_exceed"


def test_match_multi_hit():
    trees = load_fault_trees()
    matched = match_trees("二沉池漂泥，镜检丝状菌多，SV30升高", trees)
    ids = [t["id"] for t in matched]
    assert "clarifier_float" in ids
    assert "sludge_bulking" in ids


def test_match_unmatched_returns_empty():
    trees = load_fault_trees()
    assert match_trees("格栅压差高，皮带输送机跳闸", trees) == []


def test_diagnose_unmatched_has_fallback_warning():
    """P8 必测项：未命中时输出含'低置信度'声明，不依赖LLM"""
    out = diagnose("格栅压差高，皮带输送机跳闸", chat_fn=fake_chat)
    assert out.startswith(FALLBACK_WARNING)
    assert "低置信度" in out


def test_diagnose_matched_no_warning():
    out = diagnose("出水氨氮超标，DO偏低", chat_fn=fake_chat)
    assert not out.startswith(FALLBACK_WARNING)
