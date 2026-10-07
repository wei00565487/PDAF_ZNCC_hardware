# Mixed Nangate45 + FreePDK45/OpenRAM research proxy for the current pooled
# ZNCC score backend. This is not a foundry signoff technology combination.
export DESIGN_NAME = dual_pd_zncc_pooled_sram_score_top
export PLATFORM = nangate45
export DESIGN_DIR = /work/rtl/physical
export TECH_LEF = $(DESIGN_DIR)/nangate45_grid.tech.lef
export VERILOG_FILES = \
  /work/rtl/dual_pd_zncc_pooled_sram_score_top.sv \
  /work/rtl/dual_pd_zncc_scorer_pooled.sv \
  /work/rtl/dual_pd_zncc_stats_pooled_macro_farm.sv \
  /work/rtl/dual_pd_zncc_stats_macro_model.sv \
  $(DESIGN_DIR)/work_freepdk45/zncc_stats_32x192_1rw1r_freepdk45.v
export VERILOG_DEFINES = -DFREEPDK45_SRAM_MACRO -DSYNTHESIS
export SDC_FILE = $(DESIGN_DIR)/dualpd_pooled_sram_score.sdc
export CLOCK_PERIOD = 5.556
export CORE_UTILIZATION = 35
export PLACE_DENSITY = 0.30
export ABC_AREA = 1
export SYNTH_REPEATABLE_BUILD = 1
export ADDITIONAL_LEFS = $(DESIGN_DIR)/work_nangate45_routeable/zncc_stats_32x192_1rw1r_routeable.lef
export ADDITIONAL_LIBS = $(DESIGN_DIR)/work_freepdk45/zncc_stats_32x192_1rw1r_freepdk45_TT_1p0V_25C.lib
export ADDITIONAL_GDS = $(DESIGN_DIR)/work_freepdk45/zncc_stats_32x192_1rw1r_freepdk45.gds
export PDN_TCL = $(DESIGN_DIR)/dualpd_pooled_sram_score_pdn.tcl
