"""
EDA Step 4 — 상관관계 분석 (기상 제외)
  4-1) 전체 상관계수 히트맵
  4-2) SMP 상위 변수 pairplot (scatter matrix)
  4-3) SMP autocorrelation (ACF) — lag 선택 근거
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")
OUT  = BASE / "01.preprocessing" / "eda_output"
OUT.mkdir(exist_ok=True)

WEATHER = ["temp_c", "humidity_pct", "wind_speed_ms", "dew_point_c"]

df = pd.read_parquet(BASE / "00.collector/data/features/base_merged.parquet")
df["datetime"] = pd.to_datetime(df["datetime"])
df = df[(df["datetime"] >= "2023-01-01") & (df["datetime"] < "2026-01-01")].copy()
df = df.drop(columns=[c for c in WEATHER if c in df.columns])
df = df.set_index("datetime").sort_index()

# 분석 변수: gen_ratio + gen 절대값 중 ratio만 사용 (절대값은 ratio에 정보 포함)
# gen 5종 결측 있는 행은 상관 계산에서 pairwise dropna 처리됨
NUM_COLS = [
    "smp",
    "jlfd", "slfd", "mlfd",
    "gen_원자력_ratio", "gen_LNG_ratio", "gen_유연탄_ratio",
    "gen_무연탄_ratio", "gen_신재생·기타_ratio", "gen_수력_ratio",
    "gen_양수_ratio", "gen_유전_ratio",
    "fuel_cost_LNG", "fuel_cost_유연탄", "fuel_cost_유류",
    "smp_decision_cnt_LNG",
    "facility_capacity", "supply_capacity", "daily_max_demand",
    "supply_reserve_power", "supply_reserve_rate", "reserve_to_max_demand",
]
NUM_COLS = [c for c in NUM_COLS if c in df.columns]

corr = df[NUM_COLS].corr(method="pearson")

# ── 4-1. 전체 상관 히트맵 ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 12))
im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
plt.colorbar(im, ax=ax, shrink=0.8, label="Pearson r")

ax.set_xticks(range(len(NUM_COLS)))
ax.set_yticks(range(len(NUM_COLS)))
ax.set_xticklabels(NUM_COLS, rotation=45, ha="right", fontsize=8)
ax.set_yticklabels(NUM_COLS, fontsize=8)

# 셀 값 표시 (|r| >= 0.3 만)
for i in range(len(NUM_COLS)):
    for j in range(len(NUM_COLS)):
        val = corr.iloc[i, j]
        if abs(val) >= 0.3 and i != j:
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=6, color="white" if abs(val) > 0.6 else "black")

ax.set_title("변수 간 Pearson 상관계수 히트맵 (2023-2025, 기상 제외)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step4_corr_heatmap.png", dpi=150)
plt.close()
print("저장: step4_corr_heatmap.png")

# SMP 상관 요약 출력
smp_corr = corr["smp"].drop("smp").sort_values(key=abs, ascending=False)
print("\nSMP 상관계수 전체 (절대값 내림차순):")
for col, val in smp_corr.items():
    bar = "+" * int(abs(val) * 20) if val >= 0 else "-" * int(abs(val) * 20)
    print(f"  {col:<35}  {val:+.3f}  {bar}")

# fuel_cost_무연탄, 원자력 NaN 확인
print("\nfuel_cost 분산 확인:")
for c in ["fuel_cost_LNG","fuel_cost_유연탄","fuel_cost_무연탄","fuel_cost_유류","fuel_cost_원자력"]:
    if c in df.columns:
        n_unique = df[c].nunique()
        print(f"  {c:<30}: unique={n_unique}  mean={df[c].mean():.2f}  std={df[c].std():.4f}")

# ── 4-2. SMP 상관 상위 6 scatter ──────────────────────────────────────
top6 = smp_corr[smp_corr.index != "smp"].abs().nlargest(6).index.tolist()
print(f"\nScatter 대상 (SMP 상관 절대값 상위 6): {top6}")

fig, axes = plt.subplots(2, 3, figsize=(15, 9))
axes = axes.flatten()

for ax, col in zip(axes, top6):
    valid = df[[col, "smp"]].dropna()
    ax.scatter(valid[col], valid["smp"], s=1, alpha=0.15, color="#1f77b4")
    r = valid[col].corr(valid["smp"])
    ax.set_xlabel(col, fontsize=9)
    ax.set_ylabel("SMP")
    ax.set_title(f"r = {r:+.3f}", fontsize=10)
    # 추세선
    z = np.polyfit(valid[col].dropna(), valid["smp"].loc[valid[col].dropna().index], 1)
    p = np.poly1d(z)
    xr = np.linspace(valid[col].min(), valid[col].max(), 100)
    ax.plot(xr, p(xr), "r-", lw=1.5, alpha=0.8)

fig.suptitle("SMP vs 상관 상위 6 변수 (기상 제외)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step4_smp_scatter_top6.png", dpi=150)
plt.close()
print("저장: step4_smp_scatter_top6.png")

# ── 4-3. SMP ACF (autocorrelation) ───────────────────────────────────
smp = df["smp"].dropna()

# 직접 계산 (statsmodels 없어도 동작)
max_lag = 24 * 7 + 1   # 168시간 + 1
acf_vals = [smp.autocorr(lag=k) for k in range(0, max_lag + 1)]

fig, ax = plt.subplots(figsize=(14, 5))
lags = list(range(len(acf_vals)))
ax.bar(lags, acf_vals, color=["#d62728" if v > 0 else "#1f77b4" for v in acf_vals],
       width=0.8, alpha=0.8)
ax.axhline(0, color="black", lw=0.8)
# 95% 신뢰구간
ci = 1.96 / np.sqrt(len(smp))
ax.axhline(ci,  color="gray", lw=1, linestyle="--", label=f"95% CI (±{ci:.3f})")
ax.axhline(-ci, color="gray", lw=1, linestyle="--")

# 주요 lag 표시
key_lags = [1, 24, 48, 72, 168]
for k in key_lags:
    ax.axvline(k, color="orange", lw=1, linestyle=":", alpha=0.8)
    ax.text(k, max(acf_vals) * 0.95, f"lag{k}", fontsize=8, ha="center", color="darkorange")

ax.set_xlabel("Lag (시간)")
ax.set_ylabel("Autocorrelation")
ax.set_title("SMP Autocorrelation (ACF, lag 0~168)", fontsize=12, fontweight="bold")
ax.set_xlim(-1, max_lag + 1)
ax.legend(fontsize=9)
ax.xaxis.set_major_locator(mticker.MultipleLocator(24))
plt.tight_layout()
fig.savefig(OUT / "step4_smp_acf.png", dpi=150)
plt.close()
print("저장: step4_smp_acf.png")

# 주요 lag 값 출력
print("\nSMP ACF 주요 lag 값:")
for k in [1, 2, 3, 6, 12, 24, 48, 72, 96, 120, 144, 168]:
    if k < len(acf_vals):
        print(f"  lag {k:3d}h  ({k//24}일 {k%24:02d}h):  {acf_vals[k]:+.4f}")

print("\n" + "="*60)
print("Step 4 주요 인사이트")
print("="*60)
print(f"  SMP 상관 1위: {smp_corr.index[0]} (r={smp_corr.iloc[0]:+.3f})")
print(f"  SMP 상관 2위: {smp_corr.index[1]} (r={smp_corr.iloc[1]:+.3f})")
print(f"  SMP lag1 ACF:   {acf_vals[1]:+.4f}  → 직전 시간 SMP 강한 persistence")
print(f"  SMP lag24 ACF:  {acf_vals[24]:+.4f}  → 같은 시간대 전일 SMP 상관")
print(f"  SMP lag168 ACF: {acf_vals[168]:+.4f}  → 전주 동일 시간 SMP 상관")
