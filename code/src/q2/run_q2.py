"""Q2 求解入口：轴承振动特征提取与退化建模。

实现:
  - 11 项振动特征提取 (5时域 + 3频域 + 3时频)
  - Mon/Trd/Rob 综合评分 -> Top-N 特征选择
  - PCA-PC1 -> HI 构建
  - Wiener 退化建模 + 指数退化对比
  - 阶段划分 (3sigma 报警 + PELT 双判据)
  - 迁移源轴承筛选
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal
from scipy.optimize import curve_fit
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "code" / "src"
sys.path.insert(0, str(SRC))

from data.constants import (
    F_S_VIB, L_REC, DT_VIB,
    W1, W2, W3, N_TOP, W_SMOOTH,
    HI_ALARM_K, HI_F, P_HEALTHY, BETA_PEN,
    BEARINGS_OUTER, MIGRATION_SOURCE_BEARINGS,
)
from data.load_tables import (
    XJTU_RAW, list_xjtu_bearing_files, load_xjtu_bearing, save_result_table,
)

RESULTS_DIR = ROOT / "code" / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"

FEATURE_NAMES = [
    "RMS", "Kurtosis", "CrestFactor", "Skewness", "PeakToPeak",
    "MaxFreqAmp", "HighFreqRatio", "SpectralEntropy",
    "WaveletEnergyRatio", "HHTMeanIF", "EMD_IMF13_Ratio",
]


# ============================================================
# 1. 特征提取
# ============================================================

def extract_time_domain(x: np.ndarray) -> dict:
    rms = np.sqrt(np.mean(x ** 2))
    sigma = np.std(x)
    if sigma < 1e-12:
        return {"RMS": rms, "Kurtosis": 0.0, "CrestFactor": 0.0,
                "Skewness": 0.0, "PeakToPeak": 0.0}
    return {
        "RMS": rms,
        "Kurtosis": float(np.mean(((x - np.mean(x)) / sigma) ** 4)),
        "CrestFactor": float(np.max(np.abs(x)) / rms) if rms > 0 else 0.0,
        "Skewness": float(np.mean(((x - np.mean(x)) / sigma) ** 3)),
        "PeakToPeak": float(np.max(x) - np.min(x)),
    }


def extract_freq_domain(x: np.ndarray, fs: float = F_S_VIB,
                        nperseg: int = 2048) -> dict:
    f, Pxx = signal.welch(x, fs=fs, nperseg=nperseg)
    total_energy = np.sum(Pxx)
    if total_energy < 1e-15:
        return {"MaxFreqAmp": 0.0, "HighFreqRatio": 0.0, "SpectralEntropy": 0.0}
    high_mask = (f >= 8000) & (f <= fs / 2)
    high_energy = np.sum(Pxx[high_mask])
    p = Pxx / total_energy
    p = p[p > 0]
    spec_entropy = -np.sum(p * np.log(p))
    return {
        "MaxFreqAmp": float(np.max(Pxx)),
        "HighFreqRatio": float(high_energy / total_energy),
        "SpectralEntropy": float(spec_entropy),
    }


def extract_time_freq_domain(x: np.ndarray, fs: float = F_S_VIB) -> dict:
    result = {"WaveletEnergyRatio": np.nan, "HHTMeanIF": np.nan,
              "EMD_IMF13_Ratio": np.nan}
    try:
        import pywt
        wp = pywt.WaveletPacket(data=x, wavelet="db4", mode="symmetric", maxlevel=4)
        nodes = wp.get_level(4, order="natural")
        energies = [np.sum(n.data ** 2) for n in nodes]
        total = sum(energies)
        if total > 0:
            result["WaveletEnergyRatio"] = float(energies[-1] / total)
    except ImportError:
        pass
    try:
        from PyEMD import EMD
        from scipy.signal import hilbert
        emd = EMD()
        imfs = emd(x, max_imf=3)
        if imfs is not None and len(imfs) > 0:
            imf_energies = [np.sum(imf ** 2) for imf in imfs]
            sig_energy = np.sum(x ** 2)
            if sig_energy > 0:
                n_imf = min(3, len(imf_energies))
                result["EMD_IMF13_Ratio"] = float(sum(imf_energies[:n_imf]) / sig_energy)
            main_imf = imfs[0]
            analytic = hilbert(main_imf)
            inst_phase = np.unwrap(np.angle(analytic))
            inst_freq = np.diff(inst_phase) * fs / (2 * np.pi)
            if len(inst_freq) > 0:
                result["HHTMeanIF"] = float(np.mean(np.abs(inst_freq)))
    except ImportError:
        pass
    return result


def extract_features_single(x: np.ndarray) -> dict:
    features = {}
    features.update(extract_time_domain(x))
    features.update(extract_freq_domain(x))
    features.update(extract_time_freq_domain(x))
    return features


def extract_bearing_features(bearing_name: str,
                             file_indices: list[int]) -> pd.DataFrame:
    rows = []
    n_total = len(file_indices)
    for i, idx in enumerate(file_indices):
        if i % max(1, n_total // 10) == 0:
            print(f"    [{i+1}/{n_total}] ...")
        try:
            df = load_xjtu_bearing(bearing_name, idx)
        except Exception:
            continue
        feats_h = extract_features_single(df["Horizontal"].values)
        feats_v = extract_features_single(df["Vertical"].values)
        row = {"file_idx": idx, "t_min": (idx - 1) * DT_VIB / 60.0}
        for fname in FEATURE_NAMES:
            vals = []
            if not np.isnan(feats_h.get(fname, np.nan)):
                vals.append(feats_h[fname])
            if not np.isnan(feats_v.get(fname, np.nan)):
                vals.append(feats_v[fname])
            row[fname] = float(np.mean(vals)) if vals else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("file_idx").reset_index(drop=True)


# ============================================================
# 2. 特征评价
# ============================================================

def compute_monotonicity(values: np.ndarray) -> float:
    valid = values[~np.isnan(values)]
    if len(valid) < 2:
        return 0.0
    diff = np.diff(valid)
    n_pos, n_neg = np.sum(diff > 0), np.sum(diff < 0)
    denom = len(diff)
    return abs(n_pos - n_neg) / denom if denom > 0 else 0.0


def compute_trend(values: np.ndarray) -> float:
    valid = values[~np.isnan(values)]
    if len(valid) < 3:
        return 0.0
    rho, _ = spearmanr(np.arange(len(valid)), valid)
    return abs(rho) if not np.isnan(rho) else 0.0


def compute_robustness(values: np.ndarray, window: int = W_SMOOTH) -> float:
    valid = values[~np.isnan(values)]
    K = len(valid)
    if K < 2:
        return 0.0
    smoothed = (pd.Series(valid)
                .rolling(window=min(window, K), min_periods=1, center=True)
                .mean().values)
    delta = 1e-6
    ratios = np.exp(-np.abs(valid - smoothed) / (np.abs(valid) + delta))
    return float(np.mean(ratios))


def score_features(features_df: pd.DataFrame) -> dict:
    scores = {}
    for fname in FEATURE_NAMES:
        if fname not in features_df.columns:
            continue
        vals = features_df[fname].values
        scores[fname] = {
            "Mon": compute_monotonicity(vals),
            "Trd": compute_trend(vals),
            "Rob": compute_robustness(vals),
        }
        scores[fname]["S_F"] = (W1 * scores[fname]["Mon"] +
                                W2 * scores[fname]["Trd"] +
                                W3 * scores[fname]["Rob"])
    return scores


def select_top_features(all_scores: dict, n_top: int = N_TOP) -> list:
    avg_scores = {}
    for fname in FEATURE_NAMES:
        vals = [all_scores[b][fname]["S_F"] for b in all_scores
                if fname in all_scores[b]
                and not np.isnan(all_scores[b][fname]["S_F"])]
        if vals:
            avg_scores[fname] = float(np.mean(vals))
    sorted_f = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)
    return [f for f, _ in sorted_f[:n_top]]


# ============================================================
# 3. HI 构建
# ============================================================

def build_hi(features_df: pd.DataFrame, top_features: list) -> np.ndarray:
    from sklearn.decomposition import PCA
    available = [f for f in top_features if f in features_df.columns]
    if len(available) < 2:
        hi_raw = features_df[available[0]].values.astype(float)
    else:
        X = features_df[available].values.astype(float)
        X = pd.DataFrame(X).ffill().bfill().values
        pca = PCA(n_components=1)
        pc1 = pca.fit_transform(X).ravel()
        rho, _ = spearmanr(np.arange(len(pc1)), pc1)
        if rho < 0:
            pc1 = -pc1
        hi_raw = pc1
    hi_min, hi_max = np.nanmin(hi_raw), np.nanmax(hi_raw)
    if hi_max - hi_min < 1e-12:
        return np.zeros_like(hi_raw)
    return (hi_raw - hi_min) / (hi_max - hi_min)


# ============================================================
# 4. 退化建模 (在 HI 上)
# ============================================================

def fit_wiener_on_hi(t: np.ndarray, hi: np.ndarray) -> dict:
    dt = np.diff(t)
    dHI = np.diff(hi)
    T_total = t[-1] - t[0]
    mu = (hi[-1] - hi[0]) / T_total if T_total > 0 else 0.0
    sigma_sq = (np.mean((dHI - mu * dt) ** 2 / dt)
                if len(dt) > 0 else 0.0)
    hi_pred = hi[0] + mu * (t - t[0])
    rmse = np.sqrt(np.mean((hi - hi_pred) ** 2))
    ss_tot = np.sum((hi - np.mean(hi)) ** 2)
    r2 = 1 - np.sum((hi - hi_pred) ** 2) / ss_tot if ss_tot > 0 else 0
    return {"mu": mu, "sigma_sq": sigma_sq, "rmse": rmse, "r2": r2}


def fit_exponential_on_hi(t: np.ndarray, hi: np.ndarray) -> dict:
    def _model(t_, a_, b_):
        return hi[0] + a_ * (np.exp(b_ * t_) - 1.0)
    try:
        popt, _ = curve_fit(
            _model, t - t[0], hi,
            p0=[0.01, 1e-3], bounds=([1e-8, 1e-8], [10, 1]), maxfev=5000,
        )
        hi_pred = _model(t - t[0], *popt)
        rmse = np.sqrt(np.mean((hi - hi_pred) ** 2))
        return {"a": popt[0], "b": popt[1], "rmse": rmse}
    except Exception:
        return {"a": np.nan, "b": np.nan, "rmse": np.nan}


# ============================================================
# 5. 阶段划分
# ============================================================

def classify_stage_3sigma(hi: np.ndarray, p_healthy: float = P_HEALTHY,
                          k: float = HI_ALARM_K) -> list:
    """稳健化报警: median + k·1.4826·MAD 替代 mean + k·σ."""
    n = len(hi)
    n_healthy = max(1, int(n * p_healthy))
    h_healthy = hi[:n_healthy]
    h_median = np.median(h_healthy)
    h_mad = np.median(np.abs(h_healthy - h_median))
    threshold = h_median + k * 1.4826 * h_mad  # MAD→σ 一致估计

    fail_idx = n
    for i in range(n):
        if hi[i] >= HI_F:
            fail_idx = i
            break
    alarm_idx = n
    for i in range(n):
        if hi[i] > threshold:
            alarm_idx = i
            break

    stages = []
    for i in range(n):
        if i < alarm_idx:
            stages.append("H")
        elif i < fail_idx:
            stages.append("D")
        else:
            stages.append("F")
    return stages


def classify_stage_pelt(values: np.ndarray, pen: float | None = None) -> list | None:
    """自适应 PELT: pen = BETA_PEN * var(residual) * ln(K)."""
    try:
        from ruptures import Pelt
        if pen is None:
            smooth = pd.Series(values).rolling(
                window=min(10, len(values)), min_periods=1, center=True).mean().values
            resid_var = np.var(values - smooth) if len(values) > 1 else 1.0
            pen = BETA_PEN * resid_var * np.log(len(values))
        model = Pelt(model="rbf").fit(values.reshape(-1, 1))
        cps = model.predict(pen=pen)
        n = len(values)
        stages = ["H"] * n
        if len(cps) >= 2:
            for i in range(cps[0], n):
                stages[i] = "D"
        if len(cps) >= 3:
            for i in range(cps[1], n):
                stages[i] = "F"
        return stages
    except ImportError:
        return None


def classify_combined(hi: np.ndarray) -> list:
    s_3s = classify_stage_3sigma(hi)
    s_pelt = classify_stage_pelt(hi)
    if s_pelt is None:
        return s_3s
    order = {"H": 0, "D": 1, "F": 2}
    return [s1 if order[s1] >= order[s2] else s2
            for s1, s2 in zip(s_3s, s_pelt)]


# ============================================================
# 主流程
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true",
                        help="仅处理迁移源轴承 (3个)")
    args = parser.parse_args()

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Q2: 轴承振动特征提取与退化建模")
    print("=" * 60)

    if not XJTU_RAW.exists():
        print(f"\n[WARN] XJTU-SY 数据目录不存在: {XJTU_RAW}")
        print("请将 XJTU-SY 轴承数据集放入该目录。")
        print("目录结构: problem/数据/XJTU-SY/Bearing1_1/1.csv, ...")
        pd.DataFrame({"info": ["XJTU-SY数据未找到"]}).to_csv(
            TABLES_DIR / "Q2_placeholder.csv", index=False)
        return

    bearings_to_process = (MIGRATION_SOURCE_BEARINGS if args.quick
                           else BEARINGS_OUTER)
    print(f"\n处理轴承: {bearings_to_process}")

    all_features = {}
    all_scores = {}
    all_hi = {}

    for bname in bearings_to_process:
        print(f"\n--- {bname} ---")
        try:
            files = list_xjtu_bearing_files(bname)
            print(f"  振动文件数: {len(files)}")
        except FileNotFoundError as e:
            print(f"  [SKIP] {e}")
            continue
        if len(files) == 0:
            print(f"  [SKIP] 无振动文件")
            continue
        print(f"  提取 11 项特征...")
        feat_df = extract_bearing_features(bname, files)
        all_features[bname] = feat_df
        scores = score_features(feat_df)
        all_scores[bname] = scores
        top3 = sorted(scores.items(), key=lambda x: x[1]["S_F"], reverse=True)[:3]
        print(f"  Top-3: {[(f, round(s['S_F'],3)) for f,s in top3]}")

    if not all_features:
        print("\n[WARN] 无轴承数据可处理")
        return

    # 全局 Top-N 特征选择
    print("\n" + "=" * 60)
    print("全局特征选择")
    top_features = select_top_features(all_scores, N_TOP)
    print(f"  Top-{N_TOP}: {top_features}")

    df_top = pd.DataFrame([{
        "Feature": f,
        "Avg_S_F": float(np.mean([
            all_scores[b][f]["S_F"] for b in all_scores
            if f in all_scores[b]
        ]))
    } for f in top_features])
    save_result_table(df_top, "Q2_top_features.csv")
    with open(TABLES_DIR / "Q2_top_features.json", "w") as f:
        json.dump(top_features, f, ensure_ascii=False)

    # HI + 退化建模
    print("\n" + "=" * 60)
    print("HI 构建与退化建模")
    bearing_results = []

    for bname in all_features:
        feat_df = all_features[bname]
        t_min = feat_df["t_min"].values
        hi = build_hi(feat_df, top_features)
        all_hi[bname] = {"t": t_min, "HI": hi}

        w_res = fit_wiener_on_hi(t_min, hi)
        e_res = fit_exponential_on_hi(t_min, hi)
        stages = classify_combined(hi)

        print(f"  {bname}: mu={w_res['mu']:.6f}, sigma2={w_res['sigma_sq']:.6f}, "
              f"RMSE={w_res['rmse']:.4f}, stage={stages[-1]}")

        bearing_results.append({
            "bearing": bname,
            "mu": w_res["mu"], "sigma_sq": w_res["sigma_sq"],
            "wiener_rmse": w_res["rmse"], "wiener_r2": w_res["r2"],
            "exp_a": e_res["a"], "exp_b": e_res["b"],
            "exp_rmse": e_res["rmse"],
            "final_stage": stages[-1],
            "t_eol": float(t_min[-1]),
        })

        hi_df = pd.DataFrame({
            "t_min": t_min, "HI": hi, "stage": stages,
        })
        hi_df.to_csv(TABLES_DIR / f"Q2_HI_{bname}.csv", index=False)

    df_params = pd.DataFrame(bearing_results)
    save_result_table(df_params, "Q2_bearing_theta.csv")

    # 归一化 HI (tau 空间)
    print("\n[归一化] tau in [0,1] HI 序列")
    norm_records = []
    for bname in all_hi:
        t = all_hi[bname]["t"]
        hi_vals = all_hi[bname]["HI"]
        tau = t / t[-1] if t[-1] > 0 else t
        for ti, hii in zip(tau, hi_vals):
            norm_records.append({"bearing": bname, "tau": ti, "HI": hii})
    df_norm = pd.DataFrame(norm_records)
    save_result_table(df_norm, "Q2_HI_normalized.csv")

    q2_summary = {"top_features": top_features, "bearings": bearing_results}
    with open(TABLES_DIR / "Q2_summary.json", "w", encoding="utf-8") as f:
        json.dump(q2_summary, f, indent=2, ensure_ascii=False)

    print("\n[Q2] 完成!")


if __name__ == "__main__":
    main()
