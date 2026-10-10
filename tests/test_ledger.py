"""台账生成测试（不依赖LLM/网络）"""
from app.ledger.report_generator import generate_report, render_markdown


def test_render_markdown_fills_fields():
    md = render_markdown({"plant_name": "测试厂", "date": "2026-10-10",
                          "inlet_cod": "400", "outlet_cod": "45"})
    assert "测试厂 运行台账" in md
    assert "2026-10-10" in md
    assert "| 400 |" in md or "400" in md


def test_render_markdown_defaults_placeholder():
    """缺项字段显示占位符，不出现 Jinja2 未渲染标记"""
    md = render_markdown({})
    assert "{{" not in md
    assert "—" in md


def test_generate_report_returns_docx():
    """输出为非空 docx（zip 魔数 PK）"""
    data = generate_report({"plant_name": "测试厂", "date": "2026-10-10"})
    assert data[:2] == b"PK"
    assert len(data) > 1000
