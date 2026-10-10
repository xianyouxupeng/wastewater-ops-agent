"""用法: python scripts/diagnose_cli.py "出水氨氮超标，DO只有1.8" """
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Windows GBK 控制台打不出 ⚠️ 等字符，统一按 UTF-8 输出
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.diagnostic.engine import diagnose


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    user_input = " ".join(sys.argv[1:])
    print(diagnose(user_input))


if __name__ == "__main__":
    main()
