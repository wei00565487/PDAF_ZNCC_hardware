# Pooled ZNCC SRAM/score backend RTL-to-GDS report

## Scope

This run evaluates the current pooled-statistics storage and shared serial
scorer backend. The physical top accepts one completed zone's 17 pooled
184-bit sufficient-statistics records, stores them in a single 32-deep SRAM
farm, then reads the old row in zone order. Each zone address is released for
the next row only after all 17 SRAM read ports have sampled its old contents.
This permits next-row writes to overlap scoring without a second SRAM row.

The raw Bayer line buffer, pseudo-luma/candidate-window producer, and pooled
moment accumulator are not yet connected to this physical top. Accordingly,
these RTL-to-GDS numbers are for the SRAM/score backend, not the complete
sensor-to-phase pipeline.

## Technology and macro

- Standard-cell platform: Nangate45 (research library).
- SRAM: 17 OpenRAM 32x192 1RW1R macros generated from FreePDK45.
- Mixed-process proxy: the OpenRAM LEF/GDS/Liberty and Nangate45 standard-cell
  stack are not a foundry-consistent process kit.
- Logical capacity: 17 x 32 x 185 = 100,640 bits (184-bit pooled record plus
  one padding/epoch bit).
- Physical capacity: 17 x 32 x 192 = 104,448 bits; seven bits per word are
  unused.
- SRAM macro area: 1,183,671.68 um^2 (17 macros).

## Results

- Yosys synthesis and OpenROAD place/clock-tree/global-route/detailed-route
  completed; OpenRCX parasitic extraction produced SPEF.
- Final standard-cell area: 136,374 um^2.
- Final SRAM macro area: 1,183,671.68 um^2.
- Combined instance area: 1,320,046 um^2 (1.320 mm^2).
- Core area: 3,653,774.67 um^2 (3.654 mm^2); configured target utilization
  was 35%.
- Post-route setup slack: +0.1958 ns; hold slack: +0.0835 ns; setup/hold TNS:
  0. Final extracted clock minimum period: 5.36 ns, Fmax 186.56 MHz, above
  the 180 MHz target in this proxy flow.
- Detailed-route DRC: 170 remaining violations, all reported as metal4 shorts
  on/within OpenRAM macro instances. Therefore this GDS is not DRC-clean.
- PDN/IR-drop analysis: not completed. OpenROAD reports the OpenRAM `vdd`
  terminals and associated power shapes as unconnected in the Nangate45 PDN
  model. The final timing report was generated with IR-drop analysis skipped.
- Vectorless power from OpenROAD is not treated as a useful sensor power
  estimate: this backend has a 3,199-pin integration boundary and no realistic
  activity constraints. Do not use it as a 60 fps chip power figure.

## Functional check

`tb_dual_pd_zncc_pooled_sram_score_top` passed in Icarus Verilog. It fills all
32 zone addresses, scans the row in order, and confirms an address can be
refilled only after its previous contents have been sampled by the SRAM read
ports.

## Artifacts

The generated `results/` and `reports/` trees, plus generated FreePDK45/OpenRAM
and routeable LEF collateral, are local ORFS outputs and are ignored by Git;
the paths below identify products in the working environment and are not
downloadable from the GitHub repository. The RTL, flow settings, testbench,
and this summary report are tracked, but rerunning the flow also requires the
locally generated macro collateral and ORFS environment.

- Physical top: `rtl/dual_pd_zncc_pooled_sram_score_top.sv`
- Configuration: `rtl/physical/dualpd_pooled_sram_score_config.mk`
- SDC: `rtl/physical/dualpd_pooled_sram_score.sdc`
- Testbench: `sim/tb_dual_pd_zncc_pooled_sram_score_top.sv`
- Final GDS: `rtl/physical/pooled_openram_rtl2gds/results/nangate45/dual_pd_zncc_pooled_sram_score_top/base/6_final.gds`
- Final DEF: `rtl/physical/pooled_openram_rtl2gds/results/nangate45/dual_pd_zncc_pooled_sram_score_top/base/6_final.def`
- Final SPEF: `rtl/physical/pooled_openram_rtl2gds/results/nangate45/dual_pd_zncc_pooled_sram_score_top/base/6_final.spef`
- Timing/area report: `rtl/physical/pooled_openram_rtl2gds/reports/nangate45/dual_pd_zncc_pooled_sram_score_top/base/6_finish.rpt`
- Detailed-route DRC report: `rtl/physical/pooled_openram_rtl2gds/reports/nangate45/dual_pd_zncc_pooled_sram_score_top/base/5_route_drc.rpt`
