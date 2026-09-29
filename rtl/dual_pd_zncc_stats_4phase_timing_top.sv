// Interface-only synthesis smoke top for the 673-bit four-phase stats farm.
module dual_pd_zncc_stats_4phase_timing_top (
    input logic clk,
    input logic [33:0] rd_en,
    input logic [169:0] rd_addr,
    output logic [33:0] rd_valid,
    output logic [34*673-1:0] rd_data,
    input logic [33:0] wr_en,
    input logic [169:0] wr_addr,
    input logic [34*673-1:0] wr_data
);
    dual_pd_zncc_stats_4phase_macro_farm u_farm (.*);
endmodule
