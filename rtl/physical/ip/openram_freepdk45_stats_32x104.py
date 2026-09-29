"""Tail slice for 673-bit four-phase stats: 3*192 + 104 = 680 bits."""

word_size = 104
num_words = 32
num_rw_ports = 1
num_r_ports = 1
num_w_ports = 0
tech_name = "freepdk45"
nominal_corner_only = True
route_supplies = False
check_lvsdrc = False
perimeter_pins = False
analytical_delay = True
output_name = "zncc_stats_32x104_1rw1r_freepdk45"
output_path = "rtl/physical/work_freepdk45/"
