create_clock -name clk -period 5.556 [get_ports clk]
set_input_delay 1.0 -clock clk [get_ports {rst_n in_valid in_l[*] in_r[*] in_mask_l[*] in_mask_r[*]}]
set_output_delay 1.0 -clock clk [get_ports stats_valid]
set_false_path -from [get_ports rst_n]
