# Dual-PD ZNCC 4候補スロット構成の合成結果

## 対象

`dual_pd_zncc_opt_core_synth_top` は、17候補を4候補スロット×5グループに分け、4位相の統計を位相単位に分離し、候補生成・統計更新・SRAMファームを別モジュールにした合成検証用トップである。SRAMファームはブラックボックスとして扱い、SRAMビヘイビアモデルの論理展開がコア評価を汚染しないようにしている。

## 実行内容

Yosys 0.62で次を実行した。

```text
read_verilog -sv -DSYNTHESIS ...
read_verilog -sv -lib rtl/dual_pd_zncc_stats_4phase_farm_bb.sv
hierarchy -check -top dual_pd_zncc_opt_core_synth_top
synth -top dual_pd_zncc_opt_core_synth_top -run coarse:coarse -noalumacc -noshare
stat; check; write_rtlil ...
```

## 結果

- RTLコンパイル: PASS
- Yosys coarse synthesis: PASS
- `check`: `Found and reported 0 problems`
- RTLIL: `/tmp/dual_pd_zncc_opt_core_coarse.il`（約1.5 MB）
- 階層を含むセル数: 1,509
- 階層を含むwire数: 1,837
- wire bits: 996,513
- 加算器: 223
- 乗算器: 50
- 除算器: 1（現行プロトタイプの正規化部）
- レジスタ系: `$adff` 15、`$adffe` 36
- 統計SRAM: `dual_pd_zncc_stats_4phase_macro_farm` 1個のブラックボックス

## 後段セルマッピングについて

Nangate45の標準 `synth` のfine/techmap段階では、広い加算器が幅ごとのFA/LCUテンプレートへ展開され、処理時間とメモリ使用量が急増した。したがって今回の完了判定は、算術演算子を保持したcoarse合成＋RTLIL生成＋構造チェックまでとする。面積・タイミングの最終値を得るには、加算器/乗算器を明示的なパイプライン境界で分割し、SRAMマクロのLEF/Libertyと組み合わせて段階的にセルマッピングする必要がある。

### P&R試行結果

OpenROAD-flow-scriptsで、演算ラッパ（Brent–Kung加算器、Booth乗算器）と階層保持を組み合わせた2構成を試行したが、どちらもYosysのfine/techmap段階で停止し、OpenROADのfloorplan/place/CTS/route段階へは到達しなかった。

従って、この最適化RTLに対する最終配置配線面積、WNS/TNS、配線完了判定は未取得である。取得済みの1,509セル等の値はcoarse合成の構造統計であり、P&R面積ではない。

P&Rへ進むには、4×672-bit統計更新を位相・候補ごとのパイプラインへ分割し、`add_stats`を168-bit単位の段階加算へ変更する必要がある。さらに12×12乗算を共有乗算器1〜2個へ置換し、5候補グループを入力FIFOで保持して入力ビートと時間的に分離する。

## 注意事項

この最適化RTLはアーキテクチャ合成検証用であり、既存の完全機能版と同値であることはまだ確認していない。特に、5グループを同一入力ビートに対して時分割保持する入力FIFO、CFAの行パリティ、候補窓の境界処理は次の機能検証段階で補強する必要がある。

## 4画素/beat・180 MHz シリアルP&Rプロトタイプ

`dual_pd_zncc_pipe1_phys_top` は、4画素/beatの入力インターフェースを維持しつつ、17候補×4位相を1個の更新器で時分割するP&R収束用プロトタイプである。統計語は673 bit（epoch 1 bit + 4相×168 bit）で、SRAMは32ワード、1R1Wの抽象マクロとした。現行の物理トップではbank0の4スライス（192 bit×3、104 bit×1）だけを接続し、未使用の33 bankは論理最適化で除去される。

### 完了した工程

- RTLIL生成、Yosys正規化、階層チェック: PASS
- OpenROAD synthesis / floorplan / macro placement / tapcell / PDN / global placement / detailed placement / CTS: PASS
- CTS後のクロック評価: `clk period_min = 4.34 ns`、`fmax = 230.57 MHz`
- CTS後のsetup: `WNS = 0.00 ns`、`TNS = 0.00 ns`
- CTS後のhold: 最悪slack `+0.09 ns`（違反なし）
- 合成セル面積: `265,406.365 um^2`
- CTS後の配置面積: `265,706 um^2`（約0.266 mm^2、4スライス構成）
- CTS後のOpenROAD power metric: total `0.0440677`（内部 `0.0213453`、switching `0.0222241`、leakage `0.00049826`。単位は使用したLiberty/ORFSのpower設定に従う）

### SRAM面積

FreePDK45の代替SRAMマクロLEF/Libertyの面積は、1 bankあたり約`242,613 um^2`である。34 bankへ拡張した場合のSRAM面積は約`8.249 mm^2`となる。したがって、現行ロジックのP&R面積を加えた面積見積りは、

```text
logic P&R proxy       0.266 mm^2
34-bank SRAM          8.249 mm^2
--------------------------------
combined estimate     8.515 mm^2
```

である。これはSRAMマクロの面積を実LEFから加算した値であり、34 bankを実際に配置配線した値ではない。

### route未完了の理由

FreePDK45由来マクロのmetal3信号ピン（例: `din0[0]`）がNangate45の配線トラック/ピンアクセス条件と一致せず、OpenROAD detailed routerが `DRT-0073 No access point` で停止する。製造グリッドを0.0025 umへ合わせたtech LEFでもこのpin access問題は解消しなかった。従って上記は「CTS完了のP&Rプロキシ」であり、完全なGDS/DRC/LVS完了値ではない。

### 再実行用RTL

実SRAMのpin accessに依存しないロジック単体P&R用に、`dual_pd_zncc_pipe1_logic_top.sv` と `dualpd_pipe1_logic_config.mk` を追加した。これは32×673 bitのビヘイビアメモリでロジック本体を配置配線するための検証トップで、最終製品面積のSRAM代替には使用せず、ロジック配線・タイミングの測定に限定する。

## Nangate45配線規則対応LEF

SRAM compiler/IPがないため、実メモリ回路をNangate45で再生成したものではなく、P&R pin access検証用のrouteable abstract LEFを生成した。`scripts/make_nangate45_routeable_sram_lef.py` は、元LEFのマクロ外形、ピン名、方向、ピン数を保持し、信号ピンの抽象形状をNangate45配線トラックにアクセスしやすい0.28 um窓へ拡張する。LibertyとGDSは元FreePDK45のままなので、これはOpenROAD配線検証用であり、製品テープアウト用のSRAM IPではない。

生成物:

- `rtl/physical/work_nangate45_routeable/zncc_stats_32x192_1rw1r_routeable.lef`
- `rtl/physical/work_nangate45_routeable/zncc_stats_32x104_1rw1r_routeable.lef`
- `rtl/physical/dualpd_pipe1_phys_routeable_config.mk`

元LEFとの機械検証では、192-bit型で外形、ピン数593、RECT数1835が一致している。routeable LEFでroute段階が通っても、GDS/Libertyと抽象LEFの整合性が取れていないため、最終DRC/LVSの成功を意味しない。最終的には、Nangate45互換のSRAM compilerまたは同一プロセスのLEF/Liberty/GDS/OASIS一式が必要である。

## 推奨低メモリ構成への置換

60 fps入力を停止しない前提で、水平17画素履歴と32エリア列の統計保持を明示したトップを追加した。

- `rtl/dual_pd_zncc_pipe1_32col_top.sv`
- `rtl/dual_pd_zncc_stats_32col_macro_farm.sv`
- `rtl/physical/dualpd_pipe1_32col_config.mk`

1ワードは673 bit、深さ32で、1候補・4位相の統計を保持する。17候補を分離するため17バンクとし、統計容量は`32×17×673 = 366,112 bit`（約365.6 kbit）である。水平履歴は16画素＋4画素beatで、4lane換算の履歴量は約1,632 bitである。SRAMマクロは既存の3×192 bit＋1×104 bitを1バンクとして17バンク再利用する。SRAMマクロ面積の目安は`17×242,613 = 4,124,422 um^2`（約4.124 mm^2）である。

現行の`pipe1`演算器は17候補×4位相を時間共有するため、`in_valid`を毎サイクル受け続ける完全なラインレート設計ではない。センサの連続入力を吸収するには、別途1行FIFO（12-bit L/Rで約96 kbit、ping-pongで約192 kbit）または外部フレームバッファを前段に追加し、FIFO overflowを禁止するスケジューラが必要である。今回の置換は統計SRAMを34-bankから17-bankへ明示的に縮小したものであり、候補統計の混在を防ぐため候補をbank selectorとして追加した。次工程で入力FIFOとバックエンド処理遅延を結合する。

この17バンク化後のRTLに対して、前節の4スライス配置・面積・CTS値をそのまま適用してはならない。17バンクで再合成・再配置が必要であり、前節の0.266 mm²は旧4スライスP&Rプロキシの値として扱う。

### 17バンク版の実行状況（2026-09-29更新）

Docker版 `openroad/orfs:latest` を用いてYosys/OpenROADを復元し、`FLOW_VARIANT=bank17`で17バンク版を再実行した。Yosys canonicalize/technology mapping、RTLIL生成、構造checkはPASSした。OpenROADもfloorplan、68 SRAMスライス（17バンク×4スライス）のmacro placement、tapcell、proxy PDN、global/detailed placement、CTSまで完了した。

合成・CTS時点の実測値は以下である。

- 合成インスタンス面積: `4,174,989 um^2`
- CTS後インスタンス面積: `4,236,433 um^2`（約`4.236 mm^2`）
- マクロ面積: `4,124,320 um^2`（68スライス、約`4.124 mm^2`）
- コア面積: `11,923,300 um^2`、利用率約`35.53%`
- CTS後 `WNS=-1.19 ns`、`TNS=-4097.95 ns`、setup違反10800件、hold違反0件
- CTS後のclock解析上の最小周期: `4.77 ns`、`fmax=209.64 MHz`
- OpenROAD推定power: 合計`0.177171`（internal`0.124134`、switching`0.0494897`、leakage`0.00354686`）。これはmacro電力モデルを含むproxy値で、単位は使用Liberty/ORFS設定に依存する。

詳細配線は未完了である。最初のmetal1化LEFはmacro全面の`OBS metal1`と競合し、次にmetal3へ戻して製造グリッド（0.005 um）へスナップしたLEFを使用した。その結果、off-gridエラーは解消し、pin access処理は開始したが、`din0[0]`について`DRT-0073 No access point`で停止した。したがって最終route、DRC/LVS、route後タイミングは未取得である。

使用した主な生成物:

- `rtl/physical/openroad-flow-scripts/flow/results/nangate45/dual_pd_zncc_pipe1_32col_top/bank17/1_1_yosys_canonicalize.rtlil`
- `rtl/physical/openroad-flow-scripts/flow/results/nangate45/dual_pd_zncc_pipe1_32col_top/bank17/4_1_cts.odb`
- `rtl/physical/openroad-flow-scripts/flow/reports/nangate45/dual_pd_zncc_pipe1_32col_top/bank17/4_cts_final.rpt`
- `rtl/physical/openroad-flow-scripts/flow/logs/nangate45/dual_pd_zncc_pipe1_32col_top/bank17/5_1_grt.log`

route完了には、metal3ピン開口を持ち、配置・配線トラック・manufacturing grid・Liberty・GDSが同一Nangate45相当プロセスで整合したSRAM macroが必要である。現行のLEFはpin accessを検討するproxyであり、製品用SRAM IPではない。

### Proxy macro改善後のP&R試行

proxy LEFを次のように改善した。

- metal3信号pin周辺のOBSを除去し、pin access領域を確保
- pin形状を0.005 um manufacturing gridへスナップ
- vdd/gndにmetal4のproxy portを追加
- global routeのcongestion iteration数を`GRT_CONGESTION_ITERS`で制御可能に変更
- コア利用率を35%から30%、placement densityを0.30から0.25へ変更

改善後は、pin accessが以下の条件で完了した。

```text
macroValidPlanarAp = 2190
macroNoAp           = 0
stdCellPinNoAp      = 0
```

30%利用率条件ではglobal routeの最終混雑が、従来の総congestion 231から139へ低下した。allow-congestion条件ではroute guideと`5_1_grt-failed.odb`が生成され、総wirelengthは`18,726,104 um`であった。ただし、残存congestionがあるためOpenROADはglobal routeを成功扱いにせず、続くpost-route `repair_design`もproxy macroの過大な容量モデルにより長時間化したため停止した。従ってdetail route、fill、route後STAは未完了である。

この結果から、ファウンドリー情報なしで評価可能な範囲は、RTLIL、合成、macro配置、CTS、pin access、global route混雑比較までとする。detail route以降を完了させるには、SRAM Libertyのpin capacitanceを実macro相当へ校正するか、proxy専用に遅延・容量を抑えたLibertyを別途用意する必要がある。
