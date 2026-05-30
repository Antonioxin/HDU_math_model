"""敏感性分析批量入口。

按 model/敏感性分析设计.md 中的扫描点逐项运行，结果写入 code/results/tables/。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "code" / "src"
sys.path.insert(0, str(SRC))

from data.constants import (
    I_0, I_F, DELTA_I_F, THETA_H, THETA_F,
    ALPHA_0, BETA_0, ALPHA_CI,
    W1, W2, W3, N_TOP, W_SMOOTH,
    HI_ALARM_K, HI_F, P_HEALTHY, BETA_PEN,
    H_BANDWIDTH, MMD_THR, CORAL_THR, S_MAX,
    P_THR_180, P_THR_180_UP, P_THR_90, P_THR_30,
    SENS_RANGES,
)
from data.load_tables import load_processed, save_result_table

RESULTS_DIR = ROOT / "code" / "results"
TABLES_DIR = RESULTS_DIR / "tables"

# 重用 Q1 核心逻辑
from q1.run_q1 import (
    _exp_model, fit_model_a, predict_rul_model_a,
    fit_wiener_lambda, predict_rul_lambda_wiener,
    classify_stage_threshold, _ig_ppf,
)


def run_q1_sens_I_F() -> pd.DataFrame:
    """Q1-S1: 失效阈值 i_F 扫描."""
    print("\n[Q1-S1] 失效阈值扫描...")
    att1 = load_processed("att1_processed.csv")
    att2 = load_processed("att2_processed.csv")
    t2 = att2["day"].values
    i2 = att2["current"].values

    # 用附件1 拟合模型 A (全寿命形状)
    res_a = fit_model_a(att1["day"].values, att1["current"].values)

    rows = []
    for if_val in SENS_RANGES["I_F"]:
        # 临时覆写 I_F
        global I_F, DELTA_I_F
        orig_IF, orig_DIF = I_F, DELTA_I_F
        I_F = if_val
        DELTA_I_F = I_F - I_0

        rul = predict_rul_lambda_wiener(
            t2[-1], i2[-1], res_a["alpha"], res_a["beta"], 1e-10
        )
        # 注意: sigma_B2 用 1e-10 (理论值), 只考察 i_F 影响
        delta_if = I_F - I_0
        phi_last = (i2[-1] - I_0) / delta_if if delta_if > 0 else 999
        stage = classify_stage_threshold(phi_last)

        rows.append({
            "param": "I_F", "value": if_val,
            "RUL": round(rul["RUL"], 1),
            "CI_lo": round(rul["CI_lo"], 1),
            "CI_hi": round(rul["CI_hi"], 1),
            "CI_width": round(rul["CI_hi"] - rul["CI_lo"], 1),
            "stage": stage,
        })

        I_F, DELTA_I_F = orig_IF, orig_DIF

    df = pd.DataFrame(rows)
    save_result_table(df, "Q1_sens_I_F.csv")
    return df


def run_q1_sens_theta() -> pd.DataFrame:
    """Q1-S2: 阶段切分阈值扫描."""
    print("\n[Q1-S2] 阶段阈值扫描...")
    att2 = load_processed("att2_processed.csv")
    rows = []
    for th, tf in SENS_RANGES["THETA_GROUPS"]:
        phi_last = att2["phi"].values[-1]
        if phi_last < th:
            stage = "H"
        elif phi_last < tf:
            stage = "D"
        else:
            stage = "F"

        n_h = (att2["phi"] < th).sum()
        n_d = ((att2["phi"] >= th) & (att2["phi"] < tf)).sum()
        n_f = (att2["phi"] >= tf).sum()
        rows.append({
            "param": "theta",
            "theta_H": th, "theta_F": tf,
            "stage": stage,
            "n_H": n_h, "n_D": n_d, "n_F": n_f,
        })
    df = pd.DataFrame(rows)
    save_result_table(df, "Q1_sens_theta.csv")
    return df


def run_q1_sens_wiener_window() -> pd.DataFrame:
    """Q1-S3: Wiener 拟合窗口扫描."""
    print("\n[Q1-S3] Wiener 拟合窗口扫描...")
    att1 = load_processed("att1_processed.csv")
    att2 = load_processed("att2_processed.csv")
    t2 = att2["day"].values
    i2 = att2["current"].values
    res_a = fit_model_a(att1["day"].values, att1["current"].values)
    n = len(t2)

    rows = []
    for ratio in SENS_RANGES["WIENER_WINDOW"]:
        n_use = max(10, int(n * ratio))
        sub_t = t2[:n_use]
        sub_i = i2[:n_use]
        res_b = fit_wiener_lambda(sub_t, sub_i, res_a["alpha"], res_a["beta"])
        rul = predict_rul_lambda_wiener(
            sub_t[-1], sub_i[-1], res_a["alpha"], res_a["beta"], res_b["sigma_B2"]
        )
        rows.append({
            "param": "wiener_window",
            "ratio": ratio,
            "n_points": n_use,
            "sigma_B2": res_b["sigma_B2"],
            "RUL": round(rul["RUL"], 1),
            "CI_width": round(rul["CI_hi"] - rul["CI_lo"], 1),
        })
    df = pd.DataFrame(rows)
    save_result_table(df, "Q1_sens_wiener_window.csv")
    return df


def run_q1_sens_sigma_B() -> pd.DataFrame:
    """Q1-S6: σ_B 缩放扫描 (替换旧 ε 扫描)."""
    print("\n[Q1-S6] σ_B 缩放扫描...")
    att1 = load_processed("att1_processed.csv")
    att2 = load_processed("att2_processed.csv")
    t2 = att2["day"].values
    i2 = att2["current"].values
    res_a = fit_model_a(att1["day"].values, att1["current"].values)
    res_b = fit_wiener_lambda(t2, i2, res_a["alpha"], res_a["beta"])
    base_sigma = res_b["sigma_B2"]

    rows = []
    for scale in SENS_RANGES["SIGMA_B_SCALE"]:
        sigma_scaled = base_sigma * scale
        rul = predict_rul_lambda_wiener(
            t2[-1], i2[-1], res_a["alpha"], res_a["beta"], sigma_scaled
        )
        rows.append({
            "param": "sigma_B_scale", "scale": scale,
            "sigma_B2": sigma_scaled,
            "RUL": round(rul["RUL"], 1),
            "CI_width": round(rul["CI_hi"] - rul["CI_lo"], 1),
        })
    df = pd.DataFrame(rows)
    save_result_table(df, "Q1_sens_sigma_B.csv")
    return df


def run_q1_sens_beta0() -> pd.DataFrame:
    """Q1-S4: β 初值扫描."""
    print("\n[Q1-S4] β 初值扫描...")
    att1 = load_processed("att1_processed.csv")
    t1 = att1["day"].values
    i1 = att1["current"].values

    rows = []
    for b0 in SENS_RANGES["BETA_0"]:
        from scipy.optimize import curve_fit
        p0 = [ALPHA_0, b0]
        bounds = ([1e-8, 1e-8], [np.inf, np.inf])
        try:
            popt, _ = curve_fit(_exp_model, t1, i1, p0=p0, bounds=bounds,
                                method="trf", maxfev=10000)
            alpha_h, beta_h = popt
            rmse = np.sqrt(np.mean((i1 - _exp_model(t1, alpha_h, beta_h)) ** 2))
        except Exception:
            alpha_h, beta_h, rmse = np.nan, np.nan, np.nan
        rows.append({
            "param": "beta0", "beta0": b0,
            "alpha_hat": alpha_h, "beta_hat": beta_h, "rmse": rmse,
        })
    df = pd.DataFrame(rows)
    save_result_table(df, "Q1_sens_beta0.csv")
    return df


def run_q1_sens_eps() -> pd.DataFrame:
    """Q1-S6: ε 偏置扫描."""
    print("\n[Q1-S6] ε 偏置扫描...")
    att2 = load_processed("att2_processed.csv")
    t2 = att2["day"].values
    i2 = att2["current"].values

    rows = []
    for ep in SENS_RANGES["EPS"]:
        X = np.log(np.maximum(i2 - I_0, 0.0) + ep)
        dt = np.diff(t2)
        dX = np.diff(X)
        T_total = t2[-1] - t2[0]
        mu_h = (X[-1] - X[0]) / T_total if T_total > 0 else 0.0
        sigma_h = np.mean((dX - mu_h * dt) ** 2 / dt)
        rows.append({
            "param": "eps", "eps": ep,
            "mu": mu_h, "sigma_sq": sigma_h,
        })
    df = pd.DataFrame(rows)
    save_result_table(df, "Q1_sens_eps.csv")
    return df


def run_q1_sens_wsmooth() -> pd.DataFrame:
    """Q1-S5: 平滑窗口扫描 (在附件2上计算 Mon)."""
    print("\n[Q1-S5] 平滑窗口扫描...")
    att2 = load_processed("att2_processed.csv")
    delta_i = att2["delta_i_cum"].values
    n = len(delta_i)
    rows = []
    for w in SENS_RANGES["W_SMOOTH"]:
        smoothed = pd.Series(delta_i).rolling(window=min(w, n),
                                              min_periods=1, center=True).mean().values
        diff = np.diff(smoothed)
        n_pos = np.sum(diff > 0)
        n_neg = np.sum(diff < 0)
        mon = abs(n_pos - n_neg) / max(1, len(diff))
        rows.append({"param": "W_smooth", "window": w, "Mon": mon})
    df = pd.DataFrame(rows)
    save_result_table(df, "Q1_sens_wsmooth.csv")
    return df


def run_q3_sens_bandwidth() -> pd.DataFrame:
    """Q3-S1: 迁移带宽 h 扫描."""
    print("\n[Q3-S1] 迁移带宽扫描...")
    q3_path = TABLES_DIR / "Q3_summary.json"
    if not q3_path.exists():
        print("  [SKIP] Q3 未运行")
        return pd.DataFrame()

    import json
    with open(q3_path, encoding="utf-8") as f:
        q3 = json.load(f)
    base_mmd = q3["MMD"]
    # 新格式: sigma_B2_TL, 旧格式回退
    base_sigma = q3.get("sigma_B2_TL", q3.get("sigma_sq_TL", 0.03))

    rows = []
    for h in SENS_RANGES["H_BANDWIDTH"]:
        lam = np.exp(-base_mmd ** 2 / h)
        rows.append({"param": "h", "h": h, "lambda": lam})
    df = pd.DataFrame(rows)
    save_result_table(df, "Q3_sens_h.csv")
    return df


def run_q3_sens_mmd_thr() -> pd.DataFrame:
    """Q3-S2: MMD 硬阈值扫描."""
    print("\n[Q3-S2] MMD 阈值扫描...")
    q3_path = TABLES_DIR / "Q3_summary.json"
    if not q3_path.exists():
        print("  [SKIP] Q3 未运行")
        return pd.DataFrame()

    import json
    with open(q3_path, encoding="utf-8") as f:
        q3 = json.load(f)
    base_mmd = q3["MMD"]

    rows = []
    for thr in SENS_RANGES["MMD_THR"]:
        transferable = base_mmd < thr
        rows.append({
            "param": "MMD_thr", "threshold": thr,
            "MMD": base_mmd, "transferable": transferable,
        })
    df = pd.DataFrame(rows)
    save_result_table(df, "Q3_sens_mmd_thr.csv")
    return df


def run_q3_sens_warning() -> pd.DataFrame:
    """Q3-S3: 预警阈值组扫描."""
    print("\n[Q3-S3] 预警阈值扫描...")
    q3_path = TABLES_DIR / "Q3_summary.json"
    if not q3_path.exists():
        print("  [SKIP] Q3 未运行")
        return pd.DataFrame()

    import json
    with open(q3_path, encoding="utf-8") as f:
        q3 = json.load(f)

    base_p = q3["probabilities"]
    p30, p90, p180_base = base_p["P_30"], base_p["P_90"], base_p["P_180"]
    stage = q3["stage"]

    rows = []
    # 三组: 宽松, 基线, 严格
    configs = [
        ("宽松", 0.5 * P_THR_180, 0.5 * P_THR_180_UP, 0.5 * P_THR_90, 0.5 * P_THR_30),
        ("基线", P_THR_180, P_THR_180_UP, P_THR_90, P_THR_30),
        ("严格", 1.5 * P_THR_180, 1.5 * P_THR_180_UP, 1.5 * P_THR_90, 1.5 * P_THR_30),
    ]
    for label, p180, p180up, p90t, p30t in configs:
        # 直接内联四级预警判定
        if stage == "F" or p30 >= p30t:
            level = "L3"
        elif stage == "D" and (p180_base >= p180up or p90 >= p90t):
            level = "L2"
        elif p180_base >= p180:
            level = "L1"
        else:
            level = "L0"
        rows.append({"param": "warning", "config": label, "level": level})
    df = pd.DataFrame(rows)
    save_result_table(df, "Q3_sens_warning.csv")
    return df


def run_q3_sens_iF() -> pd.DataFrame:
    """Q3-S6: 失效阈值映射联动 Q1-S1。"""
    print("\n[Q3-S6] 失效阈值联动扫描...")

    q1_sens_path = TABLES_DIR / "Q1_sens_I_F.csv"
    q3_path = TABLES_DIR / "Q3_summary.json"
    if not q1_sens_path.exists():
        print("  [SKIP] Q1_sens_I_F.csv 不存在")
        return pd.DataFrame()
    if not q3_path.exists():
        print("  [SKIP] Q3_summary.json 不存在")
        return pd.DataFrame()

    import json
    with open(q3_path, encoding="utf-8") as f:
        q3 = json.load(f)

    # 新格式: alpha, beta, sigma_B2; 旧格式回退
    theta_b = q3.get("theta_B_local", {})
    alpha = theta_b.get("alpha", 0.598)
    beta = theta_b.get("beta", 0.000358)
    sigma_B2 = theta_b.get("sigma_B2", 1e-10)

    att2 = load_processed("att2_processed.csv")
    i_current = att2["current"].values[-1]
    t_current = att2["day"].values[-1]

    df_q1 = pd.read_csv(q1_sens_path)
    iF_values = df_q1["value"].values

    rows = []
    for if_val in iF_values:
        rul = predict_rul_lambda_wiener(
            t_current, i_current, alpha, beta, sigma_B2
        )
        rows.append({
            "param": "I_F",
            "value": if_val,
            "RUL_TL": round(rul["RUL"], 1),
            "CI_lo_TL": round(rul["CI_lo"], 1),
            "CI_hi_TL": round(rul["CI_hi"], 1),
            "CI_width_TL": round(rul["CI_hi"] - rul["CI_lo"], 1),
        })

    df = pd.DataFrame(rows)
    save_result_table(df, "Q3_sens_I_F.csv")
    return df


def main() -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("敏感性分析")
    print("=" * 60)

    all_dfs = {}

    # Q1 敏感性
    all_dfs["Q1_sens_I_F"] = run_q1_sens_I_F()
    all_dfs["Q1_sens_theta"] = run_q1_sens_theta()
    all_dfs["Q1_sens_wiener_window"] = run_q1_sens_wiener_window()
    all_dfs["Q1_sens_beta0"] = run_q1_sens_beta0()
    all_dfs["Q1_sens_sigma_B"] = run_q1_sens_sigma_B()
    all_dfs["Q1_sens_wsmooth"] = run_q1_sens_wsmooth()

    # Q3 敏感性
    all_dfs["Q3_sens_h"] = run_q3_sens_bandwidth()
    all_dfs["Q3_sens_mmd_thr"] = run_q3_sens_mmd_thr()
    all_dfs["Q3_sens_warning"] = run_q3_sens_warning()
    all_dfs["Q3_sens_I_F"] = run_q3_sens_iF()  # Q3-S6 联动 Q1-S1

    # 综合汇总
    print("\n" + "=" * 60)
    print("生成综合汇总表")
    summary_rows = []

    for key, df in all_dfs.items():
        if df.empty:
            continue
        # 计算弹性或变化幅度
        for _, row in df.iterrows():
            summary_rows.append({
                "analysis": key,
                "param_name": row.get("param", ""),
                "param_value": str(row.iloc[1]) if len(row) > 1 else "",
                "metric": "see_csv",
                "metric_change": "see_csv",
            })

    if summary_rows:
        df_summary = pd.DataFrame(summary_rows)
        save_result_table(df_summary, "敏感性分析.csv")

    print("\n[敏感性分析] 完成!")


if __name__ == "__main__":
    main()

