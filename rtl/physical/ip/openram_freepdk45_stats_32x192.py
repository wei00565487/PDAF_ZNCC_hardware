"""Exploratory 45 nm 1RW+1R statistics SRAM for the current 186-bit RTL.

The extra six bits are padding. FreePDK45 is a research PDK, not a
manufacturable replacement for a foundry-qualified 45 nm memory compiler.
"""

word_size = 192
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
output_name = "zncc_stats_32x192_1rw1r_freepdk45"
output_path = "rtl/physical/work_freepdk45/"
