"""
EDA Step 6 — 기상변수 × SMP 분석

분석 항목:
  6-1. 기상변수 분포 및 결측 구조 확인 (0-fill 전/후)
  6-2. 기상-SMP 선형 상관관계 히트맵
  6-3. 기온 vs SMP 비선형 패턴 (U자 효과 확인)
  6-4. 시간대별 기상-SMP 동시 패턴
  6-5. 계절별 기상-SMP 박스플롯
  6-6. 태양광 발전 비중 × 일사량 교차 분석
  6-7. 전처리 방향 요약
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

BASE    = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")
FEAT    = BASE / "00.collector/data/features"
WX_PATH = BASE / "01.preprocessing/output/weather_hourly.parquet"
OUT     = BASE / "01.preprocessing/eda_output"
OUT.mkdir(exist_ok=True)

# ── 데이터 로드 ────────────────────────────────────────────────────────
print("=" * 65)
print("  EDA Step 6 — 기상변수 × SMP 분석")
print("=" * 65)

wx = pd.read_parquet(WX_PATH)
wx["datetime"] = pd.to_datetime(wx["datetime"])

base = pd.read_parquet(FEAT / "base_merged.parquet")
base["datetime"] = pd.to_datetime(base["datetime"])
base = base[(base["datetime"] >= "2023-01-01") & (base["datetime"] < "2026-01-01")]

# 7개소 평균 컬럼만 사용 (avg_*)
AVG_COLS = [c for c in wx.columns if c.startswith("avg_")]
wx_avg = wx[["datetime"] + AVG_COLS].copy()

df = base[["datetime", "smp", "gen_신재생·기타_ratio", "gen_신재생·기타",
           "gen_total", "slfd"]].merge(wx_avg, on="datetime", how="inner")
df = df.sort_values("datetime").reset_index(drop=True)

print(f"\n분석 데이터: {df.shape}  ({df['datetime'].min()} ~ {df['datetime'].max()})")
print(f"기상 avg 컬럼: {AVG_COLS}")

# ── 6-1. 기상변수 결측 구조 확인 ─────────────────────────────────────
print("\n─── 6-1. 기상변수 결측 구조 ───")
ZERO_FILL_COLS = ["avg_precip_mm", "avg_snow_cm", "avg_sunshine_hr", "avg_solar_MJm2"]
OTHER_COLS     = ["avg_temp_c", "avg_humidity_pct", "avg_wind_speed_ms"]

print(f"\n  [결측→0 fill 대상 4개]  (물리적으로 비·눈·일사 없으면 0이 맞음)")
for c in ZERO_FILL_COLS:
    n_null = df[c].isnull().sum()
    pct    = n_null / len(df) * 100
    print(f"    {c:<25}: {n_null:,}행 ({pct:.1f}%) 결측  → 0 fill")

# 일사량 결측이 야간인지 확인
solar_miss_hour = df[df["avg_solar_MJm2"].isnull()]["datetime"].dt.hour.value_counts().sort_index()
print(f"\n  avg_solar_MJm2 결측 시간대 분포 (상위):")
for hr, cnt in solar_miss_hour.head(12).items():
    print(f"    {hr:02d}시: {cnt:,}건")

# 0 fill 적용
for c in ZERO_FILL_COLS:
    df[c] = df[c].fillna(0)

print(f"\n  [보간 대상 3개]")
for c in OTHER_COLS:
    n_null = df[c].isnull().sum()
    print(f"    {c:<25}: {n_null:,}행 ({n_null/len(df)*100:.2f}%) 결측")
    if n_null > 0:
        df[c] = df[c].interpolate(method="linear").ffill().bfill()
        print(f"      → 선형보간 완료. 잔여: {df[c].isnull().sum()}")

print(f"\n  0-fill + 보간 후 전체 결측: {df[AVG_COLS].isnull().sum().sum()}")

# ── 6-2. 기상-SMP 상관관계 ───────────────────────────────────────────
print("\n─── 6-2. 기상-SMP 상관관계 ───")
corr_wx = df[["smp"] + AVG_COLS].corr()["smp"].drop("smp")
print(f"\n  기상변수 vs SMP 상관계수 (Pearson):")
for col, val in corr_wx.sort_values(key=abs, ascending=False).items():
    bar = "█" * int(abs(val) * 30)
    sign = "+" if val >= 0 else "-"
    print(f"    {col:<25}: {val:+.3f}  {sign}{bar}")

# 기상 + 주요 비기상 상관 히트맵
HMAP_COLS = ["smp", "slfd"] + AVG_COLS + ["gen_신재생·기타_ratio"]
hmap = df[HMAP_COLS].corr()

fig, ax = plt.subplots(figsize=(10, 9))
im = ax.imshow(hmap.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
plt.colorbar(im, ax=ax, shrink=0.8, label="Pearson r")
ax.set_xticks(range(len(HMAP_COLS)))
ax.set_yticks(range(len(HMAP_COLS)))
ax.set_xticklabels(HMAP_COLS, rotation=45, ha="right", fontsize=9)
ax.set_yticklabels(HMAP_COLS, fontsize=9)
for i in range(len(HMAP_COLS)):
    for j in range(len(HMAP_COLS)):
        val = hmap.iloc[i, j]
        if abs(val) >= 0.15 and i != j:
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=7.5, color="white" if abs(val) > 0.6 else "black")
ax.set_title("기상변수 × SMP 상관계수 히트맵 (2023-2025)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step6_weather_corr_heatmap.png", dpi=150)
plt.close()
print("  저장: step6_weather_corr_heatmap.png")

# ── 6-3. 기온 vs SMP 비선형 패턴 ────────────────────────────────────
print("\n─── 6-3. 기온 vs SMP 비선형 패턴 ───")

# 기온 2°C 빈 집계
df["temp_bin"] = (df["avg_temp_c"] // 2 * 2).astype(int)
bin_stats = df.groupby("temp_bin")["smp"].agg(["mean", "median", "count"]).reset_index()
bin_stats = bin_stats[bin_stats["count"] >= 20]

# U자 검증: 상관 vs 이차항 R²
from numpy.polynomial import polynomial as P
x = df["avg_temp_c"].values
y = df["smp"].values
mask = ~(np.isnan(x) | np.isnan(y))
r_lin  = np.corrcoef(x[mask], y[mask])[0, 1]
c2     = np.polyfit(x[mask], y[mask], 2)
y_pred = np.polyval(c2, x[mask])
ss_res = np.sum((y[mask] - y_pred) ** 2)
ss_tot = np.sum((y[mask] - y[mask].mean()) ** 2)
r2_quad = 1 - ss_res / ss_tot

print(f"  기온-SMP 선형 r     : {r_lin:+.4f}")
print(f"  기온-SMP 이차 R²    : {r2_quad:.4f}  (U자 효과 여부)")
print(f"  SMP 최저 기온 빈    : {bin_stats.loc[bin_stats['mean'].idxmin(), 'temp_bin']}°C 부근")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Scatter
ax = axes[0]
ax.scatter(df["avg_temp_c"], df["smp"], s=1, alpha=0.08, color="#1f77b4")
x_fit = np.linspace(df["avg_temp_c"].min(), df["avg_temp_c"].max(), 200)
ax.plot(x_fit, np.polyval(c2, x_fit), "r-", lw=2, label=f"이차 R²={r2_quad:.3f}")
ax.set_xlabel("평균 기온 (°C)", fontsize=10)
ax.set_ylabel("SMP (원/kWh)", fontsize=10)
ax.set_title("기온 vs SMP (전체)", fontsize=11)
ax.legend(fontsize=9)

# 빈별 평균
ax = axes[1]
ax.bar(bin_stats["temp_bin"], bin_stats["mean"], width=1.6, color="#2196F3", alpha=0.8)
ax.set_xlabel("기온 구간 (2°C 빈)", fontsize=10)
ax.set_ylabel("SMP 평균 (원/kWh)", fontsize=10)
ax.set_title("기온 구간별 SMP 평균", fontsize=11)

fig.suptitle("기온 vs SMP 비선형 분석 (2023-2025)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step6_temp_smp_nonlinear.png", dpi=150)
plt.close()
print("  저장: step6_temp_smp_nonlinear.png")

# ── 6-4. 시간대별 기상-SMP 패턴 ─────────────────────────────────────
print("\n─── 6-4. 시간대별 패턴 ───")

df["hour"] = df["datetime"].dt.hour
hourly = df.groupby("hour")[["smp", "avg_temp_c", "avg_solar_MJm2",
                              "avg_humidity_pct"]].mean()

r_solar_hour = df.groupby("hour").apply(
    lambda g: g["avg_solar_MJm2"].corr(g["smp"]), include_groups=False
)
print(f"\n  태양 일사량 × SMP 시간대별 상관 (일사 있는 시간대):")
for hr in range(6, 20):
    r = r_solar_hour.get(hr, np.nan)
    print(f"    {hr:02d}시: r={r:+.3f}")

fig, axes = plt.subplots(2, 2, figsize=(14, 9))

for ax, col, label, color in zip(
    axes.flatten(),
    ["smp", "avg_temp_c", "avg_solar_MJm2", "avg_humidity_pct"],
    ["SMP (원/kWh)", "평균 기온 (°C)", "일사량 (MJ/m²)", "습도 (%)"],
    ["#d62728", "#ff7f0e", "#f7c300", "#1f77b4"]
):
    ax.plot(hourly.index, hourly[col], color=color, lw=2, marker="o", ms=4)
    ax.set_xlabel("시간 (hour)", fontsize=9)
    ax.set_ylabel(label, fontsize=9)
    ax.set_title(label, fontsize=10)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(3))
    ax.grid(alpha=0.3)

fig.suptitle("시간대별 SMP × 기상변수 평균 (2023-2025)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step6_hourly_patterns.png", dpi=150)
plt.close()
print("  저장: step6_hourly_patterns.png")

# ── 6-5. 계절별 기상-SMP 박스플롯 ──────────────────────────────────
print("\n─── 6-5. 계절별 패턴 ───")

season_map = {12: "겨울", 1: "겨울", 2: "겨울",
              3: "봄",   4: "봄",   5: "봄",
              6: "여름", 7: "여름", 8: "여름",
              9: "가을", 10: "가을", 11: "가을"}
season_order = ["봄", "여름", "가을", "겨울"]
df["season"] = df["datetime"].dt.month.map(season_map)

season_smp = df.groupby("season")["smp"].agg(["mean", "median", "std"])
season_temp = df.groupby("season")["avg_temp_c"].mean()
print("\n  계절별 SMP 및 기온:")
for s in season_order:
    print(f"    {s}: SMP 평균={season_smp.loc[s,'mean']:.1f}  "
          f"중앙={season_smp.loc[s,'median']:.1f}  "
          f"std={season_smp.loc[s,'std']:.1f}  "
          f"평균기온={season_temp[s]:.1f}°C")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 계절별 SMP 박스
ax = axes[0]
data_box = [df[df["season"] == s]["smp"].dropna().values for s in season_order]
bp = ax.boxplot(data_box, labels=season_order, patch_artist=True,
                medianprops=dict(color="black", lw=2))
colors = ["#98e0a8", "#ff9b9b", "#ffd59e", "#aeccf5"]
for patch, c in zip(bp["boxes"], colors):
    patch.set_facecolor(c)
ax.set_ylabel("SMP (원/kWh)", fontsize=10)
ax.set_title("계절별 SMP 분포", fontsize=11)
ax.grid(axis="y", alpha=0.3)

# 계절별 기온 vs SMP scatter
ax = axes[1]
cmap = {"봄": "#98e0a8", "여름": "#ff9b9b", "가을": "#ffd59e", "겨울": "#aeccf5"}
for s in season_order:
    sub = df[df["season"] == s]
    ax.scatter(sub["avg_temp_c"], sub["smp"], s=1, alpha=0.1,
               color=cmap[s], label=s)
ax.set_xlabel("평균 기온 (°C)", fontsize=10)
ax.set_ylabel("SMP (원/kWh)", fontsize=10)
ax.set_title("계절별 기온 vs SMP", fontsize=11)
ax.legend(fontsize=9, markerscale=8)

fig.suptitle("계절별 기상-SMP 분석 (2023-2025)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step6_seasonal_smp.png", dpi=150)
plt.close()
print("  저장: step6_seasonal_smp.png")

# ── 6-6. 일사량 × 신재생비중 교차 분석 ─────────────────────────────
print("\n─── 6-6. 일사량 × 신재생 비중 ───")

solar_corr_re = df["avg_solar_MJm2"].corr(df["gen_신재생·기타_ratio"])
solar_corr_smp = df["avg_solar_MJm2"].corr(df["smp"])
re_corr_smp   = df["gen_신재생·기타_ratio"].corr(df["smp"])

print(f"  일사량 × 신재생 비중 상관: r={solar_corr_re:+.4f}")
print(f"  일사량 × SMP 상관        : r={solar_corr_smp:+.4f}")
print(f"  신재생 비중 × SMP 상관   : r={re_corr_smp:+.4f}")

# 낮시간대(06-18시)만 분석
day = df[(df["hour"] >= 6) & (df["hour"] <= 18)]
sc_day = day["avg_solar_MJm2"].corr(day["smp"])
sc_re_day = day["avg_solar_MJm2"].corr(day["gen_신재생·기타_ratio"])
print(f"\n  낮(06-18시) 일사량 × SMP     : r={sc_day:+.4f}")
print(f"  낮(06-18시) 일사량 × 신재생  : r={sc_re_day:+.4f}")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

ax = axes[0]
ax.scatter(day["avg_solar_MJm2"], day["smp"], s=1, alpha=0.1, color="#f7c300")
ax.set_xlabel("일사량 (MJ/m²)", fontsize=10)
ax.set_ylabel("SMP (원/kWh)", fontsize=10)
ax.set_title(f"낮시간 일사량 vs SMP  (r={sc_day:+.3f})", fontsize=11)

ax = axes[1]
ax.scatter(day["avg_solar_MJm2"], day["gen_신재생·기타_ratio"] * 100, s=1, alpha=0.1, color="#2ecc71")
ax.set_xlabel("일사량 (MJ/m²)", fontsize=10)
ax.set_ylabel("신재생 비중 (%)", fontsize=10)
ax.set_title(f"낮시간 일사량 vs 신재생 비중  (r={sc_re_day:+.3f})", fontsize=11)

fig.suptitle("일사량 × 신재생발전 × SMP 관계 (2023-2025, 낮시간)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step6_solar_renewable.png", dpi=150)
plt.close()
print("  저장: step6_solar_renewable.png")

# ── 6-7. 전처리 방향 요약 ───────────────────────────────────────────
print(f"\n{'━'*65}")
print("  6-7. 전처리 방향 요약")
print(f"{'━'*65}")

corr_abs = corr_wx.abs().sort_values(ascending=False)

print(f"""
  [기상변수 전처리 결정]
  ┌─────────────────────────┬────────────────────────────┐
  │ 변수                    │ 처리 방식                  │
  ├─────────────────────────┼────────────────────────────┤
  │ avg_precip_mm           │ NaN → 0 fill (무강수=0)    │
  │ avg_snow_cm             │ NaN → 0 fill (무적설=0)    │
  │ avg_sunshine_hr         │ NaN → 0 fill (야간=0)      │
  │ avg_solar_MJm2          │ NaN → 0 fill (야간=0)      │
  │ avg_temp_c              │ 결측 거의 없음 (linear보간) │
  │ avg_humidity_pct        │ 결측 거의 없음 (linear보간) │
  │ avg_wind_speed_ms       │ 결측 거의 없음 (linear보간) │
  └─────────────────────────┴────────────────────────────┘

  [기상-SMP 상관 순위]
""")
for col, val in corr_abs.items():
    direction = "양(+)" if corr_wx[col] > 0 else "음(-)"
    print(f"    {col:<25}: |r|={val:.3f}  ({direction})")

print(f"""
  [주요 EDA 발견사항]
  1. 기온 U자 효과:
     - 이차 R²={r2_quad:.4f} → 기온 제곱항(temp²) 파생변수 추가 권고
     - 여름 냉방 + 겨울 난방 수요 모두 SMP 상승 요인

  2. 일사량-신재생-SMP 경로:
     - 낮 일사량 ↑ → 신재생 발전 ↑ (r={sc_re_day:+.3f})
     - 신재생 비중 ↑ → SMP ↓ (r={re_corr_smp:+.3f}, merit order 효과)
     - 일사량 직접 SMP 영향: r={solar_corr_smp:+.3f}

  3. 계절별 SMP:
""")
for s in season_order:
    print(f"     {s}: 평균 {season_smp.loc[s,'mean']:.1f}원  기온 {season_temp[s]:.1f}°C")

print(f"""
  [모델 추가 파생변수 권고]
  - avg_temp_c²    (기온 이차항, U자 효과 포착)
  - avg_temp_c_lag24    (전날 동 시간 기온)
  - avg_solar_MJm2_lag1 (직전 시간 일사)
  - is_heatwave    (avg_temp_c >= 33°C, 폭염주의보)
  - is_coldwave    (avg_temp_c <= -12°C, 한파주의보)
""")

print("─── Step 6 완료 ───")
print(f"  생성 파일: step6_weather_corr_heatmap.png")
print(f"             step6_temp_smp_nonlinear.png")
print(f"             step6_hourly_patterns.png")
print(f"             step6_seasonal_smp.png")
print(f"             step6_solar_renewable.png")
