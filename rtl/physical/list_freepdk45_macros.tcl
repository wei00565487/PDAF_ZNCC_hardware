read_db rtl/physical/openroad-flow-scripts/flow/results/nangate45/dual_pd_zncc_stats_sram_timing_top/freepdk45/2_1_floorplan.odb
foreach inst [[ord::get_db_block] getInsts] {
    if {[[$inst getMaster] getName] eq "zncc_stats_32x192_1rw1r_freepdk45"} {
        puts [$inst getName]
    }
}
