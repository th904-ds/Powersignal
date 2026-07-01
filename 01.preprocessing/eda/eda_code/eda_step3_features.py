"""
EDA Step 3 — 입력 변수별 특성 (기상 제외)
  3-1) 수요예측 3종 (jlfd, slfd, mlfd)
  3-2) 발전원별 발전량 (gen_*)
  3-3) 연료비 (fuel_cost_*)
  3-4) 전력수급 (supply_*)
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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

# ══════════════════════════════════════════════════════════════════════
# 3-1. 수요예측 3종
# ══════════════════════════════════════════════════════════════════════
print("=== 3-1. 수요예측 3종 ===")
LOAD_COLS = ["jlfd", "slfd", "mlfd"]
LOAD_NAMES = {"jlfd": "전력거래소 단기예측(jlfd)",
              "slfd": "단기부하예측(slfd)",
              "mlfd": "중기부하예측(mlfd)"}

# 기초통계
print(df[LOAD_COLS].describe().round(1).to_string())

fig, axes = plt.subplots(3, 2, figsize=(16, 12))

for i, col in enumerate(LOAD_COLS):
    # 시계열
    ax = axes[i][0]
    ax.plot(df[col].index, df[col].values, lw=0.4, alpha=0.7, color=f"C{i}")
    ax.set_title(f"{LOAD_NAMES[col]} — 시계열", fontsize=10)
    ax.set_ylabel("MW")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1,4,7,10]))
    fig.autofmt_xdate(rotation=30)

    # SMP vs 수요예측 scatter
    ax2 = axes[i][1]
    valid = df[[col, "smp"]].dropna()
    ax2.scatter(valid[col], valid["smp"], s=1, alpha=0.2, color=f"C{i}")
    corr = valid[col].corr(valid["smp"])
    ax2.set_xlabel(col + " (MW)")
    ax2.set_ylabel("SMP (원/kWh)")
    ax2.set_title(f"{col} vs SMP  (r={corr:.3f})", fontsize=10)

fig.suptitle("수요예측 3종 분석", fontsize=13, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step3_1_load_forecast.png", dpi=150)
plt.close()
print("저장: step3_1_load_forecast.png")

# 3종 간 상관 및 SMP 상관
corrs = df[LOAD_COLS + ["smp"]].corr()
print("\n수요예측 3종 × SMP 상관:")
print(corrs["smp"].drop("smp").round(3).to_string())

# 예측 편차 (jlfd - slfd)
df["load_diff_jlfd_slfd"] = df["jlfd"] - df["slfd"]
df["load_diff_jlfd_mlfd"] = df["jlfd"] - df["mlfd"]
print(f"\njlfd - slfd 평균: {df['load_diff_jlfd_slfd'].mean():.1f} MW")
print(f"jlfd - mlfd 평균: {df['load_diff_jlfd_mlfd'].mean():.1f} MW")

# ══════════════════════════════════════════════════════════════════════
# 3-2. 발전원별 발전량
# ══════════════════════════════════════════════════════════════════════
print("\n=== 3-2. 발전원별 발전량 ===")

GEN_COLS = ["gen_원자력", "gen_LNG", "gen_유연탄", "gen_무연탄",
            "gen_신재생·기타", "gen_수력", "gen_양수", "gen_유전"]
GEN_RATIO = [c + "_ratio" for c in GEN_COLS]
COLORS_GEN = ["#377eb8","#e41a1c","#4daf4a","#984ea3",
              "#f781bf","#a65628","#999999","#ff7f00"]

# 발전량 합계 비중 (2023-2025 전체)
gen_sum = df[GEN_COLS].sum().sort_values(ascending=False)
print("\n발전원별 총발전량 비중:")
for col, val in gen_sum.items():
    pct = val / gen_sum.sum() * 100
    print(f"  {col:<18}: {val:,.0f}  ({pct:.1f}%)")

# 발전원 비중 파이차트 + 시계열
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# 파이차트
labels = [c.replace("gen_", "") for c in gen_sum.index]
axes[0].pie(gen_sum.values, labels=labels, colors=COLORS_GEN,
            autopct="%1.1f%%", startangle=90,
            pctdistance=0.8, labeldistance=1.05, textprops={"fontsize": 9})
axes[0].set_title("발전원별 총발전량 비중 (2023-2025)", fontsize=11, fontweight="bold")

# 월평균 비중 스택 영역
ratio_month = df[GEN_RATIO].resample("ME").mean()
ratio_month.columns = [c.replace("gen_", "").replace("_ratio","") for c in ratio_month.columns]
ratio_month.plot.area(ax=axes[1], stacked=True, color=COLORS_GEN, alpha=0.8, lw=0)
axes[1].set_ylabel("비중")
axes[1].set_xlabel("")
axes[1].set_title("월평균 발전원 비중 추이", fontsize=11, fontweight="bold")
axes[1].legend(loc="upper right", fontsize=8, ncol=2)
axes[1].set_ylim(0, 1)
axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))
fig.autofmt_xdate(rotation=30)

plt.tight_layout()
fig.savefig(OUT / "step3_2_gen_share.png", dpi=150)
plt.close()
print("저장: step3_2_gen_share.png")

# gen_LNG_ratio vs SMP
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
valid_lng = df[["gen_LNG_ratio", "gen_원자력_ratio", "smp"]].dropna()
axes[0].scatter(valid_lng["gen_LNG_ratio"], valid_lng["smp"],
                s=1, alpha=0.2, color="#e41a1c")
c_lng = valid_lng["gen_LNG_ratio"].corr(valid_lng["smp"])
axes[0].set_xlabel("gen_LNG_ratio")
axes[0].set_ylabel("SMP (원/kWh)")
axes[0].set_title(f"LNG 비중 vs SMP  (r={c_lng:.3f})", fontsize=11)

axes[1].scatter(valid_lng["gen_원자력_ratio"], valid_lng["smp"],
                s=1, alpha=0.2, color="#377eb8")
c_nuc = valid_lng["gen_원자력_ratio"].corr(valid_lng["smp"])
axes[1].set_xlabel("gen_원자력_ratio")
axes[1].set_ylabel("SMP (원/kWh)")
axes[1].set_title(f"원자력 비중 vs SMP  (r={c_nuc:.3f})", fontsize=11)

fig.suptitle("발전원 비중 vs SMP", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step3_2_gen_ratio_vs_smp.png", dpi=150)
plt.close()
print("저장: step3_2_gen_ratio_vs_smp.png")
print(f"\n  gen_LNG_ratio vs SMP 상관: {c_lng:.3f}")
print(f"  gen_원자력_ratio vs SMP 상관: {c_nuc:.3f}")

# ══════════════════════════════════════════════════════════════════════
# 3-3. 연료비
# ══════════════════════════════════════════════════════════════════════
print("\n=== 3-3. 연료비 ===")
FUEL_COLS = ["fuel_cost_LNG", "fuel_cost_유연탄", "fuel_cost_무연탄",
             "fuel_cost_유류", "fuel_cost_원자력"]
FUEL_COLORS = ["#e41a1c", "#4daf4a", "#984ea3", "#ff7f00", "#377eb8"]

fuel_monthly = df[FUEL_COLS].resample("ME").first()  # 월별 값 (월내 동일)

fig, axes = plt.subplots(2, 1, figsize=(14, 8))

# 연료비 시계열
for col, color in zip(FUEL_COLS, FUEL_COLORS):
    axes[0].plot(fuel_monthly.index, fuel_monthly[col],
                 label=col.replace("fuel_cost_", ""), color=color, lw=1.8, marker="o", ms=3)
axes[0].set_ylabel("연료비 (원/kWh 환산)")
axes[0].set_title("월별 연료비 추이 (2023-2025)", fontsize=11, fontweight="bold")
axes[0].legend(fontsize=9)
axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))
axes[0].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1,4,7,10]))
fig.autofmt_xdate(rotation=30)

# SMP vs fuel_cost_LNG scatter
valid_fuel = df[["fuel_cost_LNG", "smp"]].dropna()
axes[1].scatter(valid_fuel["fuel_cost_LNG"], valid_fuel["smp"],
                s=1, alpha=0.3, color="#e41a1c")
c_fuel = valid_fuel["fuel_cost_LNG"].corr(valid_fuel["smp"])
axes[1].set_xlabel("fuel_cost_LNG")
axes[1].set_ylabel("SMP (원/kWh)")
axes[1].set_title(f"LNG 연료비 vs SMP  (r={c_fuel:.3f})", fontsize=11)

plt.tight_layout()
fig.savefig(OUT / "step3_3_fuel_cost.png", dpi=150)
plt.close()
print("저장: step3_3_fuel_cost.png")

fuel_corrs = df[FUEL_COLS + ["smp"]].corr()["smp"].drop("smp").round(3)
print(f"\n연료비 vs SMP 상관:\n{fuel_corrs.to_string()}")

# ══════════════════════════════════════════════════════════════════════
# 3-4. 전력수급
# ══════════════════════════════════════════════════════════════════════
print("\n=== 3-4. 전력수급 ===")
SUPPLY_COLS = ["facility_capacity", "supply_capacity", "daily_max_demand",
               "supply_reserve_power", "supply_reserve_rate", "reserve_to_max_demand"]

print(df[SUPPLY_COLS].describe().round(2).to_string())

fig, axes = plt.subplots(2, 2, figsize=(14, 9))

# supply_reserve_rate 시계열
ax = axes[0][0]
sr = df["supply_reserve_rate"].resample("D").first()
ax.plot(sr.index, sr.values, lw=0.8, color="#2ca02c", alpha=0.8)
ax.axhline(10, color="red", lw=1.2, linestyle="--", label="주의 10%")
ax.axhline(5,  color="darkred", lw=1.2, linestyle="--", label="경보 5%")
ax.set_title("공급예비율 일별 추이", fontsize=10)
ax.set_ylabel("공급예비율 (%)")
ax.legend(fontsize=8)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1,4,7,10]))

# supply_reserve_rate vs SMP
ax = axes[0][1]
valid_sr = df[["supply_reserve_rate", "smp"]].dropna()
ax.scatter(valid_sr["supply_reserve_rate"], valid_sr["smp"], s=1, alpha=0.2, color="#2ca02c")
c_sr = valid_sr["supply_reserve_rate"].corr(valid_sr["smp"])
ax.set_xlabel("공급예비율 (%)")
ax.set_ylabel("SMP (원/kWh)")
ax.set_title(f"공급예비율 vs SMP  (r={c_sr:.3f})", fontsize=10)

# daily_max_demand vs SMP
ax = axes[1][0]
valid_dm = df[["daily_max_demand", "smp"]].dropna()
ax.scatter(valid_dm["daily_max_demand"], valid_dm["smp"], s=1, alpha=0.2, color="#9467bd")
c_dm = valid_dm["daily_max_demand"].corr(valid_dm["smp"])
ax.set_xlabel("최대전력 daily_max_demand (MW)")
ax.set_ylabel("SMP (원/kWh)")
ax.set_title(f"최대전력 vs SMP  (r={c_dm:.3f})", fontsize=10)

# supply_capacity 시계열
ax = axes[1][1]
sc = df[["facility_capacity", "supply_capacity"]].resample("ME").first()
ax.plot(sc.index, sc["facility_capacity"], label="설비용량", lw=1.5, color="#1f77b4")
ax.plot(sc.index, sc["supply_capacity"],   label="공급능력", lw=1.5, color="#ff7f0e")
ax.set_ylabel("MW")
ax.set_title("설비용량·공급능력 월별 추이", fontsize=10)
ax.legend(fontsize=9)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1,4,7,10]))

fig.suptitle("전력수급 변수 분석", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step3_4_supply.png", dpi=150)
plt.close()
print("저장: step3_4_supply.png")

supply_corrs = df[SUPPLY_COLS + ["smp"]].corr()["smp"].drop("smp").round(3)
print(f"\n전력수급 vs SMP 상관:\n{supply_corrs.to_string()}")

# ── 최종 요약 ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("Step 3 주요 인사이트")
print("="*60)
all_feat_corr = df.drop(columns=["load_diff_jlfd_slfd","load_diff_jlfd_mlfd"], errors="ignore")
corr_smp = all_feat_corr.corr()["smp"].drop("smp").abs().sort_values(ascending=False)
print("\nSMP 절대 상관계수 상위 15:")
for col, val in corr_smp.head(15).items():
    raw = all_feat_corr.corr()["smp"][col]
    print(f"  {col:<38}  {raw:+.3f}")
