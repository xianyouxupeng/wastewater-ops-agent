"""增量入库知识库。用法: python scripts/ingest.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.rag.ingest import main

if __name__ == "__main__":
    main()
