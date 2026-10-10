"""知识问答链路测试（不依赖 LLM/网络）

文档要求必测：知识问答无结果时正确拒答。
覆盖：空库拒答、操作提醒的代码规则、prompt 构造。
"""
import pytest

import app.rag.qa as qa


def _fake_retrieve(hits):
    return lambda query, k=5: hits


# ---------- 必测项：无结果时正确拒答 ----------

def test_ask_rejects_when_no_hits(monkeypatch):
    monkeypatch.setattr(qa, "retrieve", _fake_retrieve([]))

    def _explode(messages):  # 拒答时不应调用 LLM
        raise AssertionError("无检索结果时不应调用语言模型")

    answer = qa.ask("随便问", chat_fn=_explode)
    assert answer == qa.NO_RESULT_REPLY
    assert "暂无相关内容" in answer
    assert "更新知识库" in answer  # 拒答里附引导


# ---------- 操作提醒：代码关键词规则（LLM 判断不稳定，改为代码判断） ----------

HITS = [{"text": "片段", "source": "data/knowledge/sop/a.md", "distance": 0.3}]


def test_ask_appends_reminder_for_dosing_question(monkeypatch):
    monkeypatch.setattr(qa, "retrieve", _fake_retrieve(HITS))
    answer = qa.ask("PAC投加量一般是多少", chat_fn=lambda m: "PAC 按铝磷摩尔比投加。")
    assert "工艺工程师或值班长确认" in answer


def test_ask_appends_reminder_from_answer_keywords(monkeypatch):
    monkeypatch.setattr(qa, "retrieve", _fake_retrieve(HITS))
    answer = qa.ask("排泥是怎么回事", chat_fn=lambda m: "建议每日排泥 200 m³。")
    assert "工艺工程师或值班长确认" in answer  # 回答含"排泥 200"→ 含"排泥量"？改由"排泥"…见关键词表


def test_ask_no_reminder_for_knowledge_question(monkeypatch):
    monkeypatch.setattr(qa, "retrieve", _fake_retrieve(HITS))
    answer = qa.ask("什么是钟虫", chat_fn=lambda m: "钟虫是缘毛目原生动物。")
    assert "工艺工程师" not in answer


def test_needs_op_reminder_keywords():
    assert qa._needs_op_reminder("投加量多少")
    assert qa._needs_op_reminder("鼓风机怎么启停")
    assert qa._needs_op_reminder("回流比控制在多少")
    assert not qa._needs_op_reminder("什么是钟虫")
    assert not qa._needs_op_reminder("芬顿氧化的原理")


# ---------- prompt 构造 ----------

def test_build_messages_contains_sources_and_question():
    msgs = qa.build_messages(
        "钟虫尺寸", [{"text": "钟虫100微米", "source": "a.md"}])
    assert msgs[0]["role"] == "system"
    user = msgs[1]["content"]
    assert "[1] 来源: a.md" in user and "钟虫100微米" in user
    assert "【问题】\n钟虫尺寸" in user
