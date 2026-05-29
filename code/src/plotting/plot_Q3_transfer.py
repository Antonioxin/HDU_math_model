"""Q3 图: MMD 对比柱状图 + 迁移前后 RUL 对比."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import apply_style

ROOT = Path(__file__).resolve().parents[3]
FIG_DIR = ROOT / "code" / "results" / "figures"
TABLES_DIR = ROOT / "code" / "results" / "tables"


def main() -> None:
    apply_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    mmd_path = TABLES_DIR / "Q3_mmd_coral.csv"
    q3_path = TABLES_DIR / "Q3_summary.json"
    q1_path = TABLES_DIR / "Q1_summary.json"

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # ── (a) MMD 柱状图 ──
    if mmd_path.exists():
        df_mmd = pd.read_csv(mmd_path)
        ax = axes[0]
        bearings = df_mmd["bearing"].values
        mmds = df_mmd["MMD"].values
        colors = ["#1f77b4" if m == mmds.min() else "#7f7f7f" for m in mmds]
        bars = ax.bar(range(len(bearings)), mmds, color=colors, edgecolor="white")
        ax.set_xticks(range(len(bearings)))
        ax.set_xticklabels([b.replace("Bearing", "") for b in bearings], fontsize=8)
        ax.set_ylabel("MMD")
        ax.set_title("源-目标域 MMD 距离")
        ax.axhline(0.10, color="red", ls="--", alpha=0.5, label="MMD_thr=0.10")
        ax.legend(fontsize=8)

    # ── (b) Q1 vs Q3 RUL 对比 ──
    if q3_path.exists() and q1_path.exists():
        with open(q3_path, encoding="utf-8") as f:
            q3 = json.load(f)
        with open(q1_path, encoding="utf-8") as f:
            q1 = json.load(f)

        ax = axes[1]
        methods = ["Q1 (无迁移)", "Q3 (有迁移)"]
        ruls = [q1["RUL_B"], q3["RUL_TL"]]
        ci_los = [q1["RUL_CI"][0], q3["RUL_TL_CI"][0]]
        ci_his = [q1["RUL_CI"][1], q3["RUL_TL_CI"][1]]
        yerr_lo = [max(0, r - lo) for r, lo in zip(ruls, ci_los)]
        yerr_hi = [hi - r for r, hi in zip(ruls, ci_his)]

        ax.bar(methods, ruls, color=["#7f7f7f", "#2ca02c"], edgecolor="white",
               yerr=[yerr_lo, yerr_hi], capsize=8)
        for i, (r, lo, hi) in enumerate(zip(ruls, ci_los, ci_his)):
            ax.text(i, hi + 5, f"{r:.0f}d\n[{lo:.0f}, {hi:.0f}]",
                    ha="center", fontsize=9)
        ax.set_ylabel("RUL (天)")
        ax.set_title("迁移前后 RUL 对比")

    fig.tight_layout()
    fig.savefig(FIG_DIR / "Q3_transfer_comparison.png")
    print(f"[plot] saved Q3_transfer_comparison.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
