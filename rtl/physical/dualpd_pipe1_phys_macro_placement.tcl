# Deterministic placement for the serialized physical SRAM abstraction.
# The logic core uses bank0; the four physical slices are placed explicitly.
place_macro -macro_name u_farm/u_bank0.u_slice0 -location {50 50} -orientation R0
place_macro -macro_name u_farm/u_bank0.u_slice1 -location {50 180} -orientation R0
place_macro -macro_name u_farm/u_bank0.u_slice2 -location {50 310} -orientation R0
place_macro -macro_name u_farm/u_bank0.u_slice3 -location {50 440} -orientation R0
