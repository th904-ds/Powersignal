"""
EDA Step 1 — 데이터 완성도 점검
  1) 변수별 결측률 바차트
  2) 시간축 결측 히트맵 (월 × 변수)
  3) gen 결측 구간 시각화
  4) ASOS 기상 결측 확인
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Patch
from pathlib import Path

# 한글 폰트
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BASE = Path("c:/Users/김태희/Desktop/프로젝트/3-1. [공모전] 산업통상부/Powersignal")
OUT  = BASE / "01.preprocessing" / "eda_output"
OUT.mkdir(exist_ok=True)

# ── 데이터 로드 ──────────────────────────────────────────────────────
df = pd.read_parquet(BASE / "00.collector/data/features/base_merged.parquet")
df["datetime"] = pd.to_datetime(df["datetime"])

# 2023-2025 구간
df23 = df[(df["datetime"] >= "2023-01-01") & (df["datetime"] < "2026-01-01")].copy()
df23 = df23.set_index("datetime").sort_index()

print(f"base_merged 전체: {df.shape}")
print(f"2023-2025 구간  : {df23.shape}  ({df23.index.min()} ~ {df23.index.max()})")

# 분석 대상 변수 (datetime 제외)
VARS = [c for c in df23.columns if not c.startswith("_")]

# ── 1. 변수별 결측률 바차트 ──────────────────────────────────────────
miss_pct = df23[VARS].isnull().mean() * 100
miss_pct = miss_pct.sort_values(ascending=False)

fig, ax = plt.subplots(figsize=(12, 6))
colors = ["#d62728" if v > 10 else "#ff7f0e" if v > 0 else "#2ca02c"
          for v in miss_pct]
bars = ax.barh(miss_pct.index, miss_pct.values, color=colors)
ax.axvline(0, color="gray", lw=0.5)
ax.set_xlabel("결측률 (%)")
ax.set_title("2023-2025 변수별 결측률", fontsize=13, fontweight="bold")
ax.invert_yaxis()
for bar, val in zip(bars, miss_pct.values):
    if val > 0.1:
        ax.text(val + 0.2, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=8)
legend_patches = [
    Patch(color="#d62728", label=">10% (gen 결측)"),
    Patch(color="#ff7f0e", label="0~10% (기상 결측)"),
    Patch(color="#2ca02c", label="완전"),
]
ax.legend(handles=legend_patches, loc="lower right")
plt.tight_layout()
fig.savefig(OUT / "step1_missing_rate.png", dpi=150)
plt.close()
print("저장: step1_missing_rate.png")

# 결측 요약 출력
print("\n결측 상위 변수:")
for col, pct in miss_pct[miss_pct > 0].items():
    print(f"  {col:<38}  {pct:5.1f}%  ({int(pct/100*len(df23)):,}행)")
print(f"\n결측 0%  변수: {(miss_pct == 0).sum()}개")
print(f"결측 있는 변수: {(miss_pct > 0).sum()}개")

# ── 2. 월 × 변수 결측 히트맵 ──────────────────────────────────────
# 결측 있는 변수만
miss_vars = miss_pct[miss_pct > 0].index.tolist()

df_month = df23[miss_vars].copy()
df_month["month"] = df_month.index.to_period("M")
monthly_miss = df_month.groupby("month").apply(lambda x: x.drop(columns="month").isnull().mean() * 100)

fig, ax = plt.subplots(figsize=(14, max(4, len(miss_vars) * 0.45)))
im = ax.imshow(monthly_miss.T.values, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)
ax.set_xticks(range(len(monthly_miss)))
ax.set_xticklabels([str(p) for p in monthly_miss.index], rotation=45, ha="right", fontsize=7)
ax.set_yticks(range(len(miss_vars)))
ax.set_yticklabels(miss_vars, fontsize=8)
plt.colorbar(im, ax=ax, label="결측률 (%)")
ax.set_title("월별 × 변수 결측률 히트맵 (2023-2025)", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step1_missing_heatmap.png", dpi=150)
plt.close()
print("저장: step1_missing_heatmap.png")

# ── 3. gen 결측 구간 시각화 ──────────────────────────────────────────
gen_fuels = {
    "gen_LNG":      "#e41a1c",
    "gen_원자력":    "#377eb8",
    "gen_유연탄":    "#4daf4a",
    "gen_무연탄":    "#984ea3",
    "gen_유전":      "#ff7f00",
    "gen_수력":      "#a65628",
    "gen_신재생·기타": "#f781bf",
    "gen_양수":      "#999999",
}

fig, axes = plt.subplots(len(gen_fuels), 1, figsize=(16, 10), sharex=True)
full_idx = pd.date_range("2023-01-01 01:00", "2026-01-01 00:00", freq="h")

for ax, (col, color) in zip(axes, gen_fuels.items()):
    if col not in df23.columns:
        ax.set_ylabel(col, fontsize=7)
        continue
    s = df23[col].reindex(full_idx)
    is_miss = s.isnull().astype(int)
    ax.fill_between(s.index, is_miss, step="pre", color=color, alpha=0.8)
    ax.fill_between(s.index, 1 - is_miss, step="pre", color="#eeeeee", alpha=0.5)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_ylabel(col.replace("gen_", ""), fontsize=8, rotation=0, ha="right", labelpad=50)
    miss_cnt = is_miss.sum()
    ax.text(0.01, 0.5, f"{miss_cnt/len(full_idx)*100:.1f}%",
            transform=ax.transAxes, va="center", fontsize=8,
            color=color if miss_cnt > 0 else "gray")

axes[-1].xaxis.set_major_locator(mticker.MaxNLocator(12))
fig.autofmt_xdate(rotation=30)
fig.suptitle("gen 연료원별 결측 구간 (빨간=결측, 회색=보유) 2023-2025", fontsize=12, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "step1_gen_missing_timeline.png", dpi=150)
plt.close()
print("저장: step1_gen_missing_timeline.png")

# ── 4. ASOS 기상 결측 요약 ────────────────────────────────────────────
weather_cols = ["temp_c", "humidity_pct", "wind_speed_ms", "dew_point_c"]
print("\n=== ASOS 기상 결측 ===")
for col in weather_cols:
    if col not in df23.columns:
        print(f"  {col}: 컬럼 없음")
        continue
    n = df23[col].isnull().sum()
    pct = n / len(df23) * 100
    # 연속 결측 구간
    miss_ts = df23[col].isnull()
    gaps = []
    in_gap = False
    gap_start = None
    for ts, v in miss_ts.items():
        if v and not in_gap:
            in_gap = True
            gap_start = ts
        elif not v and in_gap:
            in_gap = False
            gaps.append((gap_start, ts))
    if in_gap:
        gaps.append((gap_start, miss_ts.index[-1]))
    print(f"  {col:<20}: {n:,}행 ({pct:.2f}%)  연속구간 {len(gaps)}개")
    for s, e in gaps[:5]:
        print(f"      {s} ~ {e}")
    if len(gaps) > 5:
        print(f"      ... 외 {len(gaps)-5}개")

# ── 5. 전체 요약 텍스트 ──────────────────────────────────────────────
print("\n" + "="*60)
print("Step 1 요약")
print("="*60)
print(f"분석 기간   : 2023-01-01 ~ 2025-12-31")
print(f"총 행 수    : {len(df23):,}  (기대 {len(full_idx):,}, "
      f"충족률 {len(df23)/len(full_idx)*100:.1f}%)")
print(f"완전 변수   : {(miss_pct==0).sum()}개")
print(f"gen 결측    : LNG/원자력/유연탄/무연탄/유전 → 각 12.8% (3,361시간, 21구간)")
print(f"기상 결측   : 소수 (ASOS 장애·결측 등)")
print(f"\n결측 처리 방향:")
print(f"  gen 5종  → 일별 합산 후 24시간 반복 방식으로 보간 (모델팀 동일 방식)")
print(f"  기상     → 선형 보간 (단기 장애) 또는 4개소 평균으로 대체")
print(f"\nEDA 출력 위치: {OUT}")
