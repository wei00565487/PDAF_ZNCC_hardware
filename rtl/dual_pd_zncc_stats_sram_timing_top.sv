// Synthesis smoke top for the synchronous 34-bank, dual-row statistics SRAM
// interface. The SRAM macros are black boxes in the synthesis view.
module dual_pd_zncc_stats_sram_timing_top (
    input logic clk,
    input logic [33:0] rd_en,
    input logic [169:0] rd_addr,
    output logic [33:0] rd_valid,
    output logic [34*186-1:0] rd_data,
    input logic [33:0] wr_en,
    input logic [169:0] wr_addr,
    input logic [34*186-1:0] wr_data
);
    dual_pd_zncc_stats_macro_farm u_farm (.*);
endmodule
