create_clock -name clk -period 5.556 [get_ports clk]
set_input_delay 1.0 -clock clk [all_inputs -no_clocks]
set_output_delay 1.0 -clock clk [all_outputs]
set_false_path -from [get_ports rst_n]
