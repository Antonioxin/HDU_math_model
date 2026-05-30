"""Q1 图: 附件1 指数拟合 + 附件2 RUL 概率分布。"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 非交互式后端
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _style import apply_style

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "code" / "src"

sys.path.insert(0, str(SRC))
from data.constants import I_0, I_F, THETA_H, THETA_F
from data.load_tables import load_processed
from q1.run_q1 import _exp_model, fit_model_a, predict_rul_lambda_wiener, fit_wiener_lambda

FIG_DIR = ROOT / "code" / "results" / "figures"
TABLES_DIR = ROOT / "code" / "results" / "tables"
STAGE_COLORS = {"H": "#2ca02c", "D": "#ff7f0e", "F": "#d62728"}


def main() -> None:
    apply_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    att1 = load_processed("att1_processed.csv")
    att2 = load_processed("att2_processed.csv")

    # ── (a) 附件1 物理指数拟合 ──
    res_a = fit_model_a(att1["day"].values, att1["current"].values)
    t_fit = np.linspace(0, 3500, 200)
    i_fit = _exp_model(t_fit, res_a["alpha"], res_a["beta"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    ax.scatter(att1["day"], att1["current"], s=8, alpha=0.5, label="实测")
    ax.plot(t_fit, i_fit, "r-", lw=1.5, label=f"拟合: i₀+α(e^βt-1)")
    ax.axhline(I_F, color="gray", ls="--", alpha=0.5, label=f"i_F={I_F}A")
    ax.set_xlabel("时间 (天)")
    ax.set_ylabel("电流 (A)")
    ax.set_title(f"附件1 物理指数拟合\nα={res_a['alpha']:.4f}, β={res_a['beta']:.6f}, R²={res_a['r2']:.3f}")
    ax.legend(fontsize=8)
    ax.set_xlim(0, 3600)

    # ── (b) 附件2 RUL 概率密度 (Lambda-时间 Wiener) ──
    res_b = fit_wiener_lambda(att2["day"].values, att2["current"].values,
                              res_a["alpha"], res_a["beta"])
    rul = predict_rul_lambda_wiener(
        att2["day"].values[-1], att2["current"].values[-1],
        res_a["alpha"], res_a["beta"], res_b["sigma_B2"],
    )

    from scipy.stats import norm as _norm
    if rul["RUL"] > 0 and rul["CI_hi"] > rul["CI_lo"]:
        x_rul = np.linspace(max(0, rul["CI_lo"] * 0.5),
                            rul["CI_hi"] * 1.2, 300)
        sigma_approx = (rul["CI_hi"] - rul["CI_lo"]) / (2 * 1.96)
        pdf = _norm.pdf(x_rul, rul["RUL"], sigma_approx)

        ax = axes[1]
        ax.plot(x_rul, pdf, "b-", lw=1.5)
        ax.axvline(rul["RUL"], color="b", ls="--", alpha=0.7, label=f"RUL={rul['RUL']:.0f}d")
        ax.axvline(rul["CI_lo"], color="gray", ls=":", alpha=0.7)
        ax.axvline(rul["CI_hi"], color="gray", ls=":", alpha=0.7)
        ax.fill_between(x_rul, pdf, alpha=0.15, color="b",
                        where=(x_rul >= rul["CI_lo"]) & (x_rul <= rul["CI_hi"]))
        ax.set_xlabel("剩余寿命 RUL (天)")
        ax.set_ylabel("概率密度")
        ax.set_title(f"附件2 RUL 分布 (Lambda-Wiener)\n95% CI: [{rul['CI_lo']:.0f}, {rul['CI_hi']:.0f}] 天")
        ax.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(FIG_DIR / "Q1_fit_and_rul.png")
    print(f"[plot] saved Q1_fit_and_rul.png")
    plt.close(fig)


if __name__ == "__main__":
    main()

