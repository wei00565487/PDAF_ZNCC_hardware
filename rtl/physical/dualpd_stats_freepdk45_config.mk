# Exploratory 45 nm macro integration. FreePDK45 and Nangate45 are distinct
# research technology stacks; placement is a proxy, not signoff-compatible.
export DESIGN_NAME = dual_pd_zncc_stats_sram_timing_top
export PLATFORM = nangate45
export DESIGN_DIR = /mnt/c/Users/fireg/code/sensor-analysis/bayer-crosstalk-sim/rtl/physical
export VERILOG_FILES = $(DESIGN_DIR)/../dual_pd_zncc_stats_macro_model.sv $(DESIGN_DIR)/../dual_pd_zncc_stats_sram_timing_top.sv
export VERILOG_DEFINES = -DFREEPDK45_SRAM_MACRO -DSYNTHESIS
export SDC_FILE = $(DESIGN_DIR)/dualpd_stats_sram_timing.sdc
export CLOCK_PERIOD = 5.556
export CORE_UTILIZATION = 35
export PLACE_DENSITY = 0.30
export ABC_AREA = 1
export SYNTH_REPEATABLE_BUILD = 1
export ADDITIONAL_LEFS = $(DESIGN_DIR)/work_freepdk45/zncc_stats_32x192_1rw1r_freepdk45.lef
export ADDITIONAL_LIBS = $(DESIGN_DIR)/work_freepdk45/zncc_stats_32x192_1rw1r_freepdk45_TT_1p0V_25C.lib
export ADDITIONAL_GDS = $(DESIGN_DIR)/work_freepdk45/zncc_stats_32x192_1rw1r_freepdk45.gds
export MACRO_PLACEMENT_TCL = $(DESIGN_DIR)/freepdk45_stats_macro_placement.tcl
