"""Q3 求解入口。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "code" / "results"


def main() -> None:
    (RESULTS / "tables").mkdir(parents=True, exist_ok=True)
    (RESULTS / "figures").mkdir(parents=True, exist_ok=True)
    # TODO: 实现 Q3 双层 / 联合优化
    print("[Q3] TODO: implement")


if __name__ == "__main__":
    main()
