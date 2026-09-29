# Two logical banks per row; four parallel slices per logical bank.
# Escape Yosys-generated array brackets in OpenDB instance names.
for {set bank 0} {$bank < 34} {incr bank} {
    set base_x [expr {50 + ($bank % 2) * 2350}]
    set base_y [expr {50 + int($bank / 2) * 235}]
    for {set slice 0} {$slice < 4} {incr slice} {
        set x [expr {$base_x + $slice * 625}]
        set name [format {u_farm.gen_bank\[%d\].u_mem.u_slice%d} $bank $slice]
        place_macro -macro_name $name -location [list $x $base_y] -orientation R0
    }
}
