"""Q1 求解入口：飞轮退化建模与健康评估。

实现:
  - 模型A: 物理指数模型 i(t)=i0+α(e^{βt}-1)+ε, NLLS 估计
  - 模型B: Wiener 漂移过程 X(t)=X0+μt+σB(t), MLE 闭式解
  - 阶段划分: 残差电流阈值法 + PELT 变点检测
  - RUL: 逆高斯首达时分布, 点估计 + 95% CI
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.stats import norm
from scipy.optimize import brentq

# 路径设置
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "code" / "src"
sys.path.insert(0, str(SRC))

from data.constants import (
    I_0, I_F, DELTA_I_F, EPS, THETA_H, THETA_F,
    ALPHA_0, BETA_0, ALPHA_CI, PELT_PEN, DT2,
)
from data.load_tables import load_processed, save_result_table

RESULTS_DIR = ROOT / "code" / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"


# ═══════════════════════════════════════════════════════════════════════
# 模型 A: 物理指数退化模型
# ═══════════════════════════════════════════════════════════════════════

def _exp_model(t: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    """i(t) = i0 + α(e^{βt} - 1)，i0 固定"""
    return I_0 + alpha * (np.exp(beta * t) - 1.0)


def fit_model_a(t: np.ndarray, i: np.ndarray) -> dict:
    """用 Levenberg-Marquardt NLLS 拟合物理指数模型。

    Returns
    -------
    dict with keys: alpha, beta, sigma_eps_sq, rmse, r2, aic, bic, pcov, success
    """
    # 初值
    p0 = [ALPHA_0, BETA_0]
    bounds = ([1e-8, 1e-8], [np.inf, np.inf])

    try:
        popt, pcov = curve_fit(
            _exp_model, t, i,
            p0=p0, method="lm", maxfev=10000,
        )
        alpha_hat, beta_hat = popt
        success = True
    except Exception as e:
        print(f"  [WARN] NLLS 不收敛: {e}, 使用初值")
        alpha_hat, beta_hat = ALPHA_0, BETA_0
        pcov = None
        success = False

    # 残差
    i_pred = _exp_model(t, alpha_hat, beta_hat)
    residuals = i - i_pred
    n, p = len(t), 3  # 模型含 i₀ (固定), α, β 共 3 参数
    sigma_eps_sq = np.sum(residuals ** 2) / (n - p) if n > p else np.nan

    # 拟合优度
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((i - np.mean(i)) ** 2)
    rmse = np.sqrt(ss_res / n)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # AIC / BIC (p=3: i₀ + α + β)
    log_lik = -0.5 * n * (np.log(2 * np.pi * sigma_eps_sq) + 1) if sigma_eps_sq > 0 else 0
    aic = 2 * 3 - 2 * log_lik
    bic = 3 * np.log(n) - 2 * log_lik

    return {
        "alpha": alpha_hat,
        "beta": beta_hat,
        "sigma_eps_sq": sigma_eps_sq,
        "rmse": rmse,
        "r2": r2,
        "aic": aic,
        "bic": bic,
        "pcov": pcov,
        "success": success,
        "i_pred": i_pred,
    }


def predict_rul_model_a(t_current: float, alpha: float, beta: float) -> float:
    """模型 A 外推 RUL: 解 i0 + α(e^{β(t+RUL)} - 1) = iF → RUL = ln(1 + Δi_F/α)/β - t"""
    if beta <= 0 or alpha <= 0:
        return np.inf
    t_eol = np.log(1.0 + DELTA_I_F / alpha) / beta
    return max(0.0, t_eol - t_current)


# ═══════════════════════════════════════════════════════════════════════
# 模型 B: Wiener 漂移退化过程
# ═══════════════════════════════════════════════════════════════════════

def _to_X(i: np.ndarray) -> np.ndarray:
    """对数化: X = ln(current - i0 + EPS)"""
    return np.log(np.maximum(i - I_0, 0.0) + EPS)


def fit_model_b(t: np.ndarray, i: np.ndarray) -> dict:
    """MLE 闭式解估计 Wiener 参数。

    Returns
    -------
    dict with keys: mu, sigma_sq, mu_se, sigma_se, X_seq, X_F
    """
    X = _to_X(i)
    dt = np.diff(t)
    dX = np.diff(X)

    # MLE 闭式解
    T_total = t[-1] - t[0]
    mu_hat = (X[-1] - X[0]) / T_total if T_total > 0 else 0.0

    # 加权残差
    weighted_resid = (dX - mu_hat * dt) ** 2 / dt
    sigma_sq_hat = np.mean(weighted_resid)

    # Fisher 信息标准误
    K = len(dt)
    mu_se = np.sqrt(sigma_sq_hat / T_total) if T_total > 0 else np.inf
    sigma_se = np.sqrt(2 * sigma_sq_hat ** 2 / K) if K > 0 else np.inf

    # 对数化失效阈值
    X_F = np.log(max(I_F - I_0, EPS) + EPS)

    return {
        "mu": mu_hat,
        "sigma_sq": sigma_sq_hat,
        "mu_se": mu_se,
        "sigma_se": sigma_se,
        "X_seq": X,
        "X_F": X_F,
    }


def _ig_cdf(x: float, m: float, lam: float) -> float:
    """逆高斯分布 IG(m, λ) 的 CDF，用标准正态 CDF 表示。

    F(x) = Φ(√(λ/x)·(x/m - 1)) + exp(2λ/m)·Φ(-√(λ/x)·(x/m + 1))
    """
    if x <= 0:
        return 0.0
    z1 = np.sqrt(lam / x) * (x / m - 1.0)
    z2 = -np.sqrt(lam / x) * (x / m + 1.0)
    return float(norm.cdf(z1) + np.exp(2.0 * lam / m) * norm.cdf(z2))


def _ig_ppf(q: float, m: float, lam: float) -> float:
    """逆高斯 IG(m, λ) 的分位数函数 (PPF)，用数值求根。"""
    if q <= 0:
        return 0.0
    if q >= 1:
        return np.inf

    # 搜索区间: 用 Chebyshev 不等式做一个宽松上界
    var_ig = m ** 3 / lam
    lo, hi = 1e-6, m + 20.0 * np.sqrt(var_ig)

    # 扩大上界直到 CDF(hi) >= q
    for _ in range(30):
        if _ig_cdf(hi, m, lam) >= q:
            break
        hi *= 2.0

    try:
        return float(brentq(lambda x: _ig_cdf(x, m, lam) - q, lo, hi, maxiter=100))
    except Exception:
        return m  # 退回均值


def predict_rul_wiener(
    t_current: float,
    i_current: float,
    mu: float,
    sigma_sq: float,
    x_F: float,
) -> dict:
    """Wiener 首达时（逆高斯）RUL 预测。

    Returns
    -------
    dict with: RUL (点估计), CI_lo, CI_hi, P_30, P_90, P_180
    """
    x_t = np.log(max(i_current - I_0, EPS) + EPS)
    delta_x = x_F - x_t

    if delta_x <= 0:
        return {"RUL": 0.0, "CI_lo": 0.0, "CI_hi": 0.0,
                "P_30": 1.0, "P_90": 1.0, "P_180": 1.0}

    if mu <= 0 or sigma_sq <= 0:
        return {"RUL": np.inf, "CI_lo": np.inf, "CI_hi": np.inf,
                "P_30": 0.0, "P_90": 0.0, "P_180": 0.0}

    # IG(m, λ): m = 均值, λ = 形状
    m_ig = delta_x / mu
    lam_ig = delta_x ** 2 / sigma_sq

    rul_hat = m_ig  # E[RUL]
    ci_lo = _ig_ppf(ALPHA_CI / 2, m_ig, lam_ig)
    ci_hi = _ig_ppf(1 - ALPHA_CI / 2, m_ig, lam_ig)

    def _p_rul(days: float) -> float:
        return _ig_cdf(days, m_ig, lam_ig)

    return {
        "RUL": float(rul_hat),
        "CI_lo": float(ci_lo),
        "CI_hi": float(ci_hi),
        "P_30": _p_rul(30),
        "P_90": _p_rul(90),
        "P_180": _p_rul(180),
    }


# ═══════════════════════════════════════════════════════════════════════
# 阶段划分
# ═══════════════════════════════════════════════════════════════════════

def classify_stage_threshold(phi: float) -> str:
    """残差电流阈值法 (主准则)。"""
    if phi < THETA_H:
        return "H"
    elif phi < THETA_F:
        return "D"
    else:
        return "F"


def classify_stage_pelt(values: np.ndarray, pen: float = PELT_PEN) -> list:
    """PELT 变点检测辅助准则 (需要 ruptures 库)。

    返回每点的阶段标签列表。若 ruptures 不可用则返回 None。
    """
    try:
        from ruptures import Pelt
        model = Pelt(model="rbf").fit(values)
        change_points = model.predict(pen=pen)
        # 变点索引 (Python int list)
        n = len(values)
        stages = np.full(n, "H", dtype=object)
        if len(change_points) > 1:
            cp1 = change_points[0]
            stages[cp1:] = "D"
        if len(change_points) > 2:
            cp2 = change_points[1]
            stages[cp2:] = "F"
        return stages.tolist()
    except ImportError:
        return None


def classify_stage_combined(phi_seq: np.ndarray, i_seq: np.ndarray) -> list:
    """合并阈值法和 PELT 法，取较保守者（更早退化/更早衰退）。"""
    stages_thr = [classify_stage_threshold(p) for p in phi_seq]
    stages_pelt = classify_stage_pelt(i_seq)

    if stages_pelt is None:
        return stages_thr

    order = {"H": 0, "D": 1, "F": 2}
    combined = []
    for s1, s2 in zip(stages_thr, stages_pelt):
        combined.append(s1 if order[s1] >= order[s2] else s2)
    return combined


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ── 加载预处理数据 ──
    print("=" * 60)
    print("Q1: 飞轮退化建模与健康评估")
    print("=" * 60)

    att1 = load_processed("att1_processed.csv")
    att2 = load_processed("att2_processed.csv")

    t1 = att1["day"].values
    i1 = att1["current"].values
    t2 = att2["day"].values
    i2 = att2["current"].values

    # ── 模型 A: 物理指数 (用附件1 拟合) ──
    print("\n[模型 A] 物理指数退化模型")
    res_a = fit_model_a(t1, i1)
    print(f"  α = {res_a['alpha']:.6f} A")
    print(f"  β = {res_a['beta']:.8f} /day")
    print(f"  σ_ε² = {res_a['sigma_eps_sq']:.6f}")
    print(f"  RMSE = {res_a['rmse']:.4f}, R² = {res_a['r2']:.4f}")
    print(f"  AIC = {res_a['aic']:.1f}, BIC = {res_a['bic']:.1f}")
    print(f"  NLLS 收敛: {res_a['success']}")

    rul_a = predict_rul_model_a(t2[-1], res_a["alpha"], res_a["beta"])
    print(f"  附件2 RUL (模型A) = {rul_a:.1f} 天")

    # ── 模型 B: Wiener ──
    print("\n[模型 B] Wiener 漂移退化过程")
    res_b = fit_model_b(t2, i2)  # 在附件2 上估计（目标域）
    print(f"  μ = {res_b['mu']:.8f}  /day")
    print(f"  σ² = {res_b['sigma_sq']:.8f}")
    print(f"  μ SE = {res_b['mu_se']:.8f}")
    print(f"  X_F = {res_b['X_F']:.6f}")

    rul_b = predict_rul_wiener(
        t2[-1], i2[-1], res_b["mu"], res_b["sigma_sq"], res_b["X_F"]
    )
    print(f"  附件2 RUL (模型B) = {rul_b['RUL']:.1f} 天")
    print(f"  95% CI: [{rul_b['CI_lo']:.1f}, {rul_b['CI_hi']:.1f}]")
    print(f"  P(RUL<30)={rul_b['P_30']:.4f}, P(RUL<90)={rul_b['P_90']:.4f}, P(RUL<180)={rul_b['P_180']:.4f}")

    # ── A/B 一致性 ──
    print(f"\n[一致性] 模型 A RUL={rul_a:.1f}, 模型 B RUL={rul_b['RUL']:.1f}, "
          f"偏差={abs(rul_a - rul_b['RUL']) / max(rul_a, rul_b['RUL']) * 100:.1f}%")

    # ── 阶段划分 ──
    print("\n[阶段划分]")
    stages_att2 = classify_stage_combined(att2["phi"].values, att2["current"].values)
    att2["stage_combined"] = stages_att2
    current_stage = stages_att2[-1]
    stage_counts = pd.Series(stages_att2).value_counts().to_dict()
    print(f"  附件2 当前阶段 (t=1800): {current_stage}")
    print(f"  阶段分布: {stage_counts}")

    # ── 输出 ──
    # 模型 A 参数表
    df_theta_a = pd.DataFrame([{
        "i0": I_0, "alpha": res_a["alpha"], "beta": res_a["beta"],
        "sigma_eps_sq": res_a["sigma_eps_sq"],
        "rmse": res_a["rmse"], "r2": res_a["r2"],
        "aic": res_a["aic"], "bic": res_a["bic"],
    }])
    save_result_table(df_theta_a, "Q1_theta_A.csv")

    # 模型 B 参数表
    df_theta_b = pd.DataFrame([{
        "mu": res_b["mu"], "sigma_sq": res_b["sigma_sq"],
        "mu_se": res_b["mu_se"], "sigma_se": res_b["sigma_se"],
        "X_F": res_b["X_F"],
    }])
    save_result_table(df_theta_b, "Q1_theta_B_local.csv")

    # RUL 结果
    df_rul = pd.DataFrame([{
        "t_current": int(t2[-1]),
        "RUL_A_days": round(rul_a, 1),
        "RUL_B_days": round(rul_b["RUL"], 1),
        "RUL_B_CI_lo": round(rul_b["CI_lo"], 1),
        "RUL_B_CI_hi": round(rul_b["CI_hi"], 1),
        "P_RUL_lt_30": round(rul_b["P_30"], 4),
        "P_RUL_lt_90": round(rul_b["P_90"], 4),
        "P_RUL_lt_180": round(rul_b["P_180"], 4),
        "stage": current_stage,
    }])
    save_result_table(df_rul, "Q1_rul.csv")

    # 附加阶段详情
    df_stages = att2[["day", "current", "phi", "stage", "stage_combined"]].copy()
    df_stages.to_csv(TABLES_DIR / "Q1_stages_att2.csv", index=False)

    # 汇总 JSON (供 Q3 读取)
    q1_summary = {
        "theta_A": {
            "i0": I_0, "alpha": float(res_a["alpha"]), "beta": float(res_a["beta"]),
            "sigma_eps_sq": float(res_a["sigma_eps_sq"]),
        },
        "theta_B_local": {
            "mu": float(res_b["mu"]), "sigma_sq": float(res_b["sigma_sq"]),
        },
        "RUL_A": float(rul_a),
        "RUL_B": float(rul_b["RUL"]),
        "RUL_CI": [float(rul_b["CI_lo"]), float(rul_b["CI_hi"])],
        "stage": current_stage,
        "probabilities": {
            "P_30": float(rul_b["P_30"]),
            "P_90": float(rul_b["P_90"]),
            "P_180": float(rul_b["P_180"]),
        },
    }
    with open(TABLES_DIR / "Q1_summary.json", "w", encoding="utf-8") as f:
        json.dump(q1_summary, f, indent=2, ensure_ascii=False)

    print("\n[Q1] 完成！")


if __name__ == "__main__":
    main()

