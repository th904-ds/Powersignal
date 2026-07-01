"""
EDA Step 2 — 타깃 (smp) 분포·패턴
  1) 연간 시계열 + 이상치 spike 날짜
  2) 시간대별 boxplot
  3) 요일별·월별 boxplot
  4) 분포 히스토그램 (왜도 확인)
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

smp = df["smp"].dropna()

print(f"SMP 기초 통계 (2023-2025)")
print(smp.describe().round(2).to_string())
print(f"왜도(skewness): {smp.skew():.3f}")
print(f"첨도(kurtosis): {smp.kurtosis():.3f}")

# ── 1. 연간 시계열 + spike ────────────────────────────────────────────
SPIKE_Q = 0.995
spike_thr = smp.quantile(SPIKE_Q)
spikes = smp[smp >= spike_thr]

fig, axes = plt.subplots(3, 1, figsize=(16, 10), sharex=False)
years = [2023, 2024, 2025]
colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

for ax, yr, col in zip(axes, years, colors):
    s = smp[smp.index.year == yr]
    ax.plot(s.index, s.values, color=col, lw=0.6, alpha=0.8)
    # spike 표시
    sp = spikes[spikes.index.year == yr]
    ax.scatter(sp.index, sp.values, color="red", s=12, zorder=5, label=f"Spike(≥{spike_thr:.0f})")
    ax.set_ylabel("SMP (원/kWh)")
    ax.set_title(f"{yr}년", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m월"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    if len(sp):
        for ts, val in sp.items():
            ax.annotate(f"{ts.strftime('%m-%d')} {val:.0f}",
                        xy=(ts, val), xytext=(0, 6), textcoords="offset points",
                        fontsize=6, color="red", ha="center")
    ax.legend(fontsize=8)

fig.suptitle("SMP 시계열 (2023–2025)", fontsize=13, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step2_smp_timeseries.png", dpi=150)
plt.close()
print(f"\n저장: step2_smp_timeseries.png")
print(f"Spike 임계(상위 0.5%): {spike_thr:.1f} 원/kWh  →  {len(spikes)}개 시간")
top5 = spikes.nlargest(5)
print("  상위 5개:")
for ts, val in top5.items():
    print(f"    {ts}  {val:.2f}")

# ── 2. 시간대별 boxplot ──────────────────────────────────────────────
df["hour"] = df.index.hour
# hour=0 → 자정 (hour=24 컨벤션: 다음날 00시)
hour_labels = list(range(1, 24)) + [24]  # 01~23 + 자정(0→24)

fig, ax = plt.subplots(figsize=(14, 5))
hour_groups = [smp[smp.index.hour == (h % 24)] for h in hour_labels]
bp = ax.boxplot(hour_groups, patch_artist=True, showfliers=False,
                medianprops=dict(color="red", lw=1.5))

# 시간대별 색상 (첨두: 오전9-12, 오후13-17)
for i, patch in enumerate(bp["boxes"]):
    h = hour_labels[i]
    if h in range(9, 18):
        patch.set_facecolor("#ff7f0e")
        patch.set_alpha(0.6)
    elif h in [1, 2, 3, 4, 5]:
        patch.set_facecolor("#aec7e8")
        patch.set_alpha(0.6)
    else:
        patch.set_facecolor("#c7e9c0")
        patch.set_alpha(0.6)

ax.set_xticks(range(1, 25))
ax.set_xticklabels(hour_labels, fontsize=8)
ax.set_xlabel("시간 (시)")
ax.set_ylabel("SMP (원/kWh)")
ax.set_title("시간대별 SMP 분포 (2023-2025)", fontsize=12, fontweight="bold")
from matplotlib.patches import Patch
legend_el = [Patch(facecolor="#ff7f0e", alpha=0.6, label="첨두 (09-17시)"),
             Patch(facecolor="#aec7e8", alpha=0.6, label="심야 (01-05시)"),
             Patch(facecolor="#c7e9c0", alpha=0.6, label="기타")]
ax.legend(handles=legend_el, fontsize=9)
plt.tight_layout()
fig.savefig(OUT / "step2_smp_by_hour.png", dpi=150)
plt.close()
print("저장: step2_smp_by_hour.png")

# 시간대별 중앙값 출력
hourly_med = smp.groupby(smp.index.hour).median()
peak_h   = hourly_med.idxmax()
offpeak_h = hourly_med.idxmin()
print(f"\n시간대별 SMP 중앙값  최고: {peak_h:02d}시 {hourly_med[peak_h]:.1f}  "
      f"최저: {offpeak_h:02d}시 {hourly_med[offpeak_h]:.1f}")

# ── 3. 요일별·월별 boxplot ───────────────────────────────────────────
WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]
MONTH_LABELS   = [f"{m}월" for m in range(1, 13)]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# 요일별
wd_groups = [smp[smp.index.dayofweek == i] for i in range(7)]
bp1 = ax1.boxplot(wd_groups, patch_artist=True, showfliers=False,
                  medianprops=dict(color="red", lw=1.5))
for i, patch in enumerate(bp1["boxes"]):
    patch.set_facecolor("#aec7e8" if i < 5 else "#ffbb78")
    patch.set_alpha(0.7)
ax1.set_xticklabels(WEEKDAY_LABELS)
ax1.set_ylabel("SMP (원/kWh)")
ax1.set_title("요일별 SMP 분포", fontsize=11, fontweight="bold")
ax1.legend(handles=[Patch(facecolor="#aec7e8", alpha=0.7, label="평일"),
                    Patch(facecolor="#ffbb78", alpha=0.7, label="주말")], fontsize=9)

# 월별
mo_groups = [smp[smp.index.month == m] for m in range(1, 13)]
bp2 = ax2.boxplot(mo_groups, patch_artist=True, showfliers=False,
                  medianprops=dict(color="red", lw=1.5))
season_colors = {1:"#aec7e8", 2:"#aec7e8", 3:"#c7e9c0", 4:"#c7e9c0", 5:"#c7e9c0",
                 6:"#ffbb78", 7:"#ffbb78", 8:"#ffbb78", 9:"#c7e9c0",
                 10:"#c7e9c0", 11:"#c7e9c0", 12:"#aec7e8"}
for i, patch in enumerate(bp2["boxes"]):
    patch.set_facecolor(season_colors[i+1])
    patch.set_alpha(0.7)
ax2.set_xticklabels(MONTH_LABELS, fontsize=9)
ax2.set_ylabel("SMP (원/kWh)")
ax2.set_title("월별 SMP 분포", fontsize=11, fontweight="bold")
season_legend = [Patch(facecolor="#aec7e8", alpha=0.7, label="겨울(12-2월)"),
                 Patch(facecolor="#c7e9c0", alpha=0.7, label="봄·가을"),
                 Patch(facecolor="#ffbb78", alpha=0.7, label="여름(6-8월)")]
ax2.legend(handles=season_legend, fontsize=9)

fig.suptitle("요일별·월별 SMP 분포 (2023-2025)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step2_smp_by_weekday_month.png", dpi=150)
plt.close()
print("저장: step2_smp_by_weekday_month.png")

# 월별 중앙값
monthly_med = smp.groupby(smp.index.month).median()
print("\n월별 SMP 중앙값:")
for m, v in monthly_med.items():
    print(f"  {m:2d}월: {v:.1f}")

# ── 4. 분포 히스토그램 ───────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 4))

# 원값
axes[0].hist(smp, bins=80, color="#1f77b4", alpha=0.7, edgecolor="white", lw=0.3)
axes[0].axvline(smp.mean(), color="red", lw=1.5, label=f"평균 {smp.mean():.1f}")
axes[0].axvline(smp.median(), color="orange", lw=1.5, linestyle="--",
                label=f"중앙값 {smp.median():.1f}")
axes[0].set_xlabel("SMP (원/kWh)")
axes[0].set_ylabel("빈도")
axes[0].set_title(f"SMP 분포  (왜도={smp.skew():.2f})", fontsize=11)
axes[0].legend(fontsize=9)

# log 변환
log_smp = np.log1p(smp)
axes[1].hist(log_smp, bins=80, color="#2ca02c", alpha=0.7, edgecolor="white", lw=0.3)
axes[1].axvline(log_smp.mean(), color="red", lw=1.5, label=f"평균 {log_smp.mean():.2f}")
axes[1].set_xlabel("log(1 + SMP)")
axes[1].set_ylabel("빈도")
axes[1].set_title(f"log(1+SMP) 분포  (왜도={log_smp.skew():.2f})", fontsize=11)
axes[1].legend(fontsize=9)

fig.suptitle("SMP 분포: 원값 vs log 변환", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step2_smp_distribution.png", dpi=150)
plt.close()
print("저장: step2_smp_distribution.png")

print(f"\n원값  왜도: {smp.skew():.3f}  → {'우편포 (양의 왜도)' if smp.skew()>0 else '좌편포'}")
print(f"log값 왜도: {log_smp.skew():.3f}  → {'정규분포에 가까움' if abs(log_smp.skew())<0.5 else '왜도 여전히 존재'}")

# ── 요약 ─────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("Step 2 주요 인사이트")
print("="*55)
print(f"  SMP 범위   : {smp.min():.1f} ~ {smp.max():.1f} 원/kWh")
print(f"  평균/중앙값 : {smp.mean():.1f} / {smp.median():.1f}")
print(f"  첨두 시간대 : {peak_h:02d}시 (중앙값 {hourly_med[peak_h]:.1f})")
print(f"  심야 시간대 : {offpeak_h:02d}시 (중앙값 {hourly_med[offpeak_h]:.1f})")
peak_vs_offpeak = hourly_med[peak_h] / hourly_med[offpeak_h]
print(f"  첨두/심야 배율: {peak_vs_offpeak:.2f}x")
summer_med = monthly_med[[6,7,8]].mean()
winter_med = monthly_med[[12,1,2]].mean()
print(f"  여름 평균 중앙값: {summer_med:.1f}  /  겨울 평균 중앙값: {winter_med:.1f}")
