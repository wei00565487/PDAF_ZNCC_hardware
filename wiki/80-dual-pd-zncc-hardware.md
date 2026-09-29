# Dual-PD ZNCC phase detection: streaming hardware study

## Working assumptions

The concrete mode is 4000 x 3000 active pixels (12 Mpixel) with 2.44 um pitch,
12-bit unsigned L and R samples arriving as one paired raster pixel per input
beat, and a 32 x 24 grid. The active area is 9.76 x 7.32 mm and each tile is
125 x 125 pixels (305 x 305 um). Search is horizontal, integer disparity -8..+8 pixels. Each
candidate uses only overlap inside its own tile; no neighboring tile contributes
samples. Per-candidate mean subtraction and normalization are part of ZNCC.

For disparity d, compare L[y,x] with R[y,x+d]. For each candidate accumulate
`SL, SR, SLL, SRR, SLR, N`. The normalized score can be formed as

```
num = N*SLR - SL*SR
denL = N*SLL - SL*SL
denR = N*SRR - SR*SR
rho = num / sqrt(denL*denR)
```

This avoids per-pixel division and explicit mean subtraction. A practical
implementation first finds the best integer candidate, checks texture energy
and peak uniqueness, then optionally performs three-point parabolic
interpolation. The reference confidence is a bounded separation between the
best peak and the strongest non-adjacent peak; `peak_score` should also be
thresholded because a unique but weak peak is not reliable. Flat tiles return
zero confidence and NaN disparity.

## Memory architecture

Recommended first FPGA/ASIC architecture: a circular SRAM holding one tile-row
band (125 complete raster rows) for both views, followed by a block scheduler
that reads each 125 x 125 tile and runs a time-multiplexed ZNCC engine. The
current band is not overwritten until all 32 tiles have been consumed. Ping-
pong banks let capture of the next band overlap processing of the current band.

At 12 bits per view, one band is:

```
4000 columns * 125 rows * 2 views * 12 bits = 12,000,000 bits = 1.43 MiB
```

Two banks need about 2.86 MiB, excluding ECC, alignment and SRAM interface
padding. Packing each sample into 16 bits simplifies SRAMs but raises this to
16 Mbit per bank (1.91 MiB). A 125-row circular buffer is sufficient because
ZNCC spans the whole tile vertically; no frame store is needed. The active bank
must retain the full band through processing, and the next band must have a
separate write bank to avoid read/write hazards.

The paired views can share a wide SRAM word (`{L,R}`) or use two banks. Two
banks ease independent read scheduling; a packed word saves address/control
logic. Reads should be burst/sequential by tile, with a small local tile cache
so the candidate engine can reuse each row and avoid repeatedly fetching it
from the band SRAM.

## Compute and timing

For a 125 x 125 tile and 17 candidates, interior support is
`sum(125 * (125 - |d|), d=-8..8) = 256,625` sample pairs per tile. Thirty-two
tiles in a band need about 8.21 million pair evaluations. At 30 frames/s, the
24 tile bands arrive at 720 bands/s; at the specified 60 frames/s they arrive
at 1,440 bands/s. This requires about 11.83 billion candidate pair evaluations/s
if each candidate is a separate sample operation. The paired input rate is
720 million L/R pixel pairs/s (12 MP * 60 fps), before blanking and interface
overhead. There are 768 tile results per frame, or 46,080 results/s. These are
active-pixel estimates; the sensor's actual line/frame timing sets the clock
and blanking margin. A single scalar lane is not realistic at that rate.

Exploit the fact that candidate statistics are sums: use a bank of disparity
lanes, SIMD lanes across x, or partial-statistic engines distributed across
multiple clock cycles/accelerators. The minimum lane count follows
`required_pair_rate / (engine_clock * useful_ops_per_cycle)`. The SRAM bandwidth
must be budgeted at the same time: naive replay for every candidate multiplies
tile reads by 17. Prefer loading a row once into local shift registers/BRAM and
forming all candidate pairs from that data. The Y dimension can be accumulated
over rows so candidate state is only six statistics per active disparity.

An alternative removes the large band SRAM: delay the L stream horizontally
with a short shift register and accumulate all tile/disparity statistics while
capturing. This needs 32 * 17 statistic contexts and many parallel multipliers,
and makes every pixel beat feed up to 17 products. It is attractive when DSP
resources and clock rate are abundant; the band-SRAM design trades memory for
more flexible time multiplexing.

## Accumulator sizing

For 12-bit samples and at most 15,625 pairs, conservative unsigned bounds are:

| Statistic | Maximum | Minimum accumulator width |
|---|---:|---:|
| `SL`, `SR` | 63,984,375 | 26 bits |
| `SLL`, `SRR`, `SLR` | 262,080,015,625 | 38 bits |
| `N` | 15,625 | 14 bits |
| `N*SLL` / `SL*SL` intermediate | about 4.10e15 | 52 bits |
| centered numerator difference | signed | 53 bits |

Use signed intermediates for `N*SLR - SL*SR`. Clamp tiny negative variance caused
by implementation rounding to zero; with exact integer accumulators it should
not occur. The square root/division is only needed for 17 final scores per tile,
so a shared reciprocal-square-root pipeline is usually preferable to per-pixel
normalization.

## RTL synthesis result and system estimate

`rtl/dual_pd_zncc_tile.sv` is a synthesizable one-tile engine. LibreLane 3.0.13
ran its `Yosys.Synthesis` step against `sky130A` at a 10 ns clock constraint.
Yosys reports 91,976 mapped cells, 891,516 um^2 (0.892 mm^2) standard-cell area,
and zero unmapped cells or synthesis-check errors. The result includes 17
parallel disparity product lanes and a shared iterative square-root/divider
normalizer. It excludes tile scheduling and image-buffer SRAM.

For the default 125 x 125 tile, a textured tile takes 15,625 input cycles plus
about 17 * (1 PREP + 54 square-root + 70 divide) = 2,125 normalization cycles,
then a report cycle: about 17,751 cycles per tile. Four independent engines
operating at 250 MHz could process four tiles concurrently, then take eight
groups to cover the 32 columns: approximately 142,000 cycles per tile band,
versus 173,611 cycles available in 125 lines at 60 fps. This leaves about 18%
of the band interval for scheduling and blanking. The raster controller now
accepts four adjacent paired pixels per `sensor_valid` beat, in packed
`sensor_l`/`sensor_r` vectors. Since each beat starts on an x coordinate
multiple of four, the four pixels write the four x-mod-4 SRAM banks at the same
word address. The 720 Mpixel/s active input rate therefore needs at least
180 MHz at four pixels/beat; blanking reduces the average beat rate, while the
sensor's peak active-line rate must also be respected. No 180–250 MHz timing has
been met or verified by this synthesis-only run.

| Item | Capacity / mapped estimate | Scope |
|---|---:|---|
| One ZNCC tile engine | 0.892 mm^2, 91,976 mapped cells | Measured with LibreLane/Yosys, sky130A, 10 ns synthesis target |
| Four tile engines | about 3.57 mm^2 cell area | Linear estimate; wrapper and placement effects not included |
| Ping-pong tile-band SRAM | 24 Mbit raw = 2.86 MiB | 2 x 4000 x 125 x 2 views x 12 bits; not present in synthesis netlist |
| SRAM using 16-bit slots | 32 Mbit raw = 3.81 MiB | Easier alignment, 33% more storage |
| Output record storage | less than 4 kB/frame | 768 records; negligible beside image SRAM |

The line-memory estimate is a bit capacity only. Its physical area depends on
the foundry SRAM compiler and macro geometry, and must be added to the 3.57 mm^2
four-core standard-cell estimate. The previous generic 28 nm SRAM area range
was a technology estimate, not a LibreLane result; it must not be combined with
the measured sky130A logic area as one-process PPA.

This core expects an upstream scheduler to read a band SRAM and present one
tile stream to each engine. Four-way banking (or equivalent SRAM width) is
needed to feed the engines concurrently. A full sensor-to-result top-level,
SRAM macro integration, post-placement timing, and power analysis remain to be
implemented for signoff.

The result metric has 768 records/frame (46,080/s). A compact record with tile
coordinates, signed Q4.4 disparity, U8 confidence and status is under 40 bits;
even buffering one frame of result records is under 4 kB and is negligible next
to the image band SRAM.

LibreLane 3.0.13 / sky130A run artifacts are under `rtl/runs/dualpd-tile-v3/`.

The raster/SRAM wrapper is in `rtl/dual_pd_zncc_system.sv`; it uses eight
external synchronous SRAM ports (ping/pong x four pixel-interleaved banks),
and its four-pixel/beat, 4-core small-frame test is
`sim/tb_dual_pd_zncc_system.sv`. The test checks the packed writes into all four
SRAM interleaves, completes all 12 tiles on a 32x24 frame, and detects no
overrun. Input beats must be x-aligned, `FRAME_W` must be divisible by
`INPUT_PIXELS`, and the supported beat widths divide the four SRAM banks.
There is no input backpressure; `sensor_valid` must follow the raster schedule
and `overrun` is a sticky indication that the ping-pong capture has fallen
behind. Reset is assumed to align the first valid beat to frame row 0, x=0.
The wrapper passes hierarchy-checked generic Yosys synthesis with four tile
instances (494,218 generic cells total); it is not yet included in the LibreLane
physical-design flow. Generic cell count is not a standard-cell area result.

45 nm comparison is being evaluated separately with the public Nangate45
standard-cell Liberty from OpenROAD-flow-scripts. This is a generic open library,
not a foundry-qualified process design kit; it can provide a cell-mapping area
comparison, but not process-specific signoff, SRAM area, or credible timing.
LibreLane's installed PDK flow here is sky130A. A licensed/foundry 45 nm PDK
would be needed for a production-quality PPA comparison.

For an apples-to-apples RTL mapping datapoint, both Liberty files were mapped
with Yosys 0.62 using the same `synth; dfflibmap; abc -fast; stat` sequence and
the default 125 x 125, +/-8 tile parameters. The generic mapping results are:

| Liberty target | Mapped cells | Cell area | Four-core arithmetic scale |
|---|---:|---:|---:|
| Nangate45 | 131,529 | 153,795 um^2 (0.154 mm^2) | 0.615 mm^2 |
| sky130A | 134,721 | 1,124,082 um^2 (1.124 mm^2) | 4.496 mm^2 |

The direct Liberty comparison suggests about 7.3x lower standard-cell area for
Nangate45, but it is a mapper-level comparison only: `abc -fast` has no clock
constraint, placement, routing, buffering, or foundry corner setup. The earlier
0.892 mm^2 sky130A figure is the separate LibreLane synthesis flow result; do
not mix it with the direct Liberty table. The Nangate45 Liberty was fetched from
OpenROAD-flow-scripts and is not bundled with this project. The band SRAM remains
external and is excluded from every logic-area number above.

## Row-streaming alternative: prototype and break-even comparison

`rtl/dual_pd_zncc_stream_stats.sv` is a functional prototype of the row-streaming
statistics stage. It accepts four adjacent pixels per beat, keeps a 16-sample
horizontal history, splits beats that cross the 125-pixel tile boundary, and
accumulates the same six ZNCC statistics for every tile/disparity. Two banks of
statistics overlap accumulation and readout. `sim/tb_dual_pd_zncc_stream_stats.sv`
checks both tile sums and the 64/56 overlap counts for zero/one-pixel disparity.
It does not yet include the final score normalization, peak/confidence logic, or
Q4.4 output RTL; a shared scorer is scheduled after the band and must finish
before that stats bank is reused.

At default dimensions, `SUM_W=27`, `SQ_W=39`, and `CNT_W=14`; the six ZNCC
fields occupy `2*27 + 3*39 + 14 = 185` bits per tile/disparity. One tile column
across 17 disparities is therefore 3,145 statistic bits. Add one epoch bit per
entry to avoid clearing SRAM contents between uses: 3,162 bits per tile column,
101,184 bits per 32-column band, and 202,368 bits for ping-pong storage (about
24.7 KiB). The macro mapping is 34 synchronous 1R1W SRAMs (17 disparities x two
ping-pong sides), each 32 words x 186 bits. The 186-bit word is one 185-bit
statistic record plus its epoch tag. Two 3,162-bit tile-record caches can hold
boundary writeback/prefetch data. There is no foundry SRAM LEF/Liberty in this
workspace, so physical macro area and timing cannot be claimed from the RTL
smoke test.

The synchronous macro interface is in `rtl/dual_pd_zncc_stats_macro_model.sv`.
`rtl/dual_pd_zncc_stats_sram_timing_top.sv` instantiates its 34-bank farm, and
the Nangate45 ORFS Yosys canonicalization smoke test generated
`1_1_yosys_canonicalize.rtlil` in 0.45 s (about 46 MiB peak process memory).
The SRAMs are black boxes in synthesis, as intended. This verifies the SRAM
interface hierarchy—not yet integration of the streaming accumulator's
read/modify/write controller. The datapath still requires that integration,
including forwarding for repeated-address reads and the tile-boundary two-
column update.

The shared scorer was independently mapped with Yosys 0.62 and the same fast
Liberty mapper as the Nangate45/sky130A comparison above: 106,772 um^2
(0.107 mm^2) Nangate45 and 752,678 um^2 (0.753 mm^2) sky130A. For an estimate of
streaming compute, subtracting one scorer from each of the four mapped tile
cores gives about 0.188 mm^2 for four pixel/candidate update lanes; adding one
shared scorer gives about 0.295 mm^2 before the stats store/cache. This
subtraction is an estimate, because the streaming update datapath is not yet
macro-mapped at RTL.

If the stats are conservatively implemented as enabled standard-cell flops,
202,368 bits (including epoch tags) at Nangate45 DFFR_X1 + MUX2_X1 area
(5.32 + 1.862 um^2) cost about 1.453 mm^2, with roughly another 0.048 mm^2 for two wide tile caches and the
horizontal history. The resulting streaming estimate is about 1.80 mm^2 versus
0.615 mm^2 plus the stored design's 24 Mbit image SRAM. On this FF-backed model,
streaming breaks even if the image SRAM exceeds about 1.17 mm^2. With the
proposed stats SRAM macros, the estimated non-memory logic/cache is about
0.34 mm^2; streaming wins if the 24 Mbit image macro area exceeds the 0.201 Mbit
stats macro area minus about 0.27 mm^2. Equivalently, the image macro can be up
to 0.27 mm^2 smaller than the stats macros and streaming still breaks even on
this logic estimate. These are break-even estimates, not macro measurements;
actual bitcell, port, decoder and aspect-ratio overhead can only be established
with a compiled macro.

Power has no defensible absolute number without the image-SRAM and stats-memory
power models, placed clock tree, voltage/corner, and activity traces. A useful
macro-access comparison is:

```
stored image-memory traffic = 12M pixels * 24 bits * (one write + one read) * 60 fps
                            = 34.56 Gbit/s of addressed SRAM data
streaming stats traffic = 32 tiles * 125 rows * 24 bands * 60 fps
                         * 3,145 bits * (one read + one write)
                         = 36.23 Gbit/s of addressed stats SRAM data
FF-backed extra state clock = 188,700 * Cclk * V^2 * 180 MHz
```

For macro-backed stats, the data-bit traffic is similar: the stats macro needs
about 4.8% lower energy per transferred bit than the image SRAM to offset its
slightly higher traffic, before port/periphery differences. For illustration
only, an FF-backed implementation with `Cclk=1 fF` and `V=1.1 V` adds about
41 mW of state-clock power, equivalent to 1.19 pJ per transferred image-memory
bit. Both architectures perform the same candidate products (about 11.83
billion sample-pair updates/s), so arithmetic power is broadly comparable at
matched throughput. These figures omit memory periphery, clock gating, data
activity, and scorer power; they are not signoff power.

The default-size stream-stat RTL has passed simulation and lint. A standard-cell
only Yosys expansion was stopped after its memory use grew above 3 GB; the stats
arrays need intentional SRAM/register-file mapping, not blind flop expansion.
The 34-macro black-box farm in `rtl/dual_pd_zncc_stats_macro_model.sv` is
hierarchy-checked, but is not yet connected to the accumulator/controller RTL;
its purpose is to freeze the macro shape and port contract. The shared scorer
passed a +1-pixel Q4.4/confidence test and a
flat-statistics test, and was directly mapped to both standard-cell libraries.
Therefore the full area/power comparison above is an explicit macro-based
break-even estimate, not completed macro-based synthesis or measured power. A single shared
normalization engine needs roughly 32*2,125 = 68,000 cycles per tile band,
within the 125,000 four-pixel input beats available at 180 MHz, before blanking
adjustments.

## Output and validity

Emit one result per tile after its tile row is complete and processed:
`tile_row`, `tile_col`, signed Q4.4 disparity, unsigned 8-bit confidence, peak
ZNCC, and validity/low-texture status. Q4.4 is a signed 9-bit two's-complement
value with 1/16-pixel steps and range -16..+15.9375 pixels; it covers the
configured ±8-pixel search. Confidence maps [0,1] to 0..255. The reference
model exposes both floating values and these quantized codes. Preserve
frame/tile tags through the compute pipeline. Confidence policy, minimum
texture threshold, peak ratio, frame rate, and exact sensor width/height remain
system-level parameters to calibrate against real sensor data.

## AlphaChip applicability assessment

AlphaChip (Google Circuit Training) is a floorplanning/macro-placement method,
not an RTL synthesis or Boolean-logic area optimizer. It searches macro locations
and orientations and optimizes proxy objectives such as wirelength, congestion,
and density. Its placer consumes a netlist protocol buffer, and proxy scores
must be validated through physical implementation. Therefore it cannot reduce
the mapped standard-cell area reported by the existing Yosys/LibreLane synthesis
run merely by being applied to that netlist.

The repository now has an optional Sky130 binding for the streaming statistics
farm (`SKY130_SRAM_MACRO` in `rtl/dual_pd_zncc_stats_macro_model.sv`). It maps
34 logical 32x186 banks to 204 instances of the available
`sram_1rw1r_32_256_8_sky130` macro (six 32-bit slices per bank). Sky130 PDK
views for that SRAM are present in the installed `sky130_sram_macros` bundle:
LEF, Liberty, GDS, SPICE, and Verilog. From LEF dimensions 376.48 x 446.235 um,
fixed SRAM area is about 0.168 mm2 per macro, 34.27 mm2 total. This is a large,
fixed floor-area component; only 32 of each macro's 256 words are used by the
logical bank. The 204 physical macros make macro placement a plausible AlphaChip
use case, but the current design still has no Sky130 placed DEF/ODB or complete
physical top-level run tying the selected SRAM views, stream controller, and
timing constraints together.

AlphaChip is not installed in the current WSL environment (neither its
`circuit_training` Python package nor TensorFlow is available), and no
AlphaChip-compatible netlist protocol buffer or trained checkpoint is staged.
Thus no AlphaChip placement or quantitative area/power comparison has been
run. The SRAM macro views alone are not enough to produce a trustworthy
full-design placement result.

The plausible benefit, once physical inputs exist, is indirect: AlphaChip
cannot shrink the 34.27 mm2 of fixed SRAM macro area or the Yosys-mapped logic.
A better placement may reduce whitespace, routing-driven buffers/resizing, or
timing repair, improving final core area or power. This cannot be assumed from
proxy wirelength/density alone. A valid evaluation should compare a baseline
OpenROAD/LibreLane placement against an AlphaChip-derived macro placement using
the same synthesized top netlist, SRAM LEF/Liberty, die/core constraints, pin
placement, clocks, and routing settings, then run both through detailed
placement, CTS, routing, and timing/power extraction. Compare final standard-cell
area, macro area, total core area, inserted buffers, routed wirelength,
congestion, WNS/TNS, and activity-based power. Until then, AlphaChip-attributable
area reduction is unquantified and should not be subtracted from synthesis-area
estimates.

The official project describes its macro location/orientation and wirelength,
congestion, and density objectives, as well as the protocol-buffer input format
and need to validate proxy metrics with physical QoR:
https://github.com/google-research/circuit_training

## Nangate45 placement and routing run

The existing one-tile `dual_pd_zncc_tile` RTL was re-synthesized and taken
through OpenROAD-flow-scripts using its Nangate45 platform (typical Liberty,
technology/cell LEF, PDN, CTS and routing setup). The run uses a 40 ns clock,
35% target core utilization, 0.30 placement density, and simple 1 ns input and
output delays. The 40 ns period is an exploratory physical-estimation condition,
not the required 4-pixel/beat sensor clock. The source RTL is a single paired
L/R-pixel-per-beat tile engine; it is not the full 4-pixel/beat top-level and
does not instantiate the streaming stats SRAM macros.

| Metric | Nangate45 result |
| --- | ---: |
| Synthesized standard-cell area | 140,654 um^2 (0.14065 mm^2) |
| Post-route standard-cell instance area | 152,703 um^2 (0.15270 mm^2) |
| Core area | 400,974 um^2 (0.40097 mm^2) |
| Die area | 404,407 um^2 (0.40441 mm^2) |
| Post-route standard-cell instances | 103,980 |
| Global-route estimated wirelength | about 2.08 m total segment length |
| Post-OpenRCX setup slack / hold slack | +4.606 ns / -0.0119 ns |
| Post-OpenRCX hold TNS | -0.1222 ns (72 reported hold violations) |
| Estimated minimum clock period / Fmax | 35.39 ns / 28.25 MHz |
| Reported vectorless total power estimate | 5.168 mW |

The OpenRCX extraction completed on the detailed-routed design using
`nangate45/rcx_patterns.rules`; it processed 122,275 nets and generated
`6_final.spef` (~99.6 MB). The installed OpenROAD build provides
`extract_parasitics -ext_model_file`, but not the newer
`set_extraction_rules_file` Tcl command expected by current ORFS scripts. A
small compatibility fallback uses the supported older option. The SPEF-based
final STA reports the hold violations shown above; these remain to be repaired.
The 5.168 mW estimate has no sensor activity traces and is not signoff or
realistic workload power. Detailed routing completed and its DRC report is
empty. Static IR-drop analysis was skipped in the final extraction run.
Compatibility guards also bypass unsupported `sta::endpoint_count` and GUI
`get_scenes` commands in this OpenROAD build.

An initial 10 ns attempt did not converge in the pre-placement timing repair.
At 40 ns the flow reports positive slack, but the estimated 27.2 MHz maximum
frequency is far below the 180 MHz internal beat rate implied by 4 pixels/beat
at 60 fps (before blanking/overhead). This run therefore validates that the
block can be physically implemented with Nangate45, but does not validate the
sensor throughput requirement. The next optimization target is architectural:
pipeline/parallelize the ZNCC update and replace the single-pixel tile interface
with the specified four-pixel beat interface, then repeat synthesis and PPA.

Run artifacts are under `rtl/physical/work40/`; the setup is in
`rtl/physical/dualpd_tile_config.mk` and `rtl/physical/dualpd_tile.sdc`.

## Executable reference

`bxsim/dual_pd_zncc.py` provides a NumPy reference implementation and
`DualPDStream`, which accepts one L/R raster row at a time and emits all 32 tile
results at each 125-row boundary. It retains one tile-row band, matching the
recommended circular-SRAM dataflow. It is a functional algorithm model, not
cycle-accurate RTL. `scripts/verify_dual_pd_zncc.py` checks its arithmetic,
masking, tile-halo support, stream order and Q4.4 conversion.

## Alignment to the Bayer-aware repository reference (2026-09)

The NumPy reference was updated to the private `pdaf.py` implementation in
`wei00565487/pdaf-afnet-study`: 17 even-shift candidates from -16 to +16 sensor
pixels, per-global-CFA-phase mean removal followed by aggregated covariance
and energies, left-ROI/right-halo support clipped only at frame edges, optional
validity masks, minimum 32 paired samples, and the product score from peak,
nonadjacent margin, curvature, and support count. The 9-bit signed Q4.4 RTL
output cannot represent +16 pixels; a matching hardware output needs at least
10 signed bits at four fractional bits.

The existing `dual_pd_zncc_tile.sv`, `dual_pd_zncc_stream_stats.sv`, SRAM
record, and scorer have **not yet been ported** to this algorithm. Their old
single-mean, one-pixel-step, tile-clipped statistics are not interchangeable
with the updated reference. A straightforward exact-statistics record for the
default tile needs four phases of `(sumL,sumR,sumLL,sumRR,sumLR,count)`; with
24-bit sums, 36-bit square/cross sums, and 12-bit counts this is 672 bits, plus
the epoch tag (673 bits total) versus the old 186-bit word. Six 32-bit macros
per old word become 22 per new word (748 stock SRAM macros across 34 banks),
about 125.7 mm2 of the installed compact Sky130 SRAM macro by LEF area. This
is a capacity-based estimate, not a placed design. The scorer must also perform
per-phase centering and reproduce the repository's uncalibrated score; this
requires a deliberate SRAM/interface/normalizer refactor before RTL can be
claimed equivalent.
# SRAM統計バンク本体接続・全幅合成結果（2026-09）

ストリーミング統計演算本体を同期SRAM farmへ接続した。1タイル列×17視差の値を格納する32×186 bit SRAMを、ping-pong用に34個使用する。容量は合計202,368 bit（24.7 KiB）。統計値185 bitとepoch bit 1 bitを1 wordに格納する。

検証結果：

- Icarus: 4画素/beatでタイル幅6画素を横切るケース、通常のストリーム統計ケース、同期SRAMの登録readケースがすべてPASS。
- Yosys 0.62 / Nangate45: 4000×3000、17視差、4画素/beatの全幅RTLIL正規化と標準セル合成が完了。合成所要約11分32秒、最大メモリ約4.3 GiB。
- 合成結果: 317,788標準セル、標準セル面積425,030.76（Nangate45 Liberty area単位、通常µm²表記で約0.425 mm²）。この値は34個のSRAMブラックボックス面積を含まない。
- OpenROADの配置フローはSRAMを配置DBへリンクする段階で停止。Nangate45に `zncc_stats_32x186_1r1w` のLEF masterがなく、配置可能なSRAM物理ビューが未提供である。従って配置後面積、配線、180 MHzのSTA、電力は未検証。SRAM macroのLEF/Liberty/GDS（または同等のhard-macro abstract）が必要。

合成ログ・成果物は `rtl/physical/work_stream_full_sram/`、全幅ラッパーとフロー設定は `rtl/dual_pd_zncc_stream_stats_full_timing_top.sv` および `rtl/physical/dualpd_stream_full_timing_config.mk` にある。縮小タイミングプロキシの合成は別runであり、本番全幅の面積値として混同しないこと。

## Sky130マクロに代わる45nm相当SRAMの試作（2026-09）

OpenRAM v1.2.49 の FreePDK45 技術で、現行RTLの186-bit統計語を格納する
**32×192-bit、1RW+1R**マクロを生成した。1RWポートを更新書込み、独立した
1Rポートを同期読出しに割り当てる。6 bit/word は未使用。設定は
`rtl/physical/ip/openram_freepdk45_stats_32x192.py`、生成物は
`rtl/physical/work_freepdk45/zncc_stats_32x192_1rw1r_freepdk45.*` にある。
LEF、TT 1.0 V/25 C Liberty、GDS、SPICE、Verilog が生成された。
LEF寸法は604.775×115.13 µm、面積0.0696277 mm²/個である。
34個のSRAM本体は2.36734 mm²、総物理容量は208,896 bit、論理容量は
202,368 bit。生成時は解析的タイミングを使用し、DRC/LVS/PEXを省略した。

`FREEPDK45_SRAM_MACRO` を定義した `rtl/dual_pd_zncc_stats_macro_model.sv` は
このマクロに接続する。専用Icarusテストで書込み・読戻しと別アドレスへの
同時読書きを確認した。`dualpd_stats_freepdk45_config.mk` でNangate45
標準セル＋FreePDK45マクロを**技術混在の配置プロキシ**として読み込むと、
34マクロを含むYosys合成/ODB生成と手動マクロ配置、フロアプランを通過した。
合成ODB報告の面積は約2.36756 mm²（うちSRAM約2.36734 mm²）。
自動マクロ配置はこのOpenROADビルドのOR-Tools/SCIP連携でクラッシュし、
`freepdk45_stats_macro_placement.tcl` の固定配置を使った。LEFピンの一部が
Nangate45トラックに整列せず、PGピン接続も未整備である。したがって、
この混在配置を配線可能・製造可能・180 MHz達成の証拠とは扱わない。
電力も未評価である。実チップ化には、対象45nmファウンドリの標準セルと
同一PDKで生成されたSRAM IP/コンパイラが必須。

リポジトリ準拠の4 Bayer位相統計は672 bit+epoch 1 bit=673 bit/word。
単一32×704-bitマクロ（31 bit/word未使用）も生成したが、LEF寸法
2176.07×227.59 µm、0.495252 mm²/個、34個では16.8386 mm²と大きい。
採用した45nm相当の論理バンクは**32×192-bit×3＋32×104-bit×1**を並列に
した1RW+1R構成で、末尾7 bit/wordのみ未使用。104-bitマクロのLEF寸法は
334.395×100.85 µm、0.0337237 mm²/個。物理SRAMは計136個、
739,840 bit、**8.24864 mm²**。単一704-bit案に対しSRAM LEF面積は
51.0%減るが、マクロ配置・配線難度は上がる。673-bit論理容量は
732,224 bit（約89.4 KiB）。

`rtl/dual_pd_zncc_stats_4phase_macro.sv` のラッパーと34バンクfarmを実装し、
生成した2種類のVerilogモデルを用いて、192-bit境界をまたぐ読戻しを
Icarusで確認した。2種類のLibertyとLEFを読み込む
`rtl/physical/dualpd_stats_4phase_freepdk45_config.mk` でYosys正規化・
合成・ODB生成も通り、ODB報告面積は8.248855 mm²。ただしこれは
**統計バンクのみ**であり、4位相ZNCC演算ロジックは含まれない。
`freepdk45_stats_4phase_macro_placement.tcl` による136マクロの手動配置と
フロアプランODB生成も通った。35%利用率で約4857×4857 µmのダイが
自動設定されたが、FreePDK45ピンのNangate45トラック不整列、および
マクロ電源ピン未接続の警告が残る。配置・配線・電源・STAを閉じた
45nm実装ではなく、技術混在の寸法/接続プロキシである。
旧186-bitストリーム演算本体とスコアラは673-bit契約へ未移植。
したがって8.24864 mm²を新ZNCCの総面積・電力とは混同しない。
