"""V2.3 诊断 Agent 循环测试（全纯函数/注入，不依赖 LLM 与向量库）

文档要求必测：工具调用解析、循环轮数控制、降级路径。
"""
import json
from types import SimpleNamespace

from app.diagnostic import agent
from app.diagnostic.agent import (AgentSession, MODE_LABELS, detect_mode,
                                  parse_action_json)
from app.diagnostic.tools import EXECUTABLE, TOOL_NAMES, TOOL_SCHEMAS, run_tool


# ---------- 模型能力检测与降级（V2.2/V2.3 必测：7B → V1 模式） ----------

def test_detect_mode_small_local_model_degrades():
    assert detect_mode("qwen2.5:7b") == "off"
    assert detect_mode("llama3:8b") == "off"
    assert detect_mode("qwen2.5:3b") == "off"


def test_detect_mode_capable_models_native():
    assert detect_mode("qwen2.5:14b") == "native"
    assert detect_mode("qwen2.5:32b") == "native"
    assert detect_mode("deepseek-chat") == "native"
    assert detect_mode("gpt-4o-mini") == "native"
    assert detect_mode("llama-3.3-70b-versatile") == "native"  # 参数量≥14B


def test_detect_mode_unknown_model_text_fallback():
    assert detect_mode("some-new-model-v2") == "text"
    assert detect_mode("") == "text"
    assert detect_mode(None) == "text"


def test_detect_mode_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "off")
    assert detect_mode("deepseek-chat") == "off"  # 强制降级优先于模型名判定
    monkeypatch.setenv("AGENT_MODE", "native")
    assert detect_mode("qwen2.5:7b") == "native"


# ---------- 工具箱 ----------

def test_tool_schemas_valid():
    assert TOOL_NAMES == {"query_runtime", "search_knowledge",
                          "search_cases", "ask_user"}
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert len(names) == len(set(names))
    for t in TOOL_SCHEMAS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]
    assert "ask_user" not in EXECUTABLE  # ask_user 由循环拦截，不在服务端执行


def test_run_tool_dispatch_and_injection():
    calls = []
    result = run_tool("search_cases", {"query": "氨氮高"},
                      cases_fn=lambda q: (calls.append(q), "- 案例1")[-1])
    assert result == "- 案例1" and calls == ["氨氮高"]
    assert "未知工具" in run_tool("nope", {})
    assert "执行失败" in run_tool("search_knowledge", {"query": "x"},
                                  knowledge_fn=lambda q: 1 / 0)  # 失败不抛异常


def test_run_tool_query_runtime_filters_params(tmp_path, monkeypatch):
    from app.memory import runtime
    f = tmp_path / "ledger.jsonl"
    runtime.append_entry({"date": "2026-10-12", "outlet_nh3n": "6.2", "do": "3.2"},
                         path=f)
    monkeypatch.setattr(runtime, "get_recent_params",
                        lambda days=7, path=runtime.LEDGER_FILE, today=None:
                        runtime.load_entries(f))
    import app.diagnostic.tools as tools
    monkeypatch.setattr(tools.runtime_mem, "get_recent_params",
                        lambda days=7, path=runtime.LEDGER_FILE, today=None:
                        runtime.load_entries(f))
    out = run_tool("query_runtime", {"params": ["氨氮"], "days": 7})
    assert "出水氨氮=6.2" in out
    assert "DO" not in out  # 只查了氨氮，不掺别的参数


# ---------- text 模式动作解析 ----------

def test_parse_action_json_plain_and_fenced():
    raw = json.dumps({"action": "tool_call", "tool": "search_knowledge",
                      "args": {"query": "硝化"}})
    parsed = parse_action_json(f"```json\n{raw}\n```")
    assert parsed == {"action": "tool_call", "name": "search_knowledge",
                      "args": {"query": "硝化"}}


def test_parse_action_json_ask_variants():
    assert parse_action_json('{"action": "ask_user", "args": {"question": "COD高吗"}}') \
        == {"action": "ask", "question": "COD高吗"}
    assert parse_action_json('{"action": "tool_call", "tool": "ask_user",'
                             ' "args": {"question": "镜检做了吗"}}') \
        == {"action": "ask", "question": "镜检做了吗"}


def test_parse_action_json_garbage_degrades_to_conclude():
    parsed = parse_action_json("我觉得是进水冲击，建议核对上游排放。")
    assert parsed["action"] == "conclude"
    assert "进水冲击" in parsed["report"]  # 原文当报告，不丢内容
    assert parse_action_json('{"action": "tool_call", "tool": "bad_tool"}')["action"] \
        == "conclude"  # 协议外的工具名也退化为结论


# ---------- native 循环（fake message 对象） ----------

def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def _tc(id, name, args):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name,
                                                           arguments=json.dumps(args)))


def test_native_ask_then_conclude():
    """目标形态示例：LLM 先 ask_user，用户答完出结论"""
    replies = [_msg(tool_calls=[_tc("t1", "ask_user", {"question": "出水COD同步升高吗？"})]),
               _msg(content="## 结论（高置信度）\n进水负荷冲击")]
    sess = AgentSession("出水氨氮有点高", lambda m, tools=None: replies.pop(0),
                        mode="native", context="【本厂档案】…", tool_runner=run_tool)
    ev = sess.step()
    assert ev["type"] == "ask" and ev["question"] == "出水COD同步升高吗？"
    ev = sess.step("正常")
    assert ev["type"] == "conclude" and "负荷冲击" in ev["report"]
    # 用户回答以 tool 结果身份回填 tool_call_id
    tool_msgs = [m for m in sess.messages if m["role"] == "tool"]
    assert tool_msgs[-1]["tool_call_id"] == "t1" and tool_msgs[-1]["content"] == "正常"


def test_native_tool_execution_injects_result():
    replies = [_msg(tool_calls=[_tc("t1", "search_cases", {"query": "氨氮"})]),
               _msg(content="结论")]
    sess = AgentSession("氨氮高", lambda m, tools=None: replies.pop(0), mode="native",
                        tool_runner=lambda name, args: f"案例C001内容({name})")
    ev = sess.step()
    assert ev["type"] == "tool" and "案例C001" in ev["result"]
    assert sess.tools_used == ["search_cases"]
    # 工具结果已作为 tool 消息注入上下文
    assert any(m["role"] == "tool" and "案例C001" in m["content"]
               for m in sess.messages)
    ev = sess.step()  # 工具轮后 UI 续跑
    assert ev["type"] == "conclude"


def test_native_max_rounds_force_conclude():
    """轮数上限：LLM 一直要调工具 → 到顶后强制无工具收敛（best effort）"""
    def always_tool(m, tools=None):
        if tools is None:  # 强制收敛轮：不带工具
            return _msg(content="基于现有信息的最终结论")
        return _msg(tool_calls=[_tc("t", "query_runtime", {})])

    sess = AgentSession("氨氮高", always_tool, mode="native",
                        max_rounds=2, tool_runner=lambda n, a: "数据")
    ev = sess.step()
    while ev["type"] == "tool":
        ev = sess.step()
    assert ev["type"] == "conclude"
    assert "最终结论" in ev["report"]


def test_question_cap_stops_endless_asking():
    """LLM 问个不停 → 超过 max_questions 后强制收敛，不再问"""
    calls = {"n": 0}

    def always_ask(m, tools=None):
        calls["n"] += 1
        if tools is None:
            return _msg(content="强制结论")
        return _msg(tool_calls=[_tc("t", "ask_user", {"question": "还有吗？"})])

    sess = AgentSession("氨氮高", always_ask, mode="native",
                        max_rounds=4, max_questions=1,
                        tool_runner=lambda n, a: "")
    ev = sess.step()
    assert ev["type"] == "ask"
    ev = sess.step("不知道")
    while ev["type"] == "ask":  # 若再问就继续答，最终必须 conclude
        ev = sess.step("不知道")
    assert ev["type"] == "conclude"


# ---------- text 模式循环 ----------

def test_text_mode_full_flow():
    """7B 降级链路（AGENT_MODE=text）：JSON 动作协议走通 ask → answer → conclude"""
    replies = ['{"action": "tool_call", "tool": "ask_user", "args": {"question": "COD如何？"}}',
               '{"action": "conclude", "report": "结论：负荷冲击"}']
    sess = AgentSession("氨氮高", lambda m, tools=None: replies.pop(0), mode="text")
    ev = sess.step()
    assert ev["type"] == "ask"
    ev = sess.step("COD 正常")
    assert ev["type"] == "conclude" and "负荷冲击" in ev["report"]
    # 用户回答以 user 消息进入上下文
    assert any(m["role"] == "user" and "COD 正常" in m["content"]
               for m in sess.messages)


def test_text_mode_tool_result_injected_as_user():
    replies = ['{"action": "tool_call", "tool": "query_runtime", "args": {"days": 7}}',
               '{"action": "conclude", "report": "结论"}']
    sess = AgentSession("氨氮高", lambda m, tools=None: replies.pop(0), mode="text",
                        tool_runner=lambda n, a: "台账数据XYZ")
    ev = sess.step()
    assert ev["type"] == "tool" and "台账数据XYZ" in ev["result"]
    assert any(m["role"] == "user" and "【工具 query_runtime 结果】" in m["content"]
               for m in sess.messages)


# ---------- 会话上下文 ----------

def test_session_includes_context_and_history():
    from app.memory.session import history_text
    hist = [{"role": "user", "content": "昨天也偏高"}]
    sess = AgentSession("氨氮高", lambda m, tools=None: _msg(content="结论"),
                        mode="native", context="【本厂档案】测试",
                        history=hist)
    first_user = sess.messages[1]["content"]
    assert "【本厂档案】测试" in first_user
    assert "昨天也偏高" in first_user  # 历史文本块已注入


def test_mode_labels_complete():
    assert set(MODE_LABELS) == {"native", "text", "off"}


# ---------- 中间轮思考外显 ----------

def test_native_tool_event_carries_thought():
    """content 与 tool_calls 并存时，判断理由随事件外显（进轨迹展示给值班员）"""
    replies = [_msg(content="氨氮涨幅38%，首选负荷冲击，先查相似案例",
                    tool_calls=[_tc("t1", "search_cases", {"query": "氨氮"})]),
               _msg(content="结论")]
    sess = AgentSession("氨氮高", lambda m, tools=None: replies.pop(0), mode="native",
                        tool_runner=lambda n, a: "案例C001")
    ev = sess.step()
    assert ev["type"] == "tool"
    assert "负荷冲击" in ev["thought"]


def test_native_ask_event_carries_thought():
    replies = [_msg(content="还需排除毒性冲击",
                    tool_calls=[_tc("t1", "ask_user", {"question": "COD同步升高吗？"})]),
               _msg(content="结论")]
    sess = AgentSession("氨氮高", lambda m, tools=None: replies.pop(0), mode="native")
    ev = sess.step()
    assert ev["type"] == "ask" and "毒性" in ev["thought"]


def test_text_mode_thought_empty():
    """text 模式协议只有 JSON，没有可外显的思考，事件 thought 为空串"""
    replies = ['{"action": "tool_call", "tool": "query_runtime", "args": {}}',
               '{"action": "conclude", "report": "结论"}']
    sess = AgentSession("氨氮高", lambda m, tools=None: replies.pop(0), mode="text",
                        tool_runner=lambda n, a: "数据")
    ev = sess.step()
    assert ev["thought"] == ""


def test_native_thought_without_content_is_empty():
    replies = [_msg(tool_calls=[_tc("t1", "query_runtime", {})]),
               _msg(content="结论")]
    sess = AgentSession("氨氮高", lambda m, tools=None: replies.pop(0), mode="native",
                        tool_runner=lambda n, a: "数据")
    ev = sess.step()
    assert ev["thought"] == ""  # 模型没写判断时不显示空行
