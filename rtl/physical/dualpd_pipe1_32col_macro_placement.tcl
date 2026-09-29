# Place 17 candidate banks, each made of 3x192 + 1x104 SRAM slices.
# The 4-slice stack is kept together; banks are spread over a 4x5 grid.
for {set b 0} {$b < 17} {incr b} {
  set col [expr {$b % 4}]
  set row [expr {$b / 4}]
  set x [expr {50 + 700 * $col}]
  set y [expr {50 + 550 * $row}]
  set p0 [format {u_stats/gen_candidate_bank\[%d\].u_bank.u_slice0} $b]
  set p1 [format {u_stats/gen_candidate_bank\[%d\].u_bank.u_slice1} $b]
  set p2 [format {u_stats/gen_candidate_bank\[%d\].u_bank.u_slice2} $b]
  set p3 [format {u_stats/gen_candidate_bank\[%d\].u_bank.u_slice3} $b]
  place_macro -macro_name $p0 -location [list $x $y] -orientation R0
  place_macro -macro_name $p1 -location [list $x [expr {$y + 130}]] -orientation R0
  place_macro -macro_name $p2 -location [list $x [expr {$y + 260}]] -orientation R0
  place_macro -macro_name $p3 -location [list $x [expr {$y + 390}]] -orientation R0
}
