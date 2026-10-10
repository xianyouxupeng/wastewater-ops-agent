"""P9 镜检诊断纯函数测试（不依赖 LLM/网络）

覆盖：图像压缩/消息构造、VLM JSON 容错解析、质量门、
指示生物加载与匹配、膨胀触发判定、教程检索排序。
"""
import io

import pytest
from PIL import Image

from app.vision import analyzer, species


def _jpeg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


# ---------- 图像处理 ----------

def test_downscale_image_caps_max_side():
    small = analyzer.downscale_image(_jpeg(3000, 2000))
    img = Image.open(io.BytesIO(small))
    assert max(img.size) <= analyzer.MAX_SIDE


def test_downscale_image_small_image_unchanged_size():
    img = Image.open(io.BytesIO(analyzer.downscale_image(_jpeg(500, 300))))
    assert img.size == (500, 300)


def test_downscale_image_invalid_bytes_passthrough():
    assert analyzer.downscale_image(b"not-an-image") == b"not-an-image"


def test_build_image_message_structure():
    msg = analyzer.build_image_message("描述", "data:image/jpeg;base64,QUJD")
    assert msg[0]["role"] == "user"
    content = msg[0]["content"]
    assert content[0] == {"type": "text", "text": "描述"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


# ---------- VLM JSON 容错解析 ----------

def test_parse_vlm_json_plain():
    out = analyzer.parse_vlm_json('{"image_quality": "足以判断"}')
    assert out == {"image_quality": "足以判断"}


def test_parse_vlm_json_fenced():
    text = '```json\n{"image_quality": "足以判断", "observation": "絮体密实"}\n```'
    assert analyzer.parse_vlm_json(text)["observation"] == "絮体密实"


def test_parse_vlm_json_with_prefix_noise():
    text = '好的，以下是分析结果：\n{"image_quality": "模糊", "observation": null}'
    assert analyzer.parse_vlm_json(text)["image_quality"] == "模糊"


def test_parse_vlm_json_malformed_returns_none():
    assert analyzer.parse_vlm_json("完全不是JSON") is None
    assert analyzer.parse_vlm_json('{"image_quality": "残缺') is None
    assert analyzer.parse_vlm_json("") is None


# ---------- 质量门 ----------

GOOD_RESULT = {"image_quality": "足以判断", "observation": "絮体密实",
               "filament_abundance": "++", "dominant_organisms": ["钟虫类"],
               "floc_structure": "菌胶团密实"}


def test_is_quality_ok_pass():
    assert analyzer.is_quality_ok(GOOD_RESULT) is True


def test_is_quality_gate_blocks_blurry():
    bad = dict(GOOD_RESULT, image_quality="模糊")
    assert analyzer.is_quality_ok(bad) is False


def test_is_quality_gate_blocks_null_fields():
    assert analyzer.is_quality_ok(dict(GOOD_RESULT, observation=None)) is False


def test_is_quality_gate_blocks_missing_field():
    bad = {k: v for k, v in GOOD_RESULT.items() if k != "floc_structure"}
    assert analyzer.is_quality_ok(bad) is False


def test_is_quality_gate_blocks_none():
    assert analyzer.is_quality_ok(None) is False


# ---------- analyze_image（注入 fake VLM） ----------

def test_analyze_image_with_fake_vlm():
    fenced = '```json\n' + str(GOOD_RESULT).replace("'", '"') + '\n```'
    ana = analyzer.analyze_image(_jpeg(400, 300), analyzer.DEFAULT_VLM,
                                 vlm_fn=lambda messages: fenced)
    assert ana["result"]["filament_abundance"] == "++"
    # 消息里确实带了 base64 图片
    assert ana["raw"] == fenced


# ---------- 教程检索排序 ----------

def test_prefer_microscopy_sorts_and_truncates():
    hits = [
        {"text": "a", "source": "data/knowledge/sop/A03.md", "distance": 0.1},
        {"text": "b", "source": "data/knowledge/microscopy/t.md", "distance": 0.2},
        {"text": "c", "source": "data/knowledge/sop/B01.md", "distance": 0.3},
        {"text": "d", "source": "data/knowledge/microscopy/t2.md", "distance": 0.4},
        {"text": "e", "source": "data/knowledge/equipment/x.md", "distance": 0.5},
        {"text": "f", "source": "data/knowledge/sop/C.md", "distance": 0.6},
    ]
    out = analyzer._prefer_microscopy(hits, limit=5)
    assert len(out) == 5
    assert out[0]["source"].startswith("data/knowledge/microscopy")
    assert out[1]["source"].startswith("data/knowledge/microscopy")
    assert len([h for h in out if h["source"].startswith("data/knowledge/microscopy")]) == 2


def test_prefer_microscopy_empty():
    assert analyzer._prefer_microscopy([]) == []


# ---------- 指示生物 ----------

def test_load_species_has_filament_with_ref():
    rules = species.load_species()
    assert len(rules) >= 8
    filament = next(r for r in rules if r["organism"] == "丝状菌")
    assert filament["fault_tree_ref"] == "sludge_bulking"


def test_load_species_missing_file_returns_empty(tmp_path):
    assert species.load_species(tmp_path / "nope.yaml") == []


def test_organism_key_strips_parenthesis():
    assert species.organism_key({"organism": "钟虫（大量、活跃）"}) == "钟虫"
    assert species.organism_key({"organism": "丝状菌"}) == "丝状菌"


def test_match_species_hits_base_name():
    rules = species.load_species()
    hits = species.match_species("观察到大量钟虫类固着型纤毛虫，活跃", rules)
    keys = [h["organism"] for h in hits]
    assert any("钟虫" in k for k in keys)
    assert all(h["meaning"] for h in hits)


def test_match_species_no_hit():
    assert species.match_species("视野干净无明显生物", species.load_species()) == []
    assert species.match_species("", species.load_species()) == []


# ---------- 丝状菌丰度与膨胀触发 ----------

def test_filament_level():
    assert species.filament_level("+") == 1
    assert species.filament_level("++") == 2
    assert species.filament_level("+++") == 3
    assert species.filament_level("++++") == 4
    assert species.filament_level(None) == 0
    assert species.filament_level("乱码") == 0


def test_bulking_trigger_on_filament_3plus():
    result = dict(GOOD_RESULT, filament_abundance="+++")
    trig = species.bulking_trigger(result, [])
    assert trig is not None and trig["tree_id"] == "sludge_bulking"
    assert "污泥膨胀" in trig["prefill"]  # 预填文本需命中故障树 phenomenon 关键词


def test_bulking_trigger_on_ref_match_even_low_level():
    matches = [{"organism": "轮虫", "meaning": "老化", "action": "排泥",
                "fault_tree_ref": "some_tree"}]
    trig = species.bulking_trigger(dict(GOOD_RESULT), matches)
    assert trig is not None and trig["tree_id"] == "some_tree"


def test_bulking_trigger_none_for_normal():
    assert species.bulking_trigger(dict(GOOD_RESULT), []) is None
    assert species.bulking_trigger({"filament_abundance": None}, []) is None


# ---------- explain（注入 fake chat） ----------

def test_explain_builds_prompt_with_refs():
    def fake_chat(messages):
        return messages[-1]["content"]
    out = analyzer.explain("钟虫活跃，丝状菌++",
                           [{"text": "教程片段", "source": "data/knowledge/microscopy/t.md"}],
                           chat_fn=fake_chat)
    assert "【VLM镜检观察】" in out and "钟虫活跃" in out
    assert "教程片段" in out and "t.md" in out


def test_explain_without_refs_notes_missing():
    def fake_chat(messages):
        return messages[-1]["content"]
    assert "暂无命中" in analyzer.explain("观察", [], chat_fn=fake_chat)
