"""回归测试: 按 model/边界检验设计.md 实现关键断言。

运行: pytest code/tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path.cwd()
# 若从 repo 根目录运行则正确，否则尝试向上查找
if not (ROOT / "code").exists():
    ROOT = Path(__file__).resolve().parents[1] if '__file__' in dir() else Path.cwd()
SRC = ROOT / "code" / "src"
sys.path.insert(0, str(SRC))

from data.constants import I_0, I_F, DELTA_I_F
from data.load_tables import load_processed
from q1.run_q1 import (
    fit_model_a, fit_wiener_lambda, predict_rul_lambda_wiener,
    _ig_cdf, _ig_ppf,
)
from q3.run_q3 import determine_alert_level


def test_q1_ab_consistency():
    """Q1-T5: 附件2 A/B RUL 偏差 < 15% (目标 <2%)."""
    att2 = load_processed("att2_processed.csv")
    t2, i2 = att2["day"].values, att2["current"].values
    res_a_t = fit_model_a(t2, i2)
    res_b = fit_wiener_lambda(t2, i2, res_a_t["alpha"], res_a_t["beta"])
    rul_a = np.log(1.0 + DELTA_I_F / res_a_t["alpha"]) / res_a_t["beta"] - t2[-1]
    rul_b = predict_rul_lambda_wiener(
        t2[-1], i2[-1], res_a_t["alpha"], res_a_t["beta"], res_b["sigma_B2"]
    )
    dev = abs(rul_a - rul_b["RUL"]) / max(rul_a, rul_b["RUL"]) * 100
    assert dev < 15, f"A/B deviation {dev:.1f}% >= 15%"


def test_q1_sigma_zero_degeneracy():
    """Q1-T2: sigma_B->0 时 RUL CI 收窄."""
    att2 = load_processed("att2_processed.csv")
    t2, i2 = att2["day"].values, att2["current"].values
    res_a_t = fit_model_a(t2, i2)
    r_small = predict_rul_lambda_wiener(t2[-1], i2[-1], res_a_t["alpha"], res_a_t["beta"], 1e-10)
    r_base = predict_rul_lambda_wiener(t2[-1], i2[-1], res_a_t["alpha"], res_a_t["beta"], 0.03)
    assert (r_small["CI_hi"] - r_small["CI_lo"]) < (r_base["CI_hi"] - r_base["CI_lo"])


def test_q1_beta_zero_degeneracy():
    """Q1-T1: beta->0 退化到线性 i = i0 + alpha*beta*t."""
    t = np.array([0, 100, 200])
    i_linear = I_0 + 0.01 * 0.0001 * t
    res = fit_model_a(t, i_linear)
    assert res["success"]
    assert res["beta"] < 1e-3, f"beta should be near zero, got {res['beta']}"


def test_q3_warning_partial_order():
    """Q3: S=F => L>=L2; S=H => L<=L1."""
    level_order = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
    # S=F 时应 >= L2
    l_f = determine_alert_level("F", 0.01, 0.01, 0.01)
    assert level_order[l_f] >= level_order["L2"], f"F stage should be >=L2, got {l_f}"
    # S=H 低概率时应为 L0
    assert determine_alert_level("H", 0.01, 0.01, 0.01) == "L0"
    # S=H 中等概率时应触发 L1
    l_h = determine_alert_level("H", 0.01, 0.01, 0.10)
    assert level_order[l_h] >= level_order["L1"], f"H+mid => >=L1, got {l_h}"


def test_ig_consistency():
    """IG CDF/PPF 互逆验证."""
    m, lam = 100.0, 200.0
    for q in [0.025, 0.5, 0.975]:
        x = _ig_ppf(q, m, lam)
        q_back = _ig_cdf(x, m, lam)
        assert abs(q - q_back) < 0.01, f"IG inv error at q={q}"
