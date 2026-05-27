"""统一的数据读取入口。

提供函数式接口，所有后续模块均从此模块获取附件数据，避免散落在各处的硬路径。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "problem"
PROCESSED = ROOT / "code" / "data" / "processed"


def load_table(name: str, *, processed: bool = False, **kwargs) -> pd.DataFrame:
    base = PROCESSED if processed else RAW
    path = base / name
    if path.suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, **kwargs)
    return pd.read_csv(path, **kwargs)
