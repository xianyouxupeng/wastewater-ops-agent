"""知识库问答。用法: python scripts/ask_cli.py "PAC的投加量范围是多少？" """
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.rag.qa import ask


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    print(ask(question))


if __name__ == "__main__":
    main()
