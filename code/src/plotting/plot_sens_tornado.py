"""敏感性 tornado 图: 汇总各参数对 RUL 的影响."""
from __future__ import annotations

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


def _get_rul_range(csv_path: str) -> tuple[str, float, float, float]:
    """读取敏感性 CSV，返回 (参数名, baseline, min, max)."""
    p = TABLES_DIR / csv_path
    if not p.exists():
        return ("", 0, 0, 0)
    df = pd.read_csv(p)
    if "RUL" not in df.columns or len(df) < 2:
        return ("", 0, 0, 0)

    ruls = df["RUL"].dropna().values
    if len(ruls) == 0:
        return ("", 0, 0, 0)

    param_name = str(df["param"].values[0]) if "param" in df.columns else csv_path
    return (param_name, ruls[0], ruls.min(), ruls.max())


def main() -> None:
    apply_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    sens_files = [
        ("失效阈值 i_F", "Q1_sens_I_F.csv"),
        ("Wiener 窗口", "Q1_sens_wiener_window.csv"),
        ("平滑窗口 W", "Q1_sens_wsmooth.csv"),
        ("迁移带宽 h", "Q3_sens_h.csv"),
    ]

    items = []
    for label, fname in sens_files:
        name, base, lo, hi = _get_rul_range(fname)
        if base > 0:
            items.append({
                "label": label,
                "baseline": base,
                "min": lo,
                "max": hi,
                "range_pct": (hi - lo) / base * 100 if base > 0 else 0,
            })

    if not items:
        print("[plot sens] 无敏感性数据可画")
        return

    items.sort(key=lambda x: x["range_pct"], reverse=True)

    fig, ax = plt.subplots(figsize=(8, 5))

    labels = [it["label"] for it in items]
    y_pos = range(len(labels))

    for i, it in enumerate(items):
        lo_pct = (it["min"] - it["baseline"]) / it["baseline"] * 100
        hi_pct = (it["max"] - it["baseline"]) / it["baseline"] * 100
        ax.barh(i, hi_pct - lo_pct, left=lo_pct, height=0.5,
                color="#1f77b4", alpha=0.7, edgecolor="white")
        ax.axvline(0, color="black", lw=0.8)

        # 标注数值
        for pct, x_offset in [(lo_pct, -1), (hi_pct, 1)]:
            if abs(pct) > 1:
                ax.text(pct + x_offset * 0.5, i, f"{it['min']:.0f}" if pct < 0 else f"{it['max']:.0f}",
                        va="center", ha="right" if pct < 0 else "left", fontsize=8)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.set_xlabel("RUL 变化 (%)")
    ax.set_title("敏感性 Tornado 图")
    ax.axvline(0, color="black", lw=0.8)
    ax.invert_yaxis()

    fig.tight_layout()
    fig.savefig(FIG_DIR / "sens_tornado.png")
    print(f"[plot] saved sens_tornado.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
