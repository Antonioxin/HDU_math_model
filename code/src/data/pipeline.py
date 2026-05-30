"""数据预处理流水线。

读取 problem/ 下附件表，输出清洗 / 派生表到 code/data/processed/。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "problem" / "数据"
PROCESSED = ROOT / "code" / "data" / "processed"

# 导入常量
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.constants import I_0, I_F, DELTA_I_F, THETA_H, THETA_F


def load_att1_raw() -> pd.DataFrame:
    """加载附件1 原始数据。"""
    path = RAW / "附件1 reaction_wheel_3500d_data.csv"
    df = pd.read_csv(path)
    return df


def load_att2_raw() -> pd.DataFrame:
    """加载附件2 原始数据。"""
    path = RAW / "附件2 reaction_wheel_1800d_data.csv"
    df = pd.read_csv(path)
    return df


def preprocess_att1(df: pd.DataFrame) -> pd.DataFrame:
    """附件1 预处理：计算派生列。

    新增列:
      - delta_i: 残差电流 = current - current_theoretical
      - delta_i_cum: 累积退化量 = current - I_0
      - phi: 标准化退化进度 = delta_i_cum / DELTA_I_F
      - X: 对数化退化变量 = ln(current - I_0 + EPS)
      - stage: 阶段标签 H/D/F
    """
    df = df.copy()

    # 残差电流（退化信号）
    df["delta_i"] = df["current"] - df["current_theoretical"]

    # 累积退化量
    df["delta_i_cum"] = df["current"] - I_0

    # 标准化退化进度
    df["phi"] = df["delta_i_cum"] / DELTA_I_F

    # 对数化退化变量 (已弃用对数变换, 保留兼容)
    df["X"] = np.log(np.maximum(df["current"] - I_0, 1e-6) + 1e-6)

    # 阶段标签
    df["stage"] = df["phi"].apply(_classify_stage)

    return df


def preprocess_att2(df: pd.DataFrame) -> pd.DataFrame:
    """附件2 预处理：同附件1，但不含 friction_torque。"""
    df = df.copy()

    df["delta_i"] = df["current"] - df["current_theoretical"]
    df["delta_i_cum"] = df["current"] - I_0
    df["phi"] = df["delta_i_cum"] / DELTA_I_F
    df["X"] = np.log(np.maximum(df["current"] - I_0, 1e-6) + 1e-6)
    df["stage"] = df["phi"].apply(_classify_stage)

    return df


def _classify_stage(phi: float) -> str:
    """按标准化退化进度分类阶段。"""
    if phi < THETA_H:
        return "H"
    elif phi < THETA_F:
        return "D"
    else:
        return "F"


def compute_summary_stats(df: pd.DataFrame, label: str) -> dict:
    """计算数据摘要统计。"""
    return {
        "label": label,
        "n_rows": len(df),
        "t_min": df["day"].min(),
        "t_max": df["day"].max(),
        "i_min": df["current"].min(),
        "i_max": df["current"].max(),
        "i_mean": df["current"].mean(),
        "i_std": df["current"].std(),
        "delta_i_max": df["delta_i"].max(),
        "delta_i_min": df["delta_i"].min(),
        "stage_counts": df["stage"].value_counts().to_dict(),
    }


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    print(f"[pipeline] raw={RAW}  processed={PROCESSED}")

    # ── 附件1 ──
    print("\n[1/4] 加载附件1...")
    att1 = load_att1_raw()
    print(f"  原始: {att1.shape}, columns={list(att1.columns)}")

    print("[2/4] 预处理附件1...")
    att1_proc = preprocess_att1(att1)
    att1_proc.to_csv(PROCESSED / "att1_processed.csv", index=False)
    print(f"  已保存 att1_processed.csv ({len(att1_proc)} 行)")

    stats1 = compute_summary_stats(att1_proc, "附件1")
    print(f"  摘要: t=[{stats1['t_min']}, {stats1['t_max']}], "
          f"i=[{stats1['i_min']:.4f}, {stats1['i_max']:.4f}], "
          f"stage={stats1['stage_counts']}")

    # ── 附件2 ──
    print("\n[3/4] 加载附件2...")
    att2 = load_att2_raw()
    print(f"  原始: {att2.shape}, columns={list(att2.columns)}")

    print("[4/4] 预处理附件2...")
    att2_proc = preprocess_att2(att2)
    att2_proc.to_csv(PROCESSED / "att2_processed.csv", index=False)
    print(f"  已保存 att2_processed.csv ({len(att2_proc)} 行)")

    stats2 = compute_summary_stats(att2_proc, "附件2")
    print(f"  摘要: t=[{stats2['t_min']}, {stats2['t_max']}], "
          f"i=[{stats2['i_min']:.4f}, {stats2['i_max']:.4f}], "
          f"stage={stats2['stage_counts']}")

    # ── 摘要汇总 ──
    summary = pd.DataFrame([stats1, stats2])
    summary.to_csv(PROCESSED / "summary_stats.csv", index=False)
    print("\n[pipeline] 完成！")


if __name__ == "__main__":
    main()

