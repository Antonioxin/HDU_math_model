"""统一的数据读取入口。

提供函数式接口，所有后续模块均从此模块获取附件数据，避免散落在各处的硬路径。
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "problem" / "数据"
PROCESSED = ROOT / "code" / "data" / "processed"
XJTU_RAW = ROOT / "problem" / "数据" / "XJTU-SY" / "XJTU-SY_Bearing_Datasets"
# 三个工况子目录
_XJTU_CONDITIONS = ["35Hz12kN", "37.5Hz11kN", "40Hz10kN"]


def _find_bearing_dir(bearing_name: str) -> Path:
    """在三个工况子目录中查找轴承文件夹。"""
    for cond in _XJTU_CONDITIONS:
        d = XJTU_RAW / cond / bearing_name
        if d.exists():
            return d
    raise FileNotFoundError(
        f"找不到轴承目录: {bearing_name}\n"
        f"已搜索: {[str(XJTU_RAW / c / bearing_name) for c in _XJTU_CONDITIONS]}"
    )


def _resolve(path: Path) -> Path:
    """若路径不存在，尝试 .csv 和 .xlsx 后缀。"""
    if path.exists():
        return path
    for ext in [".csv", ".xlsx", ".xls"]:
        alt = path.with_suffix(ext)
        if alt.exists():
            return alt
    raise FileNotFoundError(f"找不到数据文件: {path} (也尝试了 .csv/.xlsx)")


def load_raw(name: str, **kwargs) -> pd.DataFrame:
    """从 problem/数据/ 读取原始附件表。"""
    path = _resolve(RAW / name)
    if path.suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, **kwargs)
    return pd.read_csv(path, **kwargs)


def load_processed(name: str, **kwargs) -> pd.DataFrame:
    """从 code/data/processed/ 读取预处理后的表。"""
    path = _resolve(PROCESSED / name)
    if path.suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, **kwargs)
    return pd.read_csv(path, **kwargs)


# ── 便捷函数 ────────────────────────────────────────────────────────────

def load_att1() -> pd.DataFrame:
    """加载附件1：仿真全寿命 3500 天数据。

    Columns: day, current, current_theoretical, temperature, speed_rpm, friction_torque
    """
    return load_raw("附件1 reaction_wheel_3500d_data")


def load_att2() -> pd.DataFrame:
    """加载附件2：在轨监测 1800 天数据。

    Columns: day, current, current_theoretical, temperature, speed_rpm
    """
    return load_raw("附件2 reaction_wheel_1800d_data")


def load_xjtu_bearing(bearing_name: str, file_index: int) -> pd.DataFrame:
    """加载 XJTU-SY 单个振动文件。

    Parameters
    ----------
    bearing_name : str
        如 "Bearing1_1"
    file_index : int
        文件序号 (从 1 开始)

    Returns
    -------
    pd.DataFrame with columns: [Horizontal, Vertical]
    """
    bearing_dir = _find_bearing_dir(bearing_name)
    path = bearing_dir / f"{file_index}.csv"
    if not path.exists():
        raise FileNotFoundError(f"振动文件不存在: {path}")
    return pd.read_csv(path, names=["Horizontal", "Vertical"], skiprows=1)


def list_xjtu_bearing_files(bearing_name: str) -> list[int]:
    """列出某轴承的全部振动文件序号（排序后）。"""
    bearing_dir = _find_bearing_dir(bearing_name)
    files = sorted(
        int(f.stem) for f in bearing_dir.glob("*.csv") if f.stem.isdigit()
    )
    return files


def save_processed(df: pd.DataFrame, name: str) -> None:
    """保存预处理结果到 code/data/processed/。"""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    path = PROCESSED / name
    if path.suffix == ".xlsx":
        df.to_excel(path, index=False)
    else:
        df.to_csv(path, index=False)
    print(f"[load_tables] 已保存: {path}")


def save_result_table(df: pd.DataFrame, name: str) -> Path:
    """保存结果表到 code/results/tables/。"""
    out_dir = ROOT / "code" / "results" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    if path.suffix == ".xlsx":
        df.to_excel(path, index=False)
    else:
        df.to_csv(path, index=False)
    print(f"[load_tables] 结果已保存: {path}")
    return path

