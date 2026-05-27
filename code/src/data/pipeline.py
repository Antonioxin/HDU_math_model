"""数据预处理流水线。

读取 problem/ 下附件表，输出清洗 / 派生表到 code/data/processed/。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "problem"
PROCESSED = ROOT / "code" / "data" / "processed"


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    print(f"[pipeline] raw={RAW}  processed={PROCESSED}")
    # TODO: 读取附件、清洗、缺失值处理、特征生成
    # 例：
    # import pandas as pd
    # df = pd.read_excel(RAW / "附件表1.xlsx")
    # df.to_csv(PROCESSED / "table1_clean.csv", index=False)


if __name__ == "__main__":
    main()
