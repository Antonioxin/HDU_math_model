"""Q1 求解入口。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "code" / "results"


def main() -> None:
    (RESULTS / "tables").mkdir(parents=True, exist_ok=True)
    (RESULTS / "figures").mkdir(parents=True, exist_ok=True)
    # TODO: 实现 Q1 求解；将结果写入 results/tables/，图表写入 results/figures/
    print("[Q1] TODO: implement")


if __name__ == "__main__":
    main()
