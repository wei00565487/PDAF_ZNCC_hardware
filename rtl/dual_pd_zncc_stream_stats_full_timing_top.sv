// Full production-parameter wrapper for Nangate45 synthesis/elaboration.
module dual_pd_zncc_stream_stats_full_timing_top (
    input logic clk, rst_n, in_valid,
    input logic [47:0] in_l, in_r,
    output logic band_done, band_done_bank,
    input logic rd_bank,
    input logic [4:0] rd_tile,
    input logic [4:0] rd_disp,
    output logic rd_valid,
    output logic [26:0] rd_sum_l, rd_sum_r,
    output logic [38:0] rd_sum_ll, rd_sum_rr, rd_sum_lr,
    output logic [13:0] rd_count,
    input logic [1:0] release_bank,
    output logic [1:0] ready_bank,
    output logic overrun
);
    dual_pd_zncc_stream_stats u_stats (.*);
endmodule
