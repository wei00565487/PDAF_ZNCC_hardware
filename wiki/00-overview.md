---
id: 00-overview
title: bxsim 全体像 — 何ができるか
type: overview
tags: [overview, architecture, bxsim, crosstalk]
updated: 2026-09-08
related: [10-setup, 20-physics-model, 30-results, 70-assumptions]
source_of_truth: C:\Users\tachi\Documents\bayer-crosstalk-sim
---

# bxsim 全体像 — 何ができるか

## 要約

有償ツールなしで Bayer / RGB-IR CMOS イメージセンサの混色を評価する。
2026-09-08 に初版を構築。numpy / scipy / matplotlib のみで動き、
31 波長 × 4 構成のスイープが 1 分弱（平面波）で回る。

## できること

| 出力 | API |
|---|---|
| 混色カーネル（自画素・隣接画素への配分） | `Simulator.kernel(wl, cra_deg, f_number)` |
| 光学 / 電気クロストークの分離 | `transport="full"` vs `"ideal"` |
| Bayer チャネル分光応答（混色あり / なし） | `Simulator.spectral_response(...)` |
| 3x3 混色行列と CCM ノイズ利得 | `color_mixing_matrix`, `ccm_noise_gain` |
| 任意の CFA パターン（RGB-IR 4x4 等）の画素別応答 | `scripts/run_rgbk.py` の枠組み |
| F 値光束での照明 | `f_number=1.8` |
| 厳密 FDTD 検証 | `meep/pixel_fdtd.py`（WSL） |

## 設計の要

**随伴法**。照明条件ごとに連続の式を解き直すのではなく、拡散方程式の随伴問題を
幾何ごとに 1 回だけ解く。`u(x,y,z)` = 「その点で生成したキャリアが対象 PD に収集される確率」
が得られ、あとは `G` との内積で全条件のカーネルが出る（→ [[20-physics-model]]）。

**混色の帰属**は「光子はちょうど 1 つの CFA セルを通る」という厳密な分解に基づく。
中心セルだけを開口させて計算し、周期性から全体を再構成する。

**分光透過率は幾何カーネルの外**。`K_geom(λ) × T_c(λ)` の形なので、CFA カーブを差し替えても
カーネルの再計算は不要。

## ファイル構成

```
bxsim/
  materials.py   Si の n・α（Green 2008 準拠）、CFA/IRCF 透過率、ARC の特性行列（斜入射対応）
  stack.py       画素スタックの幾何・材料・数値パラメータ（PixelStack データクラス）
  optics.py      角スペクトル法 BPM、スプリットステップ、F 値光束 → G(x,y,z)
  diffusion.py   随伴拡散ソルバ → 収集確率マップ u、カーネル合成
  crosstalk.py   波長/角度スイープ、分光応答、3x3 混色行列、CCM ノイズ利得
  plotting.py    図のヘルパ
scripts/
  selftest.py            物理検証（まずこれ）
  run_spectral.py        DTI 構成別の分光スイープ（fig1-4）
  run_cra.py             斜入射スイープ（fig5）
  run_image.py           ISP コストのデモ（fig6）
  run_case_3um.py        3.0µm 大画素ケース（fig7）
  run_rgbk.py            RGB-IR 4x4 の 6 個の G 画素（fig9/12/14）
  draw_structure.py      上面図・断面図（fig10）
  run_fnumber.py         F 値の効果（fig11）
  run_grid_ircf.py       IRCF 厚と低屈折率グリッド（fig13）
  run_g_sensitivity.py   光源別の G 画素感度差（fig15）
  run_artifact_level.py  画質影響の定量（fig16）
meep/
  pixel_fdtd.py   Meep による厳密 FDTD
  _diag_slab.py   Si 板での解像度収束診断
  run_res60.sh    解像度 60 の実行チェーン
out/              生成物（PNG + CSV）
wiki/             本ナレッジベース
```

## 主要パラメータ（`PixelStack`）

| 名前 | 既定値 | 意味 |
|---|---|---|
| `pitch_um` | 0.80 | 画素ピッチ |
| `n_pix` | 5 | シミュレーション配列サイズ（奇数、横方向は周期境界） |
| `ml_sag_um` | 0.35 | マイクロレンズのサグ量（ROC はここから導出） |
| `ml_shift_um` | 0.0 | 瞳補正のレンズシフト（**+x に傾いた光には負の値**） |
| `t_ircf_um` / `n_ircf` | 0.0 / 1.65 | オンチップ IR カット（CFA の上） |
| `t_cfa_um` | 0.50 | カラーフィルタ厚 |
| `cfa_grid_enabled` / `cfa_grid_width_um` / `n_cfa_grid` | False / 0.15 / 1.25 | 低屈折率グリッド |
| `si_thickness_um` | 3.00 | Si（エピ）厚 |
| `dti_enabled` / `dti_depth_um` / `dti_width_um` | True / 2.6 / 0.10 | DTI |
| `pd_fill` / `pd_depth_um` | 0.75 / 1.00 | PD 開口率と空乏層深さ |
| `dx_opt_nm` / `dx_diff_nm` | 25 / 50 | 光学格子 / 拡散格子（整数倍であること） |

## 実測データの差し替え

- Si の n, α → `materials.load_si_csv("si.csv")`（`wavelength_nm,n,alpha_per_cm`）
- CFA 透過率 → `materials.cfa_transmittance` を実測カーブ補間に置き換え
- **色再現の精度を一番左右するのは CFA カーブ**（→ [[70-assumptions]]）
