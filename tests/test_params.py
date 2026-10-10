"""参数建议纯函数测试（不依赖LLM）"""
from app.params.advisor import parse_params, match_rules, suggest, load_rules


def test_parse_numeric_and_direction():
    facts = parse_params("DO 1.5，氨氮偏高")
    assert facts["DO"]["value"] == 1.5
    assert facts["氨氮"]["direction"] == "high"


def test_alias_priority_inlet_cod():
    """“进水COD”不得被拆成“COD”"""
    facts = parse_params("进水COD 900")
    assert "进水COD" in facts
    assert facts["进水COD"]["value"] == 900.0


def test_match_by_value_and_direction():
    rules = load_rules()
    # 数值命中：DO 1.5 < 2.0
    hits = match_rules(parse_params("DO 1.5"), rules)
    assert any(r["id"] == "do_low" for r in hits)
    # 方向命中：氨氮偏高
    hits = match_rules(parse_params("氨氮偏高"), rules)
    assert any(r["id"] == "nh3n_high" for r in hits)
    # 数值正常不命中：DO 3.0 不触发 do_low / do_high
    hits = match_rules(parse_params("DO 3.0"), rules)
    assert not any(r["id"] in ("do_low", "do_high") for r in hits)


def test_suggest_contains_disclaimer():
    """P8 必测：输出必含免责声明（“仅供人工参考”字样）"""
    out = suggest("DO 1.5，氨氮偏高")
    assert "仅供人工参考" in out
    assert "禁止直接自动执行" in out
    assert "DO 偏低" in out and "氨氮偏高" in out


def test_suggest_no_match_still_disclaims():
    out = suggest("今天天气不错")
    assert "仅供人工参考" in out
