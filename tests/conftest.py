import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (main.py, stt/, llm/ 등 import 가능하도록)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
