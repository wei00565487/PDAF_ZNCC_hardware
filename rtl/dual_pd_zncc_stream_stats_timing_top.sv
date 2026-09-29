// Timing-proxy top: keeps the production 4-pixel/17-disparity arithmetic
// while shrinking only the statistics-context count for practical P&R.
module dual_pd_zncc_stream_stats_timing_top (
    input logic clk, rst_n, in_valid,
    input logic [47:0] in_l, in_r,
    output logic band_done, band_done_bank,
    input logic rd_bank,
    input logic [1:0] rd_tile,
    input logic [1:0] rd_disp,
    output logic rd_valid,
    output logic [19:0] rd_sum_l, rd_sum_r,
    output logic [31:0] rd_sum_ll, rd_sum_rr, rd_sum_lr,
    output logic [7:0] rd_count,
    input logic [1:0] release_bank,
    output logic [1:0] ready_bank,
    output logic overrun
);
    dual_pd_zncc_stream_stats #(
        .FRAME_W(64), .FRAME_H(16), .TILE_COLS(4), .TILE_ROWS(2),
        .TILE_W(16), .TILE_H(8), .INPUT_PIXELS(4), .MAX_D(1),
        .SUM_W(20), .SQ_W(32), .CNT_W(8), .COL_W(2), .DISP_W(2),
        .CTX_COUNT(24)
    ) u_stats (.*);
endmodule
