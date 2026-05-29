"""Q2 图: 迁移源轴承 HI 曲线 + 阶段划分."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import apply_style

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "code" / "src"
sys.path.insert(0, str(SRC))
from data.constants import MIGRATION_SOURCE_BEARINGS

FIG_DIR = ROOT / "code" / "results" / "figures"
TABLES_DIR = ROOT / "code" / "results" / "tables"
STAGE_COLORS = {"H": "#2ca02c", "D": "#ff7f0e", "F": "#d62728"}


def main() -> None:
    apply_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    hi_files = list(TABLES_DIR.glob("Q2_HI_*.csv"))
    if not hi_files:
        print("[plot Q2] 无 HI 文件, 跳过")
        return

    # 只画迁移源轴承
    source_bearings = [b for b in MIGRATION_SOURCE_BEARINGS
                       if (TABLES_DIR / f"Q2_HI_{b}.csv").exists()]

    if not source_bearings:
        source_bearings = [f.stem.replace("Q2_HI_", "") for f in hi_files[:3]]

    n = len(source_bearings)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 4))
    if n == 1:
        axes = [axes]

    for ax, bname in zip(axes, source_bearings):
        df = pd.read_csv(TABLES_DIR / f"Q2_HI_{bname}.csv")
        t = df["t_min"].values
        hi = df["HI"].values
        stages = df["stage"].values if "stage" in df.columns else None

        ax.plot(t, hi, "k-", lw=0.8, alpha=0.5)
        if stages is not None:
            for s, c in STAGE_COLORS.items():
                mask = np.array(stages) == s
                if mask.any():
                    ax.scatter(t[mask], hi[mask], c=c, s=10, alpha=0.6, label=s)
        ax.axhline(0.9, color="gray", ls="--", alpha=0.5, label="HI_F=0.9")
        ax.set_xlabel("时间 (min)")
        ax.set_ylabel("HI")
        ax.set_title(f"{bname}")
        ax.legend(fontsize=8)

    fig.suptitle("轴承健康指数 (HI) 退化曲线", fontsize=14)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "Q2_HI_curves.png")
    print(f"[plot] saved Q2_HI_curves.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
