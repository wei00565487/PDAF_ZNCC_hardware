# bxsim — Bayer CMOSイメージセンサの混色(クロストーク)シミュレータ

有償の光学/デバイスシミュレータ(Lumerical FDTD, Zemax, Synopsys Sentaurus, Silvaco 等)を
使わずに、Bayer配列CMOSイメージセンサの**混色**を定量評価するための Python パッケージです。
依存は numpy / scipy / matplotlib のみ。

混色を、設計で効くレバーが違う3つの成分に**分離**して出します。

| 成分 | 物理 | 本ツールでの扱い |
|---|---|---|
| **分光クロストーク** | カラーフィルタ(CFA)の透過帯の重なり、NIR漏れ | `materials.cfa_transmittance` の分光透過率 |
| **光学クロストーク** | マイクロレンズの集光不足・回折、斜入射での隣画素への漏れ込み | 角スペクトル法(BPM)によるスカラー波動伝搬 |
| **電気クロストーク** | Si深部で生成した少数キャリアの横方向拡散 | 定常拡散方程式の**随伴解**で収集確率マップを算出 |

---

> **知見は `wiki/` に整理してあります。** 数値を引用する前に
> [wiki/70-assumptions.md](wiki/70-assumptions.md)(仮定値と感度)と
> [wiki/60-roadmap.md](wiki/60-roadmap.md)(未検証事項)を読んでください。
> 索引は [wiki/index.md](wiki/index.md)。

## 1. すぐ動かす

```bash
cd C:\Users\tachi\Documents\bayer-crosstalk-sim
python scripts/selftest.py      # 物理の健全性チェック(約10秒)
python scripts/run_spectral.py  # 本体デモ(約2〜3分)
python scripts/run_cra.py       # 斜入射(CRA)スイープ(約20秒)
python scripts/run_image.py     # ISP側のコスト(彩度低下とCCMノイズ増幅)(約20秒)
```

## PDAF ZNCC hardware implementation

本リポジトリには、12Mpixel Dual-PD センサ（4000x3000、60 fps、4 pixel/beat、180 MHz）を対象にした、水平走査型 ZNCC 位相差検出ハードウェアの検討成果も含む。32x24 タイル、17 視差候補、4 位相、673-bit 統計ワード、17 バンク同期 SRAM、および共有正規化器を中心に、RTL、Yosys 正規化、Nangate45 参照の OpenROAD 評価をまとめている。

- RTL: `rtl/`
- 設計検証・合成レポート: `wiki/dual_pd_zncc_opt_synthesis_report.md`
- ハードウェア設計Wiki: `wiki/80-dual-pd-zncc-hardware.md`
- ルート化可能な SRAM プロキシ LEF 生成: `scripts/make_nangate45_routeable_sram_lef.py`
- OpenROAD 設定: `rtl/physical/dualpd_pipe1_32col_config.mk`

OpenROAD の P&R は、ファウンドリ SRAM コンパイラが利用できないため、Nangate45 標準セルとルート可能な SRAM プロキシ LEF を用いた評価である。生成データベース、ログ、波形、ベンダーの OpenROAD-flow-scripts クローンはサイズと再現性の観点から Git 管理対象外とし、手順と評価結果を Wiki に記録している。

出力は `out/` に PNG と CSV で入ります。

最小の使い方:

```python
from bxsim import PixelStack, Simulator

st  = PixelStack(pitch_um=0.8, si_thickness_um=3.0,
                 dti_enabled=True, dti_depth_um=2.6, pd_depth_um=1.0)
sim = Simulator(st)
K   = sim.kernel(550.0)          # 3x3(または n_pix x n_pix)のクロストークカーネル
print(K / K.sum())               # 自画素・隣接画素への配分
```

`K[i, j]` は「中心画素のCFAセルを通過した光子のうち、オフセット `(i-2, j-2)` の
フォトダイオードで信号になった割合」です。

---

## 2. 物理モデル

### 2.1 スタックと光伝搬(`bxsim/optics.py`)

裏面照射(BSI)を想定し、上から
**空気 → マイクロレンズ → 平坦化膜 → CFA → ARC(SiN) → Si(裏面 z=0、表面 z=t にPD)**
の順に、**角スペクトル法**で面から面へ場を伝搬させます(光線追跡ではなく回折計算なので、
サブミクロン画素のようにマイクロレンズの f/# が小さい領域でも成立します)。

- マイクロレンズ: 球面キャップの薄膜位相素子。物理量である**サグ量** `ml_sag_um` で
  指定し、曲率半径 `R = (a² + h²)/2h`(`a` = 画素の半対角)を導出します。
  0.8 µm 画素・サグ 0.35 µm では f ≈ 1.54 µm に対しスタック高が 0.65 µm なので
  **アンダーフォーカス**になります。これは実際の微細画素で起きていることそのものです。
- ARC は1層の特性行列法で垂直入射の透過率を厳密計算(550 nmで T≈0.96、
  ARCなしのベアSiなら 0.68)。
- Si 内は複素屈折率 `n + ik`(`k = αλ/4π`)のまま角スペクトル伝搬させ、
  各スラブの吸収 `|E|²(1 − e^{−α dz})` を積算して生成率分布 `G(x,y,z)` を作ります。
- 混色の帰属は「**光子はちょうど1つのCFAセルを通る**」という厳密な分解に基づき、
  中心セルだけを開口させて計算します(周期配列なので全セル分の和が全体になる)。

### 2.2 キャリア輸送(`bxsim/diffusion.py`)— 随伴法

素直にやると照明条件ごとに連続の式を解き直すことになりますが、ここでは**随伴問題を1回だけ**
解きます。少数キャリアの定常方程式

```
D∇²n − n/τ + G = 0,   n = 0(PD空乏層内),  D ∂n/∂ν + S n = 0(再結合面)
```

に対し、随伴場 `u` を

```
D∇²u − u/τ = 0,   u = 1(対象PD内), u = 0(他のPD内),  D ∂u/∂ν + S u = 0
```

と定義すると、Greenの恒等式から**厳密に**

```
J_c = ∫ G · u_c dV
```

が成り立ちます。つまり `u(x,y,z)` は「その点で生成したキャリアが対象PDに収集される確率」
そのものです。配列は周期的なので、他のPDの `u` は横方向シフトで得られます。
結果として **1回の線形ソルブで、全波長・全入射角・全CFA色のカーネルが出せます**。

有限体積法 + 対称行列 + 共役勾配法(Jacobi前処理)で解いています。

**PDは点接触ではなく体積(空乏層)としてモデル化**しています(`pd_depth_um`)。
これが本質的で、DTI 深さが空乏層に届くかどうかで電気クロストークが劇的に変わります。

### 2.3 DTI

- 電気的には、`dti_depth_um` までの画素境界面をゼロフラックス境界にします。
- 光学的には、BPM の各ステップで振幅マスクを掛ける = **吸収壁**として扱います。
  実際の酸化膜充填DTIは光を**反射**して自画素に戻すので、QE はここで過小評価されます
  (クロストーク抑制の傾向は正しく出ます)。反射まで含めたい場合は §4 の Meep を使ってください。

---

## 3. 検証

`scripts/selftest.py` が以下を確認します(すべてパスします)。

| 検証項目 | 結果 |
|---|---|
| Si の光学定数(n, α, 吸収長) | 450 nm で 0.35 µm、850 nm で 18.7 µm |
| 全開口照射時の Si 吸収量 vs Beer-Lambert 解析解 | **4桁一致**(例: 650 nm で 0.5458 対 0.5458) |
| 収集確率の**確率保存**(全PDの `u` の総和 = 1) | min = max = 1.000000 |
| `u ∈ [0, 1]` | OK |

エネルギー保存と確率保存が独立に成立しているので、光学側と輸送側それぞれの離散化が
正しく閉じていることが確認できます。

---

## 4. 得られた結果(0.8 µm画素・Si 3.0 µm・空乏層 1.0 µm・PD開口率 0.75)

`out/crosstalk_summary.csv` より:

| 構成 | QE@550 | XT@450 | XT@550 | XT@650 | XT@850 | 色純度 R/G/B | CCMノイズ利得 R |
|---|---|---|---|---|---|---|---|
| DTIなし | 75.3% | 93.1% | 79.4% | 76.0% | 77.9% | 0.19 / 0.64 / 0.42 | 13.7 |
| BDTI 1.5 µm | 68.9% | 73.3% | 63.6% | 57.4% | 55.7% | 0.20 / 0.66 / 0.45 | 9.3 |
| BDTI 2.6 µm | 68.2% | **7.7%** | **10.1%** | **9.2%** | **6.6%** | 0.76 / 0.95 / 0.91 | 1.37 |
| FDTI 3.0 µm | 68.2% | 7.7% | 10.0% | 9.0% | 6.3% | 0.76 / 0.95 / 0.91 | 1.37 |

読み取れること:

1. **支配要因は電気クロストーク**。DTIなしの550 nmでは混色 79.4% のうち 60.4 pt が拡散由来、光学由来は 15.0 pt。ただし850 nmでは光学由来が 38.6 pt まで増える(回折と吸収長)。
2. **BSIでは青が最も電気混色しやすい**。裏面直下(0.35 µm)で生成したキャリアが PD まで
   3 µm 近く拡散するため。表面照射の直感と逆になる点は注意。
3. **DTI は「深さ」ではなく「空乏層に届くか」で決まる**。BDTI 1.5 µm は トレンチ底と空乏層上端の
   間に 0.5 µm の隙間が残るためほぼ無効(XT 57〜73%)。2.6 µm にして空乏層とオーバーラップ
   させた瞬間に電気クロストークが消え、残るのは光学分の 7〜10% だけ。FDTI にしても
   そこから先の改善はほぼゼロ = **設計上のスイートスポットが見える**。
4. **光学クロストークは長波長ほど大きい**(回折 ∝ λ、かつ吸収長が伸びて横に広がるため)。
5. ISP コスト(`out/fig6_image.png`): 中間グレーで 2000 e⁻ のとき、混色なしの色ノイズ
   35 e⁻ に対し、FDTI で 48 e⁻、DTIなしでは CCM 利得 13.7 倍が効いて **483 e⁻**。
   混色は「色が濁る」だけでなく、補正した瞬間に**ノイズ問題に化ける**ことが定量化できます。

CRAスイープ(`out/fig5_cra.png`)では、30° 入射で自画素比率が 90.8% → 80.6%(650 nm)に低下し、
+x 方向への偏り(=色シェーディングの正体)が 13.5% まで増えます。
マイクロレンズシフト −0.157 µm を入れると 30° で 86.4% まで回復する一方、
軸上では 90.8% → 87.7% に劣化する、という実機どおりのトレードオフが再現されます。

---

## 5. モデルの限界と、厳密化の道(すべて無償)

BPM は **スカラー・一方向**近似です。以下は原理的に扱えません。

- 偏光依存、ベクトル集光効果
- スタック内の多重反射・干渉(裏面反射、金属配線反射)
- 酸化膜DTIの**反射**(本ツールは吸収壁として扱うので QE を過小評価)
- 回折格子的な構造(W-grid、低屈折率グリッド、インナーレンズ)

これらが効く条件では `meep/pixel_fdtd.py`(MIT Meep、無償・オープンソース)を使ってください。
同じスタックを 3D FDTD で解き、`bxsim` と同じグリッドで吸収分布を `.npz` に書き出すので、
そのまま §2.2 の拡散ソルバに食わせられます。

```bash
# WSL / Linux
conda create -n mp -c conda-forge pymeep pymeep-extras && conda activate mp
python meep/pixel_fdtd.py --wavelength 550 --resolution 40 --cell-pixels 3
```

> Meep は WSL の micromamba 環境で実行します。環境定義は `meep/environment.yml`、
> BPMとの収束比較は `meep/run_validation.sh` と `scripts/compare_meep_bpm.py` です。

無償で使える他の選択肢:

| ツール | ライセンス | 向き |
|---|---|---|
| **Meep** | GPL | 3D FDTD。画素スタック全体の厳密解。本命 |
| **Tidy3D client** | 有償(クラウド課金) | 参考まで。無償枠は限定的 |
| **RETICOLO / S4** | 無償(RCWA) | 周期構造(グリッド、格子)の高速解析 |
| **Devsim / Charon** | オープンソースTCAD | ドリフト拡散を自己無撞着に解きたい場合 |
| **PVLighthouse / OPAL** | 無償Web | Si光学定数・ARC設計の検算用 |

---

## 6. 主なパラメータ(`bxsim/stack.py: PixelStack`)

| 名前 | 既定値 | 意味 |
|---|---|---|
| `pitch_um` | 0.80 | 画素ピッチ |
| `n_pix` | 5 | シミュレーション配列サイズ(奇数、横方向は周期境界) |
| `ml_sag_um` | 0.35 | マイクロレンズのサグ量 |
| `ml_shift_um` | 0.0 | CRA補正のレンズシフト(**+x に傾いた光には負の値**) |
| `t_ml_to_cfa_um` / `t_cfa_um` / `t_cfa_to_si_um` | 0.05 / 0.50 / 0.10 | 層厚 |
| `t_k_cfa_um` | `None` | K/IRセルだけ異なるCFA総厚（例: R+B積層なら各0.90 µmで1.80 µm） |
| `si_thickness_um` | 3.00 | Si(エピ)厚 |
| `dti_enabled` / `dti_depth_um` / `dti_width_um` | True / 2.6 / 0.10 | DTI |
| `dti_blocks_light` | True | 光学的に吸収壁として扱うか |
| `pd_fill` / `pd_depth_um` | 0.75 / 1.00 | PD開口率と空乏層深さ |
| `diff_coeff_cm2s` / `lifetime_us` | 25 / 10 | 電子の拡散係数と寿命 |
| `s_back_cm_s` / `s_front_cm_s` | 200 / 0 | 表面再結合速度 |
| `dx_opt_nm` / `dz_opt_nm` | 25 / 25 | 光学グリッド |
| `dx_diff_nm` / `dz_diff_nm` | 50 / 50 | 拡散グリッド(光学グリッドの整数倍であること) |

自社の実測データがある場合の差し替え:

- Si の n, α → `materials.load_si_csv("si.csv")`(`wavelength_nm,n,alpha_per_cm`)
- CFA 透過率 → `materials.cfa_transmittance` を実測カーブ補間に置き換え(ここが色再現の精度を一番左右します)

---

## 7. ファイル構成

```
bxsim/
  materials.py   Si の n・α(Green 2008 準拠)、CFA/IRCF 透過率、ARC の特性行列
  stack.py       画素スタックの幾何・材料・数値パラメータ
  optics.py      角スペクトル法BPM → Si内生成率分布 G(x,y,z)
  diffusion.py   随伴拡散ソルバ → 収集確率マップ u、カーネル合成
  crosstalk.py   波長/角度スイープ、分光応答、3x3混色行列、CCMノイズ利得
  plotting.py    図のヘルパ
scripts/
  selftest.py    物理検証(まずこれを実行)
  run_spectral.py  本体デモ(fig1〜4, CSV)
  run_cra.py       斜入射スイープ(fig5)
  run_image.py     ISPコストのデモ(fig6)
meep/
  pixel_fdtd.py  Meep による3DベクトルFDTD（WSL環境を再構築・検証済み）
out/             生成物
```
