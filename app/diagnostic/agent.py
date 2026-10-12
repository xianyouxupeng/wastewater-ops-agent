"""诊断 Agent 循环（V2.3）：观察 → 判断 → 提问/查证 → 收敛。

三种模式（detect_mode 按模型名自动判定，.env 设 AGENT_MODE=native/text/off 可强制覆盖）：
- native：OpenAI function calling（tools 参数），API 层保证结构化输出，优先
- text：  模型每轮输出一个 JSON 动作，代码解析兜底（端点不支持 tools 时）
- off：   小参数本地模型（<14B，V1 实证多轮指令不稳），不进循环，页面降级 V1 一次性诊断

循环可恢复式设计：step() 每次推进一轮并返回事件（tool/ask/conclude），
UI 驱动——工具轮自动续跑，ask 轮停下渲染问题卡等用户回答。
"""
import json
import os
import re

from app.agent.prompts import AGENT_SYSTEM, TEXT_ACTION_SUFFIX
from app.diagnostic.tools import EXECUTABLE, TOOL_SCHEMAS, run_tool

MAX_ROUNDS = 5      # LLM 轮数上限（工具轮+提问轮合计），到顶强制收敛
MAX_QUESTIONS = 3   # 整个诊断最多向用户提问次数，防问个不停
MODE_ENV = "AGENT_MODE"

MODE_LABELS = {
    "native": "工具调用（function calling）",
    "text": "文本解析（JSON 动作协议）",
    "off": "不支持多轮循环，使用 V1 一次性诊断",
}

# 模型名含这些关键字 → 认定支持 function calling（主流在线/新本地模型）
_KNOWN_NATIVE = ("deepseek", "gpt-4", "gpt-5", "o3", "o4", "claude", "gemini",
                 "glm-4", "glm-5", "qwen3", "qwen-plus", "qwen-max", "qwen-turbo",
                 "moonshot", "kimi", "doubao", "abab", "hunyuan", "ernie",
                 "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b")


def detect_mode(model: str | None, override: str | None = None) -> str:
    """判定 agent 模式：native / text / off。

    判定顺序：显式覆盖（参数或 AGENT_MODE 环境变量）→ 模型名参数量
    （<14B 的本地量化模型 off）→ 已知支持工具调用的关键字 → 未知模型保守走 text。
    """
    override = (override or os.getenv(MODE_ENV, "auto") or "auto").lower()
    if override in ("native", "text", "off"):
        return override
    name = (model or "").lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", name)
    if m:
        return "native" if float(m.group(1)) >= 14 else \
            "off"  # 7B 级多轮结构化输出不可靠（V1 实证），降级
    if any(k in name for k in _KNOWN_NATIVE):
        return "native"
    return "text"


def parse_action_json(raw: str) -> dict:
    """text 模式动作解析：容忍 ```json 围栏与前后杂文字；
    解析失败/协议不符时整体视为 conclude（原文当报告），不中断诊断。"""
    text = (raw or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            data = json.loads(m.group())
            action = data.get("action")
            if action == "ask_user" or (action == "tool_call"
                                        and data.get("tool") == "ask_user"):
                args = data.get("args") or {}
                question = (args.get("question") if isinstance(args, dict) else None) \
                    or data.get("question") or ""
                return {"action": "ask", "question": str(question)}
            if action == "tool_call" and data.get("tool") in EXECUTABLE:
                args = data.get("args") or {}
                return {"action": "tool_call", "name": data["tool"],
                        "args": args if isinstance(args, dict) else {}}
            if action == "conclude":
                return {"action": "conclude", "report": str(data.get("report") or "")}
        except (json.JSONDecodeError, TypeError):
            pass
    return {"action": "conclude", "report": text}


def build_agent_context(user_input: str) -> str:
    """拼装初始观察上下文：命中故障树 + 厂情档案 + 台账摘要 + 相似案例。
    各部分失败静默跳过（复用 engine 的兜底策略）。"""
    import yaml

    from app.diagnostic.engine import (_case_block, _safe, _similar_cases,
                                       load_fault_trees, match_trees)
    from app.memory.plant import plant_profile_block
    from app.memory.runtime import runtime_block

    parts = []
    matched = match_trees(user_input, load_fault_trees())
    if matched:
        tree_text = yaml.dump(matched, allow_unicode=True, sort_keys=False)
        parts.append("【命中的故障树条目（提问须以其中 distinguishing_tests 为依据）】\n"
                     + tree_text)
    plant = _safe(plant_profile_block)
    runtime = _safe(runtime_block)
    if plant:
        parts.append(plant)
    if runtime:
        parts.append(runtime)
    case_block = _case_block(_similar_cases(user_input))
    if case_block:
        parts.append(case_block)
    return "\n\n".join(parts)


class AgentSession:
    """一次诊断会话。UI 持有实例，step() 推进；答案经 step(answer) 传回。

    llm_fn 契约：fn(messages, tools=None) → 带 .content 与 .tool_calls 的消息对象
    （native），或返回 str（text 模式）。tool_runner 可注入替换（测试）。
    """

    def __init__(self, user_input: str, llm_fn, mode: str = "native", *,
                 context: str = "", history: list[dict] | None = None,
                 max_rounds: int = MAX_ROUNDS, max_questions: int = MAX_QUESTIONS,
                 tool_runner=run_tool):
        if mode not in MODE_LABELS:
            raise ValueError(f"未知 agent 模式：{mode}")
        self.mode = mode
        self.llm_fn = llm_fn
        self.tool_runner = tool_runner
        self.max_rounds = max_rounds
        self.max_questions = max_questions
        self.rounds = 0        # 已用 LLM 轮数（不含强制收敛那轮）
        self.questions = 0
        self.tools_used: list[str] = []
        self._pending_tool_call = None  # ask_user 拦截后待回填的 tool_call
        system = AGENT_SYSTEM + (TEXT_ACTION_SUFFIX if mode == "text" else "")
        self.messages: list[dict] = [{"role": "system", "content": system}]
        first = user_input
        if history:
            from app.memory.session import history_text
            hist = history_text(history)
            if hist:
                first = f"{first}\n\n{hist}"
        if context:
            first = f"{first}\n\n{context}"
        self.messages.append({"role": "user", "content": first})

    # ---------- 对外主入口 ----------

    def step(self, user_answer: str | None = None) -> dict:
        """推进一轮，返回事件：
        {"type": "tool", "name", "args", "result"}   工具已执行并注入上下文，应继续 step
        {"type": "ask", "question"}                  等用户回答，答案经 step(answer) 传回
        {"type": "conclude", "report"}               诊断结束（含到达轮数上限的强制收敛）
        """
        if user_answer is not None:
            self._append_answer(user_answer)
        while True:
            if self.rounds >= self.max_rounds:
                return self._force_conclude()
            self.rounds += 1
            reply, parsed = self._round()
            action = parsed["action"]

            if action == "conclude":
                return {"type": "conclude", "report": parsed["report"]}

            if action == "ask" or (action == "tool_call" and parsed["name"] == "ask_user"):
                if self.questions >= self.max_questions:
                    self.messages.append({"role": "user", "content":
                                          "提问次数已达上限，请立即基于现有信息给出最终结论。"})
                    continue
                self.questions += 1
                self._record_assistant(reply)
                question = parsed.get("question") or (parsed.get("args") or {}).get("question", "")
                if action == "tool_call":  # native：ask_user 以 tool_call 形式下发
                    self._pending_tool_call = _find_tc(reply, "ask_user")
                return {"type": "ask", "question": str(question),
                        "thought": _thought_of(reply)}

            # 可执行工具
            name, args = parsed["name"], parsed.get("args") or {}
            result = self.tool_runner(name, args)
            self.tools_used.append(name)
            self._record_tool_round(reply, name, result)
            return {"type": "tool", "name": name, "args": args,
                    "result": _brief(result), "thought": _thought_of(reply)}

    # ---------- 内部 ----------

    def _round(self):
        """调一次 LLM 并归一化为 (原始回复, 动作 dict)"""
        if self.mode == "native":
            reply = self.llm_fn(self.messages, tools=TOOL_SCHEMAS)
            tcs = getattr(reply, "tool_calls", None) or []
            if tcs:
                tc = tcs[0]  # MVP：一次取第一个动作（ask_user 优先见下）
                for t in tcs:  # 模型若同时给多个，优先响应 ask_user
                    if t.function.name == "ask_user":
                        tc = t
                        break
                return reply, {"action": "tool_call",
                               "name": tc.function.name,
                               "args": _safe_json(tc.function.arguments)}
            return reply, {"action": "conclude",
                           "report": getattr(reply, "content", None) or ""}
        # text 模式
        reply = self.llm_fn(self.messages, tools=None)
        raw = reply if isinstance(reply, str) else \
            (getattr(reply, "content", None) or "")
        return raw, parse_action_json(raw)

    def _record_assistant(self, reply):
        """把助手轮写回历史（native 转 dict 保证可再序列化）"""
        if isinstance(reply, str):
            self.messages.append({"role": "assistant", "content": reply})
            return
        entry = {"role": "assistant", "content": getattr(reply, "content", None) or ""}
        tcs = getattr(reply, "tool_calls", None) or []
        if tcs:
            entry["tool_calls"] = [
                {"id": t.id, "type": "function",
                 "function": {"name": t.function.name,
                              "arguments": t.function.arguments}}
                for t in tcs]
        self.messages.append(entry)

    def _record_tool_round(self, reply, name: str, result: str):
        self._record_assistant(reply)
        if self.mode == "native":
            tc = _find_tc(reply, name)
            self.messages.append({"role": "tool", "tool_call_id": tc.id
                                  if tc else name, "content": result})
        else:
            self.messages.append({"role": "user",
                                  "content": f"【工具 {name} 结果】\n{result}"})

    def _append_answer(self, answer: str):
        if self.mode == "native" and self._pending_tool_call is not None:
            self.messages.append({
                "role": "tool", "tool_call_id": self._pending_tool_call.id,
                "content": answer})
            self._pending_tool_call = None
        else:
            self.messages.append({"role": "user", "content": f"用户回答：{answer}"})

    def _force_conclude(self) -> dict:
        """达到轮数上限：不带 tools 再要一次结论（best effort，模型无法再调工具）"""
        self.messages.append({"role": "user", "content":
                              "已达最大诊断轮数。请立即基于已掌握的信息输出最终结论"
                              + ("，只输出 {\"action\": \"conclude\", \"report\": ...}"
                                 if self.mode == "text" else "。")})
        reply = self.llm_fn(self.messages, tools=None)
        text = _text_of(reply)
        if self.mode == "text":
            parsed = parse_action_json(text)
            text = parsed.get("report") if parsed["action"] == "conclude" else text
        return {"type": "conclude", "report": text}


def _find_tc(reply, name: str):
    """在回复的 tool_calls 里按工具名找（模型可能一轮下发多个调用）"""
    for t in getattr(reply, "tool_calls", None) or []:
        if t.function.name == name:
            return t
    return None


def _safe_json(args) -> dict:
    """模型给的 arguments 可能是空串/坏 JSON，兜底空 dict"""
    if isinstance(args, dict):
        return args
    try:
        data = json.loads(args or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _thought_of(reply) -> str:
    """中间轮的外显思考：native 模式 content 与 tool_calls 可并存，
    prompt 已要求模型调工具前写一句判断；text 模式协议只有 JSON，无思考可取"""
    if isinstance(reply, str):
        return ""
    return (getattr(reply, "content", None) or "").strip()


def _text_of(reply) -> str:
    return reply if isinstance(reply, str) else (getattr(reply, "content", None) or "")


def _brief(text: str, limit: int = 120) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"
