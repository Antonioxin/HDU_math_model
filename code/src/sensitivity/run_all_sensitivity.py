"""敏感性分析批量入口。

按 model/敏感性分析设计.md 中的扫描点逐项运行，结果写入 code/results/tables/敏感性分析.csv。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "code" / "results" / "tables"


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    # TODO: 实现敏感性扫描；按 model/敏感性分析设计.md 的设定遍历参数
    print("[sensitivity] TODO: implement")


if __name__ == "__main__":
    main()
