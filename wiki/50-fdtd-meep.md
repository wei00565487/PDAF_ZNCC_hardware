---
id: 50-fdtd-meep
title: Meep FDTD による厳密検証 — 環境構築と収束問題
type: record
tags: [meep, fdtd, wsl, convergence, dti-reflection, validation]
updated: 2026-09-09
related: [21-validation, 20-physics-model, 60-roadmap, 40-design-insights]
source_of_truth: meep/pixel_fdtd.py, scripts/compare_meep_bpm.py, scripts/plot_absolute_qe_validation.py, out/meep_bpm_comparison.csv, out/absolute_qe_validation.csv, out/fig21_external_qe_validation.png
---

# Meep FDTD による厳密検証 — 環境構築と収束問題

## 要約

BPM が原理的に扱えない**酸化膜 DTI の反射**と**低屈折率グリッドの導波**を確定させるため、
MIT Meep（無償・GPL）を WSL に構築した。環境は動いているが、**必要解像度が高く、
絶対 QE はまだ収束していない。2026-09-09 に同一誘電体構造でBPMとの比較系列を取得し、
Si内の正規化吸収深さ分布は解像度60で一致したが、絶対QEと画素分配には残差がある。

## なぜ FDTD が要るか

BPM は**スカラー・一方向**近似なので、以下は原理的に扱えない。

- 偏光依存、ベクトル集光効果
- スタック内の多重反射・干渉
- **酸化膜 DTI の反射**（本ツールは吸収壁扱いなので QE を過小評価）
- 低屈折率グリッドの側壁での後方反射

現行構造には金属および負の誘電率を持つDrude/Lorentz分散材料がないため、**プラズモン共鳴は
計算していない**。Meep自体は分散金属を定義すれば扱えるが、数nm級の金属形状と表皮深さを
解像する別の収束試験が必要になる。

## 2026-09-09 同一条件BPM比較

DTIと低屈折率グリッドを外し、両ソルバを0.8µmピッチ、550nm、法線入射、3×3セル、
MLサグ0.35µm、CFA 0.50µm、Si 3.0µmへそろえた。

| Meep解像度 | Meep QE | BPM QE | Meep XT | BPM XT | 深さ分布cos類似度 |
|---:|---:|---:|---:|---:|---:|
| 30 px/µm | 31.68% | 76.34% | 17.21% | 15.08% | 0.97981 |
| 45 px/µm | 52.07% | 76.34% | 14.46% | 15.08% | 0.99790 |
| 60 px/µm | 58.29% | 76.34% | 13.47% | 15.08% | 0.99945 |

判定は、**吸収深さの形状は整合、絶対QEは未収束、光学XTは解像度60で1.61ポイント差**。
素Si板の解像度60も解析解0.5418に対して0.5008（-7.6%）なので、Meep絶対値には少なくとも
この離散化誤差が残る。再計算は `meep/run_validation.sh`、比較は
`scripts/compare_meep_bpm.py` を使う。

### 絶対QEの差分分解

同じ解像度60で全CFAセルを透明にした全面照明も計算した。

| 指標 | Meep | BPM | 判定 |
|---|---:|---:|---|
| 全面照明QE（直接値） | 72.73% | 82.07% | Meepは素Si板と同様にメッシュ損失を含む |
| 全面照明QE（素Si板誤差で補正） | 78.68% | 82.07% | 差3.39ポイント |
| 中心開口QE（暫定収束範囲） | 63.06〜64.61% | 76.34% | 黒CFA境界の反射・回折差が残る |
| 中心/全面QE保持率 | 推定82.1% | 93.0% | BPMは開口境界損失を小さく見積もる |

中心開口のMeep暫定範囲は、素Si板r60誤差による補正値63.06%と、r30/45/60を
`q(r)=q_inf+a/r^p`で外挿した64.61%で挟んだ。完全な収束値ではないが、BPMの絶対QEへ
掛ける現条件専用係数は`0.826〜0.846`となる。

したがって、BPMで設計スイープを進めてよい。BPMは形状・XT・相対変化・設計順位に使い、
絶対QEは代表条件ごとのMeep係数で校正する。金属、数十nm以下の構造、強い回折格子、
プラズモン共鳴を追加した場合は同じ係数を流用せず、Meepの収束系列を取り直す。

吸収分布`G(x,y,z)`を同一の3D随伴キャリア収集モデルへ通した外部QEは、BPM 76.27%、
Meep r60直接値58.24%、Meep暫定収束推定63.00〜64.56%。このベンチマークでは全PDへの
収集を合計した効率が約99.9%なので、外部QE差はほぼ光学吸収差を引き継ぐ。

図示は `scripts/plot_absolute_qe_validation.py`、出力は
`out/fig20_absolute_qe_validation.png`、`out/fig21_external_qe_validation.png`、
`out/absolute_qe_validation.csv`。

特に「低屈折率グリッドで混色が減り**かつ QE が上がる**」という結論（→ [[40-design-insights]]）は
BPM の導波計算に依存しているので、FDTD での確認が要る。

## 環境構築（現PC: WSL Ubuntu 24.04）

Ubuntu 24.04 の設定済みaptリポジトリにはpymeepが無かったため、micromambaとconda-forgeを使う。

```bash
export MAMBA_ROOT_PREFIX="$HOME/.micromamba"
micromamba create -f meep/environment.yml
```

構築済み環境は Meep 1.31.0 / Python 3.11 / MPICH MPI版。実行時はconda環境内の
`mpirun` と `python` を対で使う。システムOpenMPIとの混在は避ける。

**引っかかりどころ**:

| 症状 | 原因 | 対処 |
|---|---|---|
| `Failed to fetch ... Network is unreachable` | apt が IPv6 を掴む | `-o Acquire::ForceIPv4=true` |
| `MPI_Comm_rank() called before MPI_INIT` | MPI 版 Meep は mpirun 必須 | `mpirun -np N python3 ...` |
| `mpirun: command not found` | ランタイムのみで `openmpi-bin` が無い | 追加インストール |
| `failed to load python MPI module (mpi4py)` | mpi4py 未導入 | `python3-mpi4py` |
| `prte-rmaps-base:alloc-error` | `-np` が**物理コア数**を超えた | 14 コア機なら `-np 14` |

別PCで作成した旧NPZは Meep 1.29.0。現PCの新規検証系列は Meep 1.31.0。

## スクリプト側で修正した問題

### 正規化バグ（重大）

入射電力を `add_flux`、吸収を `add_dft_fields` で計算していたが、**Meep 内部でこの 2 つの
正規化が約 2.06 倍ずれる**。QE が一律その分低く出る。

修正: 両方を DFT 場から計算する。真空中の下向き平面波は DFT 振幅 E に対し
単位面積あたり `0.5 * |E|^2` を運ぶ（Meep 単位系で c = eps0 = mu0 = 1）。

```python
E2 = sum(np.abs(sim.get_dft_array(pdft, c, 0))**2 for c in (mp.Ex, mp.Ey, mp.Ez))
_, _, _, w = sim.get_array_metadata(vol=pvol)
p_inc = 0.5 * float((E2 * np.asarray(w).reshape(E2.shape)).sum())
```

`get_array_metadata` の重み `w` は体積要素を含む（`sum(w)` = 体積で確認済み）。

全面照明では入射電力も吸収量も3×3セル全面の値なので、中心1画素開口で使う
`p_inc/9`ではなく`p_inc`で正規化する。`pixel_fdtd.py`は`--aperture`に応じて分母を切り替える。

### 配列形状

DFT 配列は `cell_size * resolution` からは決まらない。`get_array_metadata(vol=...)` で
実座標を取り、それで画素ビニングする。

### 偏光の対称化

線偏光（Ex）で走らせるが、正方格子は 4 回対称なので**無偏光の答えは Ex の結果と
その転置の平均**。さらに鏡映対称化すると離散化の非対称が落ちる。
その差分（`asym`）は誤差の目安として出力している。

### 鏡映対称性による高速化

法線入射なら `mp.Mirror(mp.X, phase=-1)` + `mp.Mirror(mp.Y, phase=+1)` が使える。
Si 板テストで結果が完全一致（0.5008）し、**8.6 倍高速**（97.9 s → 11.4 s）。

## 収束問題 — 必要解像度

素の Si 板で吸収率を解析解 0.5418 と比較（550nm、n = 4.09、λ/n = 134nm）:

| 解像度 | dx | Si 内 点/λ | 吸収率 | 解析解比 |
|---|---|---|---|---|
| 20 | 50nm | 2.7 | 0.0099 | -98% |
| 30 | 33nm | 4.0 | 0.1805 | -67% |
| 40 | 25nm | 5.4 | 0.4390 | -19% |
| 45 | 22nm | 6.1 | 0.4434 | -18% |
| 60 | 17nm | 8.0 | 0.5008 | -7.6% |
| 80 | 13nm | 10.7 | 0.5195 | -4.1% |
| 120 | 8nm | 16.0 | 0.5321 | -1.8% |

**数 % 精度には解像度 60 以上が必要。** 3.0µm 画素の 3x3 セル（9 x 9 x 11µm）を
解像度 60 で解くと、鏡映対称性込みで約 48M ボクセル、1 本あたり 1.5〜2 時間。

3.0µm セルでの混色率も未収束:

| 解像度 | 混色率 |
|---|---|
| 30 | 2.24% |
| 45 | 1.64% |

## 実行状況（2026-09-08）

`meep/run_res60.sh` で以下を順に実行中:

1. 解像度 45、低屈折率グリッド有り（収束確認用）
2. 解像度 60、低屈折率グリッド有り（本命）
3. 解像度 60、グリッド無し（グリッド効果の検証）

共通条件: 3.0µm ピッチ / Si 6.0µm / FDTI 全深 0.20µm 幅 / 空乏層 3.0µm /
ML サグ 0.80µm / CFA 0.90µm / **オンチップ IRCF 0.30µm** / 550nm / 中心開口 /
`mpirun -np 14`。

DTI は**酸化膜（n = 1.46）の実誘電体**として入れてあるので、BPM が扱えない反射がここで入る。

**結果が出たら本ページに追記すること。** 現時点では [[30-results]] の BPM 値が唯一の根拠。

## 出力の使い方

`.npz` に `G`（bxsim の拡散格子上、裏面から z 増加、セルあたり吸収割合）が入るので、
そのまま随伴拡散ソルバに渡せる。

```python
import numpy as np
from bxsim import PixelStack, diffusion
d = np.load("meep/out/fdtd_550nm_center_grid_r60.npz")
st = PixelStack(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, ...)
K = diffusion.collect(d["G"], diffusion.collection_map(st), st)
```
