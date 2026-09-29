read_db /mnt/c/Users/fireg/code/sensor-analysis/bayer-crosstalk-sim/rtl/physical/openroad-flow-scripts/flow/results/nangate45/dual_pd_zncc_pipe1_32col_top/bank17/2_1_floorplan.odb
set block [ord::get_db_block]
foreach inst [$block getInsts] {
  set master [$inst getMaster]
  if {[$master isBlock]} {
    puts [$inst getName]
  }
}
exit
