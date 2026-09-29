// Synthesis-only abstract view. Physical runs bind the generated FreePDK45
// macro farm from dual_pd_zncc_stats_4phase_macro.sv and its LEF/Liberty.
(* blackbox *)
module dual_pd_zncc_stats_4phase_macro_farm (
    input logic clk,
    input logic [33:0] rd_en,
    input logic [169:0] rd_addr,
    output logic [33:0] rd_valid,
    output logic [34*673-1:0] rd_data,
    input logic [33:0] wr_en,
    input logic [169:0] wr_addr,
    input logic [34*673-1:0] wr_data
);
endmodule
