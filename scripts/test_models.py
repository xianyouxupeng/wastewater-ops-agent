"""P3 双通道验证：同一问题分别请求各模型预设端点，全部正常返回即切换机制打通。

用法: python scripts/test_models.py
- 本地预设：需 Ollama 在后台运行
- 在线预设：需在 .env 加 DEEPSEEK_API_KEY=sk-xxx，否则自动跳过
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agent.llm import chat
from app.config import MODEL_PRESETS

QUESTION = "用一句话说明：活性污泥法中SRT过短对硝化有什么影响？"


def main():
    ok, skip, fail = 0, 0, 0
    for name, preset in MODEL_PRESETS.items():
        print(f"\n===== {name} ｜ model={preset['model']} ｜ {preset['base_url']} =====")
        if not preset.get("api_key"):
            print("⏭ 跳过：未配置该预设的 API key（在 .env 加 DEEPSEEK_API_KEY=sk-xxx 后重跑）")
            skip += 1
            continue
        t0 = time.time()
        try:
            answer = chat(
                [{"role": "user", "content": QUESTION}],
                model=preset["model"],
                base_url=preset["base_url"],
                api_key=preset["api_key"],
            )
            print(f"✓ {time.time() - t0:.1f}s  回答：{answer[:80]}")
            ok += 1
        except Exception as e:
            print(f"✗ 失败：{type(e).__name__}: {e}")
            fail += 1

    print(f"\n===== 结果：成功 {ok} ｜ 跳过 {skip} ｜ 失败 {fail} =====")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
