"""Q3 求解入口：跨域迁移学习 + 预警机制 + 健康管理报告。

实现:
  - 可迁移性分析 (MMD, CORAL, t-SNE)
  - L1: 时间尺度对齐 (tau in [0,1])
  - L2: 形态对齐 (仿射映射)
  - L3: 加权融合 (MMD 权重)
  - 迁移后 RUL 推断 (逆高斯)
  - 四级预警 + 健康管理报告
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, norm
from scipy.optimize import curve_fit, brentq

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "code" / "src"
sys.path.insert(0, str(SRC))

from data.constants import (
    I_0, I_F, DELTA_I_F, EPS, H_BANDWIDTH, MMD_THR, ALPHA_CI,
    P_THR_180, P_THR_180_UP, P_THR_90, P_THR_30,
    LEVEL_NORMAL, LEVEL_ATTENTION, LEVEL_ALERT, LEVEL_EMERGENCY,
    ALERT_ACTIONS, MIGRATION_SOURCE_BEARINGS, DT2,
)
from data.load_tables import load_processed, save_result_table

RESULTS_DIR = ROOT / "code" / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

def _to_X(i: np.ndarray) -> np.ndarray:
    return np.log(np.maximum(i - I_0, 0.0) + EPS)


def _ig_cdf(x: float, m: float, lam: float) -> float:
    if x <= 0:
        return 0.0
    z1 = np.sqrt(lam / x) * (x / m - 1.0)
    z2 = -np.sqrt(lam / x) * (x / m + 1.0)
    return float(norm.cdf(z1) + np.exp(2.0 * lam / m) * norm.cdf(z2))


def _ig_ppf(q: float, m: float, lam: float) -> float:
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


def median_heuristic(X: np.ndarray) -> float:
    """高斯核带宽的 median heuristic."""
    from scipy.spatial.distance import pdist
    if len(X) < 2:
        return 1.0
    dists = pdist(X.reshape(-1, 1), metric="euclidean")
    return float(np.median(dists[dists > 0])) if np.any(dists > 0) else 1.0


def gaussian_kernel(x: np.ndarray, y: np.ndarray, bandwidth: float) -> np.ndarray:
    dist = np.sum((x[:, None] - y[None, :]) ** 2, axis=-1) if x.ndim > 1 else (x[:, None] - y[None, :]) ** 2
    return np.exp(-dist / (2 * bandwidth ** 2))


def compute_mmd(source: np.ndarray, target: np.ndarray) -> float:
    """MMD² (高斯核 RKHS), source/target 为一维退化序列."""
    hk = median_heuristic(np.concatenate([source, target]))
    K_ss = gaussian_kernel(source, source, hk)
    K_tt = gaussian_kernel(target, target, hk)
    K_st = gaussian_kernel(source, target, hk)
    ns, nt = len(source), len(target)
    mmd2 = np.mean(K_ss) + np.mean(K_tt) - 2 * np.mean(K_st)
    return float(np.sqrt(max(0.0, mmd2)))


def compute_coral(source: np.ndarray, target: np.ndarray) -> float:
    """CORAL 距离 (二阶矩对齐)."""
    cs = np.cov(source.reshape(1, -1)) if source.ndim == 1 else np.cov(source.T)
    ct = np.cov(target.reshape(1, -1)) if target.ndim == 1 else np.cov(target.T)
    d = 1
    return float(1.0 / (4 * d ** 2) * np.sum((cs - ct) ** 2))


def phm_score(delta: np.ndarray) -> float:
    """PHM Score Function (非对称损失)."""
    scores = np.where(delta < 0,
                      np.exp(-delta / 13) - 1,
                      np.exp(delta / 10) - 1)
    return float(np.mean(scores))


# ═══════════════════════════════════════════════════════════════════════
# L1: 时间尺度对齐
# ═══════════════════════════════════════════════════════════════════════

def normalize_to_tau(t: np.ndarray, values: np.ndarray,
                     n_grid: int = 50) -> np.ndarray:
    """将退化曲线归一化到 tau in [0,1], 均匀 n_grid 网格插值."""
    if t[-1] <= t[0]:
        return values
    tau_orig = (t - t[0]) / (t[-1] - t[0])
    tau_grid = np.linspace(0, 1, n_grid)
    return np.interp(tau_grid, tau_orig, values)


# ═══════════════════════════════════════════════════════════════════════
# L2: 形态对齐 (仿射映射)
# ═══════════════════════════════════════════════════════════════════════

def estimate_affine(
    source_tau: np.ndarray, source_vals: np.ndarray,
    target_tau: np.ndarray, target_vals: np.ndarray,
) -> tuple[float, float]:
    """用早期段 (前 50% tau) 最小二乘估计仿射参数 (a, b).

    target ≈ a * source + b
    """
    early_mask = source_tau <= 0.5
    if not np.any(early_mask):
        return 1.0, 0.0

    s_early = source_vals[early_mask]
    t_early = target_vals[early_mask]

    A = np.column_stack([s_early, np.ones_like(s_early)])
    try:
        x, residuals, rank, s = np.linalg.lstsq(A, t_early, rcond=None)
        return float(x[0]), float(x[1])
    except Exception:
        return 1.0, 0.0


# ═══════════════════════════════════════════════════════════════════════
# 预警等级判定
# ═══════════════════════════════════════════════════════════════════════

def determine_alert_level(
    stage: str,
    p_30: float, p_90: float, p_180: float,
) -> str:
    """四级预警判定.

    规则:
      - L3 紧急: stage == 'F' 或 P(RUL<30) >= P_THR_30
      - L2 告警: stage == 'D' 且 P(RUL<180) >= P_THR_180_UP 或 P(RUL<90) >= P_THR_90
      - L1 关注: P(RUL<180) >= P_THR_180
      - L0 正常: 其余
    """
    if stage == "F" or p_30 >= P_THR_30:
        return LEVEL_EMERGENCY
    if stage == "D" and (p_180 >= P_THR_180_UP or p_90 >= P_THR_90):
        return LEVEL_ALERT
    if p_180 >= P_THR_180:
        return LEVEL_ATTENTION
    return LEVEL_NORMAL


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Q3: 跨域迁移学习 + 预警机制")
    print("=" * 60)

    # ── 加载 Q1/Q2 输出 ──
    q1_path = TABLES_DIR / "Q1_summary.json"
    q2_path = TABLES_DIR / "Q2_summary.json"
    if not q1_path.exists():
        print(f"[ERROR] Q1 结果不存在: {q1_path}, 请先运行 Q1")
        return
    if not q2_path.exists():
        print(f"[WARN] Q2 结果不存在: {q2_path}, 使用 Q1 退化到无迁移模式")

    with open(q1_path) as f:
        q1 = json.load(f)

    theta_b_local = q1["theta_B_local"]
    mu_local = theta_b_local["mu"]
    sigma_sq_local = theta_b_local["sigma_sq"]
    print(f"\n[Q1 目标域]  mu_local={mu_local:.8f}, sigma2_local={sigma_sq_local:.8f}")
    print(f"  RUL(Q1)={q1['RUL_B']:.1f} 天, CI=[{q1['RUL_CI'][0]:.1f}, {q1['RUL_CI'][1]:.1f}]")

    # ── 加载附件1/2 ──
    att1 = load_processed("att1_processed.csv")
    att2 = load_processed("att2_processed.csv")

    # ── 可迁移性分析 ──
    print("\n" + "=" * 60)
    print("可迁移性分析")
    print("=" * 60)

    # 源域: 附件1 归一化退化曲线
    t1 = att1["day"].values
    i1 = att1["current"].values
    g_target_att1 = normalize_to_tau(t1, (i1 - I_0) / DELTA_I_F)

    # 加载 Q2 归一化 HI
    if q2_path.exists():
        with open(q2_path) as f:
            q2 = json.load(f)
        hi_norm_path = TABLES_DIR / "Q2_HI_normalized.csv"
        if hi_norm_path.exists():
            df_hi_norm = pd.read_csv(hi_norm_path)
        else:
            df_hi_norm = None
    else:
        q2 = None
        df_hi_norm = None

    mmd_results = {}
    if df_hi_norm is not None:
        for bname in MIGRATION_SOURCE_BEARINGS:
            b_data = df_hi_norm[df_hi_norm["bearing"] == bname]
            if len(b_data) < 10:
                mmd_results[bname] = {"MMD": 999, "CORAL": 999}
                continue
            source_hi = normalize_to_tau(
                b_data["tau"].values * 100, b_data["HI"].values
            )  # 去归一化再归一化到统一网格
            mmd_val = compute_mmd(source_hi, g_target_att1)
            coral_val = compute_coral(source_hi, g_target_att1)
            mmd_results[bname] = {"MMD": float(mmd_val), "CORAL": float(coral_val)}
            print(f"  {bname}: MMD={mmd_val:.4f}, CORAL={coral_val:.8f}")

    # 选最小 MMD 的源轴承
    if mmd_results:
        best_source = min(mmd_results, key=lambda k: mmd_results[k]["MMD"])
        best_mmd = mmd_results[best_source]["MMD"]
    else:
        best_source = "Bearing3_1"
        best_mmd = 999.0

    transferable = best_mmd < MMD_THR
    print(f"\n  最佳源轴承: {best_source}, MMD={best_mmd:.4f}")
    print(f"  可迁移性: {'✓ 可迁移' if transferable else '✗ 不可迁移 (退化为 Q1 输出)'}")

    df_mmd = pd.DataFrame([
        {"bearing": b, "MMD": v["MMD"], "CORAL": v["CORAL"]}
        for b, v in mmd_results.items()
    ])
    save_result_table(df_mmd, "Q3_mmd_coral.csv")

    # ── L2: 形态对齐 ──
    print("\n" + "=" * 60)
    print("L2 形态对齐 (仿射映射)")
    print("=" * 60)

    a_hat, b_hat = 1.0, 0.0
    if df_hi_norm is not None and mmd_results:
        # 模型要求: 用候选轴承均值 ḡ_S(τ)，而非单个最佳轴承
        tau_grid = np.linspace(0, 1, 50)
        source_curves = []
        for bname in MIGRATION_SOURCE_BEARINGS:
            b_data = df_hi_norm[df_hi_norm["bearing"] == bname]
            if len(b_data) < 10:
                continue
            # 源轴承 HI 归一化到 τ 空间
            source_tau = b_data["tau"].values
            source_hi = b_data["HI"].values
            # τ 已在 [0,1]，重新插值到统一 50 点网格
            curve = np.interp(tau_grid, source_tau, source_hi)
            source_curves.append(curve)

        if source_curves:
            g_bar_S = np.mean(source_curves, axis=0)  # ḡ_S(τ) 候选轴承均值

            # 模型要求: 用附件1 前 1000 天（早期段）估计仿射参数
            t1 = att1["day"].values
            early_mask = t1 <= 1000.0
            if np.any(early_mask):
                # 目标域: 附件1 早期段 φ 曲线
                phi_early = (att1["current"].values[early_mask] - I_0) / DELTA_I_F
                t_early = t1[early_mask]
                tau_early = (t_early - t_early[0]) / (t_early[-1] - t_early[0])
                target_early = np.interp(tau_grid, tau_early, phi_early)

                a_hat, b_hat = estimate_affine(
                    tau_grid, g_bar_S,
                    tau_grid, target_early,
                )
            print(f"  使用 {len(source_curves)} 个源轴承均值 + 附件1 前1000天")
    print(f"  a = {a_hat:.4f}, b = {b_hat:.4f}")

    # ── 源域参数转换到 tau 空间 ──
    if q2_path.exists():
        df_theta = pd.read_csv(TABLES_DIR / "Q2_bearing_theta.csv")
        source_bearings = [b for b in MIGRATION_SOURCE_BEARINGS
                          if b in df_theta["bearing"].values]
        mu_source_tau_list = []
        sigma_sq_source_tau_list = []
        for bname in source_bearings:
            row = df_theta[df_theta["bearing"] == bname].iloc[0]
            t_eol = row["t_eol"]
            mu_source_tau = row["mu"] * t_eol
            sigma_sq_source_tau = row["sigma_sq"] * t_eol
            mu_source_tau_list.append(mu_source_tau)
            sigma_sq_source_tau_list.append(sigma_sq_source_tau)

        if mu_source_tau_list:
            mu_bar_s_tau = float(np.mean(mu_source_tau_list))
            sigma_sq_bar_s_tau = float(np.mean(sigma_sq_source_tau_list))
        else:
            mu_bar_s_tau = mu_local * T_att1_est
            sigma_sq_bar_s_tau = sigma_sq_local * T_att1_est
    else:
        mu_bar_s_tau = 0.0
        sigma_sq_bar_s_tau = 0.0

    # L2 转换: mu_T_L2 = a * mu_bar_S_tau + b
    mu_T_L2 = a_hat * mu_bar_s_tau + b_hat
    sigma_sq_T_L2 = a_hat ** 2 * sigma_sq_bar_s_tau

    print(f"  mu_S_bar(tau)={mu_bar_s_tau:.6f}, sigma²_S_bar(tau)={sigma_sq_bar_s_tau:.6f}")
    print(f"  mu_T_L2 = {mu_T_L2:.6f}")
    print(f"  sigma²_T_L2 = {sigma_sq_T_L2:.8f}")

    # ── 附件2 局部估计 (转 tau 空间) ──
    t2 = att2["day"].values
    i2 = att2["current"].values
    # 模型要求: T̂_EOL_T 来自 L2 外推 = Q1 模型 A 预测的飞轮全寿命
    theta_a_path = TABLES_DIR / "Q1_theta_A.csv"
    if theta_a_path.exists():
        df_theta_a = pd.read_csv(theta_a_path)
        alpha_a = df_theta_a["alpha"].values[0]
        beta_a = df_theta_a["beta"].values[0]
        T_att2_est = np.log(1.0 + DELTA_I_F / alpha_a) / beta_a if beta_a > 0 else 3000.0
    else:
        T_att2_est = 3500.0  # 回退到附件1 全寿命
    mu_local_tau = mu_local * T_att2_est
    sigma_sq_local_tau = sigma_sq_local * T_att2_est
    print(f"\n  目标域 T̂_EOL (模型A外推) = {T_att2_est:.0f} 天")
    print(f"  目标域(附件2) tau空间: mu_local_tau={mu_local_tau:.6f}, "
          f"sigma²_local_tau={sigma_sq_local_tau:.8f}")

    # ── L3: 加权融合 ──
    print("\n" + "=" * 60)
    print("L3 加权融合")
    print("=" * 60)

    lam = np.exp(-best_mmd ** 2 / H_BANDWIDTH) if transferable else 0.0
    print(f"  λ = exp(-MMD²/h) = {lam:.4f}")

    mu_TL_tau = lam * mu_T_L2 + (1 - lam) * mu_local_tau
    sigma_sq_TL_tau = lam * sigma_sq_T_L2 + (1 - lam) * sigma_sq_local_tau
    print(f"  mu_TL(tau) = {mu_TL_tau:.6f}")
    print(f"  sigma²_TL(tau) = {sigma_sq_TL_tau:.8f}")

    # 转换回天单位
    mu_TL_day = mu_TL_tau / T_att2_est
    sigma_sq_TL_day = sigma_sq_TL_tau / T_att2_est
    print(f"  mu_TL(day) = {mu_TL_day:.8f}")
    print(f"  sigma²_TL(day) = {sigma_sq_TL_day:.8f}")

    # ── 迁移后 RUL ──
    print("\n" + "=" * 60)
    print("迁移后 RUL 推断")
    print("=" * 60)

    X_F = np.log(max(I_F - I_0, EPS) + EPS)
    x_t = _to_X(np.array([i2[-1]]))[0]
    delta_x = X_F - x_t

    if delta_x <= 0 or mu_TL_day <= 0:
        print("  [WARN] 退化已达或超过失效阈值")
        rul_tl = 0.0
        ci_lo, ci_hi = 0.0, 0.0
        p30, p90, p180 = 1.0, 1.0, 1.0
    else:
        m_ig = delta_x / mu_TL_day
        lam_ig = delta_x ** 2 / sigma_sq_TL_day
        rul_tl = m_ig
        ci_lo = _ig_ppf(ALPHA_CI / 2, m_ig, lam_ig)
        ci_hi = _ig_ppf(1 - ALPHA_CI / 2, m_ig, lam_ig)

        def _p(days):
            return _ig_cdf(days, m_ig, lam_ig)
        p30, p90, p180 = _p(30), _p(90), _p(180)

    print(f"  RUL(TL) = {rul_tl:.1f} 天")
    print(f"  95% CI: [{ci_lo:.1f}, {ci_hi:.1f}]")
    print(f"  P(RUL<30)={p30:.4f}, P(RUL<90)={p90:.4f}, P(RUL<180)={p180:.4f}")

    # ── Q1 vs Q3 对比 ──
    print("\n" + "=" * 60)
    print("Q1 vs Q3 对比")
    print("=" * 60)

    rul_q1 = q1["RUL_B"]
    ci_q1_lo, ci_q1_hi = q1["RUL_CI"]
    ci_width_q1 = ci_q1_hi - ci_q1_lo
    ci_width_q3 = ci_hi - ci_lo

    print(f"  {'指标':<20} {'Q1 (无迁移)':<20} {'Q3 (有迁移)':<20}")
    print(f"  {'RUL 点估计':<20} {rul_q1:<20.1f} {rul_tl:<20.1f}")
    print(f"  {'95% CI 宽度':<20} {ci_width_q1:<20.1f} {ci_width_q3:<20.1f}")

    # PHM Score (在附件1 已知点上自评)
    # 选附件1 的几个中间时刻作为"假装当前"
    eval_times = [1000, 1500, 2000, 2500]
    if len(att1) > 0:
        t1_arr = att1["day"].values
        i1_arr = att1["current"].values
        T_eol_att1 = 3500.0
        deltas_q1 = []
        deltas_q3 = []
        for tc in eval_times:
            if tc >= t1_arr[-1]:
                break
            idx = np.searchsorted(t1_arr, tc)
            ic = i1_arr[idx]
            true_rul = T_eol_att1 - tc

            # Q1: 用 Q1 参数预测
            from data.constants import I_0 as I0
            xc = np.log(max(ic - I0, EPS) + EPS)
            dx = X_F - xc
            if dx > 0 and q1["theta_B_local"]["mu"] > 0:
                m_q1 = dx / q1["theta_B_local"]["mu"]
                pred_q1 = m_q1
            else:
                pred_q1 = 0.0
            deltas_q1.append(pred_q1 - true_rul)

            # Q3: 用迁移参数预测
            if dx > 0 and mu_TL_day > 0:
                m_q3 = dx / mu_TL_day
                pred_q3 = m_q3
            else:
                pred_q3 = 0.0
            deltas_q3.append(pred_q3 - true_rul)

        if deltas_q1:
            score_q1 = phm_score(np.array(deltas_q1))
            score_q3 = phm_score(np.array(deltas_q3))
            print(f"  {'PHM Score':<20} {score_q1:<20.4f} {score_q3:<20.4f}")

    # ── 预警等级 ──
    print("\n" + "=" * 60)
    print("预警等级")
    print("=" * 60)

    stage_q1 = q1["stage"]
    alert_level = determine_alert_level(stage_q1, p30, p90, p180)
    print(f"  当前阶段: {stage_q1}")
    print(f"  预警等级: {alert_level}")
    print(f"  建议措施: {ALERT_ACTIONS[alert_level]}")

    # ── 健康管理报告 ──
    print("\n" + "=" * 60)
    print("健康管理报告")
    print("=" * 60)

    report = f"""
╔══════════════════════════════════════════════════════════════╗
║              卫星飞轮健康管理报告                              ║
╠══════════════════════════════════════════════════════════════╣
║  监测时刻: 第 {int(t2[-1])} 天 (在轨)                         ║
║  当前电流: {i2[-1]:.4f} A                                      ║
║  健康阶段: {stage_q1}                                                ║
║  预警等级: {alert_level}                                                ║
╠══════════════════════════════════════════════════════════════╣
║  剩余寿命 (迁移后): {rul_tl:.1f} 天                            ║
║  95% 置信区间: [{ci_lo:.1f}, {ci_hi:.1f}] 天                   ║
║  P(RUL < 30天):  {p30:.2%}                                    ║
║  P(RUL < 90天):  {p90:.2%}                                    ║
║  P(RUL < 180天): {p180:.2%}                                    ║
╠══════════════════════════════════════════════════════════════╣
║  建议措施:                                                    ║
║  {ALERT_ACTIONS[alert_level]:<55s} ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(report)

    # ── 输出 ──
    df_rul = pd.DataFrame([{
        "t_current": int(t2[-1]),
        "RUL_TL_days": round(rul_tl, 1),
        "RUL_Q1_days": round(rul_q1, 1),
        "RUL_TL_CI_lo": round(ci_lo, 1),
        "RUL_TL_CI_hi": round(ci_hi, 1),
        "lambda": round(lam, 4),
        "MMD": round(best_mmd, 4),
        "transferable": transferable,
        "mu_TL_day": float(mu_TL_day),
        "sigma_sq_TL_day": float(sigma_sq_TL_day),
        "P_RUL_lt_30": round(p30, 4),
        "P_RUL_lt_90": round(p90, 4),
        "P_RUL_lt_180": round(p180, 4),
        "stage": stage_q1,
        "alert_level": alert_level,
    }])
    save_result_table(df_rul, "Q3_rul.csv")

    q3_summary = {
        "RUL_TL": float(rul_tl),
        "RUL_TL_CI": [float(ci_lo), float(ci_hi)],
        "RUL_Q1": float(rul_q1),
        "lambda": float(lam),
        "MMD": float(best_mmd),
        "transferable": transferable,
        "mu_TL": float(mu_TL_day),
        "sigma_sq_TL": float(sigma_sq_TL_day),
        "stage": stage_q1,
        "alert_level": alert_level,
        "probabilities": {
            "P_30": float(p30),
            "P_90": float(p90),
            "P_180": float(p180),
        },
        "action": ALERT_ACTIONS[alert_level],
    }
    with open(TABLES_DIR / "Q3_summary.json", "w", encoding="utf-8") as f:
        json.dump(q3_summary, f, indent=2, ensure_ascii=False)

    # 预警等级映射表
    df_alert = pd.DataFrame([
        {"level": k, "action": v} for k, v in ALERT_ACTIONS.items()
    ])
    save_result_table(df_alert, "Q3_alert_actions.csv")

    print("\n[Q3] 完成!")


if __name__ == "__main__":
    main()

