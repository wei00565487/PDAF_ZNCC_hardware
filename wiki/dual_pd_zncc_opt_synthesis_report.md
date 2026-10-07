# Dual-PD ZNCC 4候補スロット構成の合成結果

## RGGB疑似輝度ZNCCの実装検討（2026-09-30）

性能評価wikiの方式に合わせ、4相独立統計から2×2 RGGBセルのR+G+G+B和を使う単一統計面へ移行する設計案を仕様書へ記録した（[固定幅・SRAM・ラインバッファ仕様](81-dual-pd-zncc-rtl-spec.md#10-疑似輝度znccへの移行案ユーザー指定の評価方式)）。12-bit RAW、125×125 raw-pixel area、cell-center割当ての仮定では統計wordは673 bitから185 bit（epoch含む）へ縮小し、統計SRAMの論理bitは約72.5%減る見積もり。ラインメモリと疑似セルFIFO込みの論理bitは約35.9%減だが、既存32×192 proxy macroをそのまま1000深さにbank化すると端数幅で合計497,664 physical bitとなり、現行369,920 bitより増える。狭幅・深深度SRAM IPまたはメモリ構成の再設計が重要。

前処理RTL `dual_pd_zncc_pseudoluma_pair4` と同期1RW SRAM adapter `dual_pd_zncc_pseudoluma_linebuf4` を追加。Icarus Verilogで行メモリread/write遅延、2×2セル和、偶数行での出力抑止、mask処理、および125画素area境界の水平/垂直cell-center割当てをPASS確認した。Yosys 0.68でadapter+前処理のflatten synthesisも完了（0 structural problem、1,218 generic cells）。この値はadapterと前処理だけで、行SRAM macroの面積を含まない。まだ疑似輝度統計器/スコアラ/SRAMファームへの接続、固定小数点ZNCCの参照モデル、フルフレーム境界・タイル統計検証、新全体構成のP&Rは未実施。数値評価は64×64 areaであり、125画素境界を含む実データ再評価も必要。

### pooled moment/scorer/SRAM単体RTL（2026-09-30）

- `dual_pd_zncc_pooled_moment_accum`: 184-bit moment recordのload/accumulateをIcarusでPASS。最大想定3,969 cellをfull-scale入力してsum/count全fieldのoverflowなしも確認。Yosys 0.68 flatten synthesis: 4,061 generic cells、check 0 errors。
- `dual_pd_zncc_stats_pooled_macro_farm`: 17×32 bankを186-bit proxy wrapperに接続。185 logical bits（184 moment+epoch）をpadしてreadback/isolation test PASS。
- `dual_pd_zncc_scorer_pooled`: 17候補を逐次平方根・除算する単一面scorer。既知統計値でQ1.15 peak、Q4.4=+0.5 px補間、8-bit quality=199を確認。Yosys coarse synthesis/RTLIL/checkはPASS（738 cells、13 `$mul`、3 `$div`）。flattened generic `synth`は2分超で完了せず停止し、mapped area/STAは未取得。
- 以上5つの新規単体testbench（pair4, linebuf4, pooled accumulator, pooled scorer, pooled SRAM farm）は全てPASS。まだこれらのblock間配線、±8-cell candidate window、500×60-bit順序保持pair FIFO、tile-row SRAM read/accumulate/write schedulerは未実装。従って統合機能・フレームレート・面積・電力の合格を意味しない。

## 逐次コアの行内2相更新軽量化（2026-09-30）

`dual_pd_zncc_stream_stats_4phase_pipe1_phys.sv` の逐次スケジューラを変更し、1行の処理ではBayer相のうち当該行に対応する2相だけを更新する。行末で`y_parity`を反転し、統計語内の位相番号を次行の相ペアへ進める。17候補は維持し、各位相の統計フィールドと有効ペアcountもそのまま保持する。

countをSRAMから省く案は採用しなかった。有効マスクと視差オーバーラップ境界により有効ペア数が変化し、countはZNCC正規化に必要な統計値だからである。統計語幅は673 bitのままなので、17 bank×32 wordの論理容量366,112 bit（約357.5 Kibit）とSRAM本体面積は変わらない。

変更後の逐次スケジュールは1入力ビートあたり17×2=34回の候補相更新となり、旧17×4=68回から半減する。Yosys 0.68で`hierarchy -check`、`proc`、`check -assert`を実行し、0 structural problemsを確認した。続けてgeneric `synth -flatten`も完了した。これは機能等価性・Nangate45 mapped area・PPAの検証ではない。サイクル精度シミュレーションと活動率ベースの電力測定は未実施である。

このトップは1ビートの処理に34クロックを使うため、60 fpsの4 pixel/beat連続入力を受け切るラインレート設計ではない。`in_valid`がbusy中に来ても保持するready/FIFOがない。この変更は逐次プロトタイプの相更新を半分にしたものであり、連続入力要件を満たした結果とは扱わない。実センサ帯域へ適用するには、複数候補更新レーンまたは行FIFOを含めて再スケジュールする必要がある。

### 行内2相版の機能検証・物理実装状況（2026-09-30）

- Icarus Verilogの`tb_dual_pd_zncc_pipe1_two_phase`で、偶数行相0/1・奇数行相2/3の更新を確認（PASS、even=20 / odd=20）。検証幅は`FRAME_W=TILE_W=4`の小規模ケースであり、全画面・マスク境界を覆うものではない。
- Yosys 0.68で`hierarchy -check; proc; check -assert; stat`を実行し、構造問題0件。続けてgeneric `synth -flatten`も完了。これはNangate45マッピング面積や機能同値の証明ではない。
- ORFS / Nangate45標準セル + FreePDK45生成SRAMのLEF/Liberty proxyで、synthesis、floorplan、配置、CTS、global routeまで到達。CTS後設計面積は4,240,157 µm²（約4.240 mm²、マクロを含むproxy合計）。配置修復で多数のbufferを挿入しているため、実プロセスの面積予測には使えない。
- 目標周期5.556 ns（180 MHz）に対し、GRTで更新されたclock period 6.352 ns、slack -1.130 ns、endpoint paths 25,544。setupは未達。global routeはcongestion警告付きで、route guideは生成された。
- 詳細配線は保存済みGRT checkpointから実行したが、反復修復後も違反が残ったため停止。第1反復終了時113,904、第2反復終了時13,595、第3反復終了時3,421、第4反復終了時1,296、第5反復終了時944、第6反復終了時823、第7反復開始時点でも違反があり、停止時のclean判定は得ていない。したがって詳細配線完了・DRC clean・最終配線後タイミングは未取得。
- この物理トップは統計更新プロトタイプであり、ZNCC scorer、タイル完成制御、位相差/信頼度の画素サブピクセル出力を統合していない。電力もSAIF/VCD活動率を用いた評価は行っていない。

上記数値は技術的に混在するproxy評価であり、foundry 45 nm製品の面積・電力・タイミングを示すものではない。DRTのshort/spacing違反は、まずLEF/tech LEF/RC定義とSRAM proxy pin/obstruction、電源・信号レイヤー設定の整合性を検証して解消する必要がある。

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

## RGGB pooled ZNCC・2セル/clock演算コア PPA（2026-09-30、逐次化後）

4相ごとに相関を計算せず、各RGGB 2×2 cellの4画素和を1 pseudo-luma値とし、隣接2 cell/clockで17候補の統計を並列更新する構成を追加した。`dual_pd_zncc_pooled_moments17x2`は2レーン×17候補の184-bit統計器、`dual_pd_zncc_scorer_pooled`は候補を逐次正規化しQ4.4位相/Q8信頼度を出す共有scorerである。候補別の2レーン統計はタイル後にfield-by-fieldで合算する。

### サイクル分割と検証結果

180 MHz制約での前回配置後STAの最長経路がscorerのREPORT状態へ集中していたため、後段演算を次のように逐次化した。17候補の最大値走査と第2ピーク走査を1候補/clockで別ステートにし、サブピクセル補間除算をrestoring dividerで反復実行する。confidenceの乗算は段階化し、Q8変換も逐次除算にした。各候補の平方根・ZNCC除算も元の反復実行を維持する。これにより、1周期に全候補の比較・選択・除算を組み合わせる経路をなくし、1タイルの結果レイテンシを増やしてクロック周期を短縮した。1タイル/フレームの出力頻度仕様には影響しない構成だが、RTL topより上流の連続4画素/beat入力からタイル完了までを含むシステム帯域検証ではない。

- 変更後scorerの既知ベクトルテスト: PASS（phase Q4.4=8、peak Q1.15=32767、second=0、confidence=199）。
- Icarusの7テスト（pseudo-luma pair、line buffer、moment accumulator、17候補window、2-cell/clock統計合算、pooled scorer、pooled SRAM farm）すべてPASS。
- Yosys 0.68 RTLIL生成、階層展開、`proc; check -assert` PASS。Nangate45標準セルtechnology mapping PASS。
- OpenROAD Flow Scripts / Nangate45、5.556 ns（180 MHz）制約でfloorplan、global/detailed placement、CTS、global/detailed route、OpenRCX抽出、final reportまで完了。
- Detailed-route DRCは最終0件（途中21,024件から修復）、antenna違反0件。SRAM macroなしの演算コアであり、LVS/製造signoffではない。

### 演算コア実測値

| 指標 | 結果 |
|---|---:|
| Yosys mapped standard-cell area | 282,742.040 µm² = 0.283 mm² |
| 最終 standard-cell area（fill除外） | 286,420 µm² = 0.286 mm² |
| CTS後 area | 286,420 µm² |
| コア面積 | 806,322.9 µm²、最終利用率 約35.5% |
| clock minimum period / Fmax | 5.25 ns / 190.30 MHz |
| 5.556 ns制約での最終WNS/TNS | 0.00 ns / 0.00 ns（違反なし） |
| final critical-path slack / max data arrival | +0.301 ns / 5.68 ns |
| detailed-route DRC / antenna | 0 / 0 |
| OpenROAD vectorless power | 3.01 W（internal 1.58 W、switching 1.42 W、leakage 0.00564 W） |

180 MHz制約はNangate45 proxy上の最終配線後STAで達成した（190.30 MHz、約5.3%の周波数余裕）。新しい最長経路は`u_scorer.score_idx[0]`から`u_scorer.den2_reg[110]`へ向かう統計正規化準備段で、補間/peak選択経路ではなくなった。余裕は約0.30 nsと小さいため、異なるRC corner、OCV、電圧・温度条件、実SRAM接続、clock uncertaintyを含めた量産条件での達成を意味しない。

電力は入力toggle注釈/VCDなしのOpenROAD vectorless値であり、センサ画像のデータ依存活動率を反映しない。出力された3.01 WとIR解析の最大電圧降下約35%はこの仮定とproxy電源網に強く依存し、電力比較やIR signoffには使用できない。実入力のSAIF/VCD、適切な電源網・デカップリング、プロセスコーナーおよび電圧/温度条件を設定して再評価すること。

### メモリを含む面積の暫定加算

今回のP&R topは演算コア評価用であり、line SRAM、17-bank統計SRAM、候補window/front-endはtopに接続していない。既存routeable LEFの面積から単純加算すると:

| メモリ | マクロ構成 | ビット容量（physical） | 面積 proxy |
|---|---:|---:|---:|
| pooled tile stats | 17 × 32×192 | 104,448 bit | 1.184 mm² |
| 1-line L/R + mask | 32 × 32×104（深さ余り24語） | 106,496 bit | 1.079 mm² |
| 演算コア | Nangate45 final std cells | — | 0.286 mm² |
| 小計 | — | — | 約2.549 mm² |

ラインバッファは論理104,000 bit（1000×104）、統計は論理100,640 bit（17×32×185）だが、上表はマクロのword幅/深さ切上げを含める。SRAM macro LEF/Liberty/GDSはFreePDK45ベースproxyであり、Nangate45演算セルと混在させた2.549 mm²は見積り用の混成比較で、同一processの実装面積・signoff値ではない。candidate windowとtile制御、clock/power配線の増分も未計上。従って現時点の「全体面積」は確定せず、2.549 mm²は既知ブロックだけの下限寄り積算である。1-cell/cycle方式を使う場合はさらに約500×60 bit FIFOが必要となり、32×104 proxy macro 16個を仮定した追加面積は約0.540 mm²。現在のPPA topはFIFOを避ける2-cell/clock入力を前提とする。

PPA生成物（OpenROAD 2026-09-30実行）:

- `rtl/physical/pooled_compute_ppa/synth_stat.txt`
- `rtl/physical/pooled_compute_ppa/6_finish.rpt`
- `rtl/physical/pooled_compute_ppa/6_report.log`
- `rtl/physical/pooled_compute_ppa/5_2_route.log`
- `rtl/physical/pooled_compute_ppa/6_final.odb`（最終OpenDB、約261 MB / 249 MiB）

## pooled統計SRAM＋共有スコアラ RTL-to-GDS（2026-10-07）

32-zone列のpooled統計を17個のSRAM bankに保持し、旧zone行を読み出して共有逐次スコアラへ渡すバックエンドを、Nangate45標準セル＋FreePDK45由来OpenRAMマクロの研究用混成proxyでRTL-to-GDS評価した。各zoneアドレスは17 bankすべての旧データをSRAM read portがサンプルした後に再利用可能となる。これにより次zone行の書込みと前zone行のスコア処理を重ね、統計用SRAMを二重化せず17マクロに抑える。

### 容量と面積

| 項目 | 結果 |
|---|---:|
| SRAM構成 | 17個 × 32×192 bit、各1RW1R |
| 論理容量 | 17×32×185 = 100,640 bit（184-bit record＋epoch/padding） |
| マクロ物理容量 | 104,448 bit（12.75 KiB、wordあたり7 bit未使用） |
| SRAMマクロ面積 | 1,183,671.68 µm²（1.184 mm²） |
| 最終標準セル面積 | 136,374 µm²（0.136 mm²） |
| 合計インスタンス面積 | 1,320,046 µm²（1.320 mm²、SRAM比率約89.7%） |
| コア面積 | 3,653,774.67 µm²（3.654 mm²、目標利用率35%） |

### タイミング・配線・検証

- Yosys synthesisからOpenROAD floorplan、placement、CTS、global/detailed route、OpenRCX SPEF抽出とGDS mergeまで完了。KLayoutでLEF/GDS cell対応とorphan cellなしを確認。
- 抽出後setup slack +0.1958 ns、hold slack +0.0835 ns、setup/hold TNS 0。最小周期5.36 ns、Fmax 186.56 MHzで、180 MHz制約をproxy上で満たした。
- 詳細配線後もDRC違反170件が残り、すべてOpenRAM macro上/内部のmetal4 short。したがってGDSはDRC cleanではない。
- PDN/IR解析は未完了。Nangate45側の電源網でOpenRAMの小文字`vdd`端子・電源形状が未接続扱いとなったため、最終STAはIR解析をスキップして実行。
- OpenROAD vectorless powerは入力活動率・実センサ波形なし、巨大なトップI/O境界のため、60 fpsセンサ電力として無効。数値を電力見積もりに使わない。

### 適用範囲と制限

物理トップは「完成済みzoneの17×184-bit統計値」を受け取るSRAM/score backendであり、RAW L/R入力からのラインバッファ、疑似輝度生成、候補窓、moment accumulatorは未接続である。従ってこの面積・タイミングはセンサから位相差/信頼度出力までの全体RTL結果ではない。また、Nangate45標準セルとFreePDK45 SRAMは同一foundry/process kitではなく、研究用の混成proxyであり、45 nm製品のsignoff値ではない。

実行条件、モジュール構成、生成物パスを含む詳細は[RTL-to-GDSレポート](../rtl/physical/pooled_sram_score_rtl2gds_report.md)を参照。代表生成物は、[物理トップ](../rtl/dual_pd_zncc_pooled_sram_score_top.sv)、[最終GDS](../rtl/physical/pooled_openram_rtl2gds/results/nangate45/dual_pd_zncc_pooled_sram_score_top/base/6_final.gds)、[最終STAレポート](../rtl/physical/pooled_openram_rtl2gds/reports/nangate45/dual_pd_zncc_pooled_sram_score_top/base/6_finish.rpt)、[DRCレポート](../rtl/physical/pooled_openram_rtl2gds/reports/nangate45/dual_pd_zncc_pooled_sram_score_top/base/5_route_drc.rpt)。RTLのzone-row SRAM再利用テストはIcarus VerilogでPASS。
