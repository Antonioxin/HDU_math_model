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
    I_0, I_F, DELTA_I_F, THETA_H, THETA_F,
    ALPHA_0, BETA_0, ALPHA_CI, BETA_PEN, DT2,
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
# 模型 B: Λ-时间 Wiener 退化过程 (修订版, 弃用对数变换)
# ═══════════════════════════════════════════════════════════════════════

def _Lambda(t: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    """运行时间: Λ(t) = α(e^{βt} - 1)"""
    return alpha * np.expm1(beta * t)


def _Lambda_inv(s: float, alpha: float, beta: float) -> float:
    """运行时间逆映射: t = ln(1 + s/α) / β"""
    return np.log1p(s / alpha) / beta


def fit_wiener_lambda(t: np.ndarray, i: np.ndarray,
                      alpha: float, beta: float) -> dict:
    """Λ-时间 Wiener 退化过程参数估计。

    退化信号 D(t) = i(t) - i₀, D(t) = Λ(t) + σ_B·B(Λ(t))
    σ_B² = (1/(K-1)) Σ (Δr_k)² / ΔΛ_k, r_k = D_k - Λ(t_k)

    Returns dict: {sigma_B2, rmse, r2}
    """
    D = i - I_0
    Lam = _Lambda(t, alpha, beta)
    r = D - Lam              # 残差
    dLam = np.diff(Lam)
    dr = np.diff(r)

    K = len(t)
    mask = dLam > 1e-15
    if mask.sum() < 2:
        return {"sigma_B2": 1e-10, "rmse": 0.0, "r2": 0.0}

    sigma_B2 = float(np.sum((dr[mask]) ** 2 / dLam[mask]) / (mask.sum() - 1))

    # 拟合优度
    rmse = float(np.sqrt(np.mean(r ** 2)))
    ss_tot = np.sum((D - np.mean(D)) ** 2)
    r2 = 1 - np.sum(r ** 2) / ss_tot if ss_tot > 0 else 0.0

    return {
        "sigma_B2": sigma_B2,
        "rmse": rmse,
        "r2": r2,
        "D_seq": D,
        "Lam_seq": Lam,
    }


def predict_rul_lambda_wiener(
    t_current: float,
    i_current: float,
    alpha: float,
    beta: float,
    sigma_B2: float,
) -> dict:
    """Λ-时间 Wiener 首达时 RUL 预测。

    1. D_c = i_current - I_0, D_F = I_F - I_0
    2. ΔU ~ IG(D_F - D_c, (D_F - D_c)²/σ_B²)  (Λ-空间内的剩余运行时间)
    3. RUL = Λ⁻¹(Λ(t_c) + ΔU) - t_c

    Returns dict: RUL, CI_lo, CI_hi, P_30, P_90, P_180
    """
    D_c = i_current - I_0
    D_F = I_F - I_0

    if D_F <= D_c:
        return {"RUL": 0.0, "CI_lo": 0.0, "CI_hi": 0.0,
                "P_30": 1.0, "P_90": 1.0, "P_180": 1.0}

    if sigma_B2 <= 0 or beta <= 0 or alpha <= 0:
        return {"RUL": np.inf, "CI_lo": np.inf, "CI_hi": np.inf,
                "P_30": 0.0, "P_90": 0.0, "P_180": 0.0}

    # IG on ΔU (Λ-空间剩余量)
    delta_D = D_F - D_c
    m_ig = delta_D           # E[ΔU]
    lam_ig = delta_D ** 2 / sigma_B2  # 形状

    # 点估计: E[ΔU] → 映回日历
    Lam_c = _Lambda(np.array([t_current]), alpha, beta)[0]
    dU_med = m_ig
    t_eol_med = _Lambda_inv(Lam_c + dU_med, alpha, beta)
    rul_hat = max(0.0, t_eol_med - t_current)

    # CI: 取 IG 分位数 → 映射
    ci_lo_dU = _ig_ppf(ALPHA_CI / 2, m_ig, lam_ig)
    ci_hi_dU = _ig_ppf(1 - ALPHA_CI / 2, m_ig, lam_ig)

    t_eol_lo = _Lambda_inv(Lam_c + ci_lo_dU, alpha, beta)
    t_eol_hi = _Lambda_inv(Lam_c + ci_hi_dU, alpha, beta)
    ci_lo = max(0.0, t_eol_lo - t_current)
    ci_hi = max(0.0, t_eol_hi - t_current)

    # RUL 概率: P(RUL < days) = P(t_eol < t_c + days)
    # = P(ΔU < Λ(t_c + days) - Λ(t_c))
    def _p_rul(days: float) -> float:
        Lam_target = _Lambda(np.array([t_current + days]), alpha, beta)[0]
        dU_target = Lam_target - Lam_c
        return _ig_cdf(dU_target, m_ig, lam_ig)

    return {
        "RUL": float(rul_hat),
        "CI_lo": float(ci_lo),
        "CI_hi": float(ci_hi),
        "P_30": _p_rul(30),
        "P_90": _p_rul(90),
        "P_180": _p_rul(180),
    }


# ═══════════════════════════════════════════════════════════════════════
# 逆高斯分布工具函数
# ═══════════════════════════════════════════════════════════════════════

def _ig_cdf(x: float, m: float, lam: float) -> float:
    """IG(m, λ) CDF: Φ(√(λ/x)(x/m-1)) + exp(2λ/m)Φ(-√(λ/x)(x/m+1))"""
    if x <= 0:
        return 0.0
    z1 = np.sqrt(lam / x) * (x / m - 1.0)
    z2 = -np.sqrt(lam / x) * (x / m + 1.0)
    return float(norm.cdf(z1) + np.exp(2.0 * lam / m) * norm.cdf(z2))


def _ig_ppf(q: float, m: float, lam: float) -> float:
    """IG(m, λ) PPF，数值求根."""
    if q <= 0:
        return 0.0
    if q >= 1:
        return np.inf
    var_ig = m ** 3 / lam
    lo, hi = 1e-6, m + 20.0 * np.sqrt(var_ig)
    for _ in range(30):
        if _ig_cdf(hi, m, lam) >= q:
            break
        hi *= 2.0
    try:
        return float(brentq(lambda x: _ig_cdf(x, m, lam) - q, lo, hi, maxiter=100))
    except Exception:
        return m


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


def classify_stage_pelt(values: np.ndarray, pen: float | None = None) -> list:
    """PELT 变点检测辅助准则。pen=None 时自适应: pen = BETA_PEN * var(resid) * ln(K)。"""
    if pen is None:
        # 自适应罚项
        smooth = pd.Series(values).rolling(window=min(10, len(values)),
                                            min_periods=1, center=True).mean().values
        resid_var = np.var(values - smooth) if len(values) > 1 else 1.0
        pen = BETA_PEN * resid_var * np.log(len(values))
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

    # ── 模型 A: 附件1 全寿命拟合 + 附件2 独立拟合 ──
    print("\n[模型 A] 物理指数退化模型")
    res_a = fit_model_a(t1, i1)            # 附件1 全寿命模板
    res_a_t = fit_model_a(t2, i2)          # ★ 附件2 独立拟合
    print(f"  附件1: α={res_a['alpha']:.6f}, β={res_a['beta']:.8f}, R²={res_a['r2']:.4f}")
    print(f"  附件2: α={res_a_t['alpha']:.6f}, β={res_a_t['beta']:.8f}, R²={res_a_t['r2']:.4f}")

    # 附件2 RUL 用附件2 自身参数
    rul_a = predict_rul_model_a(t2[-1], res_a_t["alpha"], res_a_t["beta"])
    print(f"  附件2 RUL (模型A) = {rul_a:.1f} 天")

    # ── 模型 B: Λ-时间 Wiener (附件2 独立参数) ──
    print("\n[模型 B] Λ-时间 Wiener 退化过程")
    res_b = fit_wiener_lambda(t2, i2, res_a_t["alpha"], res_a_t["beta"])
    print(f"  σ_B² = {res_b['sigma_B2']:.8f}")
    print(f"  RMSE (残差) = {res_b['rmse']:.4f}, R² = {res_b['r2']:.4f}")

    rul_b = predict_rul_lambda_wiener(
        t2[-1], i2[-1], res_a_t["alpha"], res_a_t["beta"], res_b["sigma_B2"]
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

    # 模型 A (附件2) 参数表
    df_theta_a2 = pd.DataFrame([{
        "i0": I_0, "alpha": res_a_t["alpha"], "beta": res_a_t["beta"],
        "sigma_eps_sq": res_a_t["sigma_eps_sq"],
        "rmse": res_a_t["rmse"], "r2": res_a_t["r2"],
        "aic": res_a_t["aic"], "bic": res_a_t["bic"],
    }])
    save_result_table(df_theta_a2, "Q1_theta_A_att2.csv")

    # 模型 B 参数表 (附件2 独立)
    df_theta_b = pd.DataFrame([{
        "alpha": res_a_t["alpha"], "beta": res_a_t["beta"],
        "sigma_B2": res_b["sigma_B2"],
        "rmse": res_b["rmse"], "r2": res_b["r2"],
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
            "alpha": float(res_a_t["alpha"]), "beta": float(res_a_t["beta"]),
            "sigma_B2": float(res_b["sigma_B2"]),
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

