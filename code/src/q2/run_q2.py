"""Q2 求解入口。"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "code" / "results"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="跳过重计算（如 ILP 完整求解）")
    args = parser.parse_args()

    (RESULTS / "tables").mkdir(parents=True, exist_ok=True)
    (RESULTS / "figures").mkdir(parents=True, exist_ok=True)

    # TODO: 实现 Q2 求解
    print(f"[Q2] TODO: implement  quick={args.quick}")


if __name__ == "__main__":
    main()
