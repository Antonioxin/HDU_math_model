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
    """读取敏感性 CSV。优先 RUL；若平坦则回退 CI_width."""
    p = TABLES_DIR / csv_path
    if not p.exists():
        return ("", 0, 0, 0)
    df = pd.read_csv(p)
    param_name = str(df.iloc[0, 0]) if len(df.columns) > 0 else csv_path

    for col in ["RUL", "RUL_TL"]:
        if col in df.columns:
            vals = df[col].dropna().values
            if len(vals) >= 2 and (vals.max() - vals.min()) / max(abs(vals[0]), 1) > 0.005:
                return (param_name, float(vals[0]), float(vals.min()), float(vals.max()))
    for col in ["CI_width", "CI_width_TL"]:
        if col in df.columns:
            vals = df[col].dropna().values
            if len(vals) >= 2:
                return (param_name, float(vals[0]), float(vals.min()), float(vals.max()))
    return ("", 0, 0, 0)


def main() -> None:
    apply_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    sens_files = [
        ("σ_B 缩放\n(CI 宽度)", "Q1_sens_sigma_B.csv"),
        ("Wiener\n拟合窗口",     "Q1_sens_wiener_window.csv"),
    ]

    items = []
    for label, fname in sens_files:
        name, base, lo, hi = _get_rul_range(fname)
        if base > 0 and (hi - lo) / base > 0.005:
            items.append({
                "label": label,
                "baseline": base,
                "min": lo,
                "max": hi,
                "range_pct": (hi - lo) / base * 100 if base > 0 else 0,
            })
        else:
            print(f"  [skip] {label}: 变化过小或无 RUL 列")

    if not items:
        print("[plot sens] 无敏感性数据可画")
        return

    items.sort(key=lambda x: x["range_pct"], reverse=True)

    fig, ax = plt.subplots(figsize=(10, 3.5 + 0.5 * len(items)))

    labels = [it["label"] for it in items]
    y_pos = range(len(labels))

    for i, it in enumerate(items):
        lo_pct = (it["min"] - it["baseline"]) / it["baseline"] * 100
        hi_pct = (it["max"] - it["baseline"]) / it["baseline"] * 100
        ax.barh(i, hi_pct - lo_pct, left=lo_pct, height=0.6,
                color="#4472C4", alpha=0.85, edgecolor="white", linewidth=0.5)

        # 数值标在 bar 两端外侧
        bar_left = lo_pct
        bar_right = hi_pct
        if abs(bar_left) > 0.5:
            ax.text(bar_left - 6.0, i, f"{it['min']:.0f}",
                    va="center", ha="right", fontsize=8, color="#333")
        if abs(bar_right) > 0.5 and (bar_right - bar_left) > 5:
            ax.text(bar_right + 4.0, i, f"{it['max']:.0f}",
                    va="center", ha="left", fontsize=8, color="#333")

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("相对基线变化 (%)", fontsize=10)
    ax.set_title("敏感性 Tornado 图", fontsize=12, fontweight="bold")
    ax.axvline(0, color="black", lw=0.8)
    ax.invert_yaxis()

    fig.subplots_adjust(left=0.42, right=0.92, top=0.90, bottom=0.15)
    ax.set_xlim(-100, ax.get_xlim()[1] + 5)

    fig.savefig(FIG_DIR / "sens_tornado.png", dpi=150)
    print(f"[plot] saved sens_tornado.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
