---
id: 10-setup
title: 実行方法とスクリプト一覧
type: howto
tags: [setup, scripts, runtime, wsl, meep]
updated: 2026-09-08
related: [00-overview, 21-validation, 50-fdtd-meep]
source_of_truth: scripts/, meep/, requirements.txt
---

# 実行方法とスクリプト一覧

## 要約

Windows ネイティブの Python で完結する（numpy / scipy / matplotlib のみ）。
FDTD だけ WSL の Meep を使う。まず `selftest.py` を通すこと。

## セットアップ

プロジェクトルート: `C:\Users\tachi\Documents\bayer-crosstalk-sim`

```bash
python -m pip install -r requirements.txt
python scripts/selftest.py
```

`selftest.py` が通れば、光学側のエネルギー保存と輸送側の確率保存が確認できる
（→ [[21-validation]]）。

FDTD を使う場合のみ、WSL Ubuntu で（→ [[50-fdtd-meep]]）:

```bash
apt-get -o Acquire::ForceIPv4=true install -y python3-meep-mpi-default python3-scipy openmpi-bin python3-mpi4py
```

## スクリプトと所要時間（実測、14 コア機）

| スクリプト | 内容 | 所要 | 出力 |
|---|---|---|---|
| `selftest.py` | 物理検証。**最初にこれ** | 10 s | 標準出力 |
| `run_spectral.py` | DTI 構成別の分光スイープ | 55 s | fig1-4, CSV |
| `run_cra.py` | 斜入射スイープ + レンズシフト | 15 s | fig5 |
| `run_image.py` | 彩度低下と CCM ノイズ増幅 | 21 s | fig6 |
| `run_case_3um.py` | 3.0µm 大画素ケース | 36 s | fig7 |
| `draw_structure.py` | 上面図・断面図 | 3 s | fig10 |
| `run_fnumber.py` | F 値の効果 | 431 s | fig11 |
| `run_grid_ircf.py` | IRCF 厚と低屈折率グリッド | 約 25 min | fig13 |
| `run_stacked_rb_ir.py` | K画素のR+B積層可視カットと厚み増加 | 約 2 min | fig17 |
| `run_rgbk.py` | RGB-IR 4x4 の 6 個の G 画素 | 356 s | fig14 |
| `run_g_sensitivity.py` | 光源別の G 画素感度差 | 370 s | fig15 |
| `run_artifact_level.py` | 画質影響の定量 | 625 s | fig16 |
| `meep/run_res60.sh` | FDTD 解像度チェーン（WSL） | 3-4 h | npz |

## 最小の使い方

```python
from bxsim import PixelStack, Simulator

st = PixelStack(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, pd_depth_um=3.0,
                pd_fill=1.0, dti_enabled=True, dti_depth_um=6.0,
                t_ircf_um=0.30, cfa_grid_enabled=True,
                dx_opt_nm=50.0, dz_opt_nm=50.0,
                dx_diff_nm=100.0, dz_diff_nm=100.0)
sim = Simulator(st)
K = sim.kernel(550.0, cra_deg=30.0, f_number=1.8, n_samples=16)
print(K / K.sum())
```

`K[i, j]` は「中心画素の CFA セルを通過した光子のうち、オフセット `(i-h, j-h)` の
フォトダイオードで信号になった割合」。行が y、列が x。

## 高速化の勘所

- **随伴ソルブは幾何ごとに 1 回だけ。** 同じ Si / DTI / PD 構成でスタック上部だけを
  振るなら `sim._u = u` で使い回せる（スイープが 10 倍速くなる）。
- `Simulator` は生成率分布 `G` を (λ, CRA, azimuth, f_number) でキャッシュする。
  `transport="full"` と `"ideal"` を続けて呼べば光学計算は 1 回で済む。
- 格子は `dx_diff_nm / dx_opt_nm` が整数になるよう選ぶこと（アサーションで落ちる）。
- F 値光束は `n_samples=16` で 3 桁収束する。32 以上は無駄。
- 大画素（3.0µm）は `dx_opt_nm=50, dx_diff_nm=100` で十分。既定の 25/50 だと 4 倍遅い。
