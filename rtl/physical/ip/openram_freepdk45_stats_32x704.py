"""Exploratory 45 nm 1RW+1R statistics SRAM for four-phase ZNCC.

Four 168-bit Bayer phase records plus an epoch tag require 673 bits.
Thirty-one upper bits of this 704-bit physical word are padding.
"""

word_size = 704
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
output_name = "zncc_stats_32x704_1rw1r_freepdk45"
output_path = "rtl/physical/work_freepdk45/"
