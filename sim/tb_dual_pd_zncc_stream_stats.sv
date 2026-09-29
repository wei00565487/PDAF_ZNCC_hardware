module tb_dual_pd_zncc_stream_stats;
    logic clk=0, rst_n=0, in_valid=0;
    logic [47:0] in_l=0, in_r=0;
    logic band_done, band_done_bank, rd_bank=0;
    logic [0:0] rd_tile=0;
    logic [1:0] rd_disp=1;
    logic rd_valid;
    logic [18:0] rd_sum_l, rd_sum_r;
    logic [30:0] rd_sum_ll, rd_sum_rr, rd_sum_lr;
    logic [6:0] rd_count;
    logic [1:0] release_bank=0, ready_bank;
    logic overrun;
    logic done_seen=0;
    integer x,y,p;

    always #5 clk=~clk;
    always @(posedge clk) if (band_done) done_seen<=1'b1;
    dual_pd_zncc_stream_stats #(.FRAME_W(16), .FRAME_H(8), .TILE_COLS(2),
        .TILE_ROWS(1), .TILE_W(8), .TILE_H(8), .INPUT_PIXELS(4),
        .MAX_D(1), .SUM_W(19), .SQ_W(31), .CNT_W(7), .COL_W(1),
        .DISP_W(2), .CTX_COUNT(12), .CTX_W(4)) dut (
        .clk, .rst_n, .in_valid, .in_l, .in_r, .band_done, .band_done_bank,
        .rd_bank, .rd_tile, .rd_disp, .rd_valid, .rd_sum_l, .rd_sum_r,
        .rd_sum_ll, .rd_sum_rr, .rd_sum_lr, .rd_count, .release_bank,
        .ready_bank, .overrun
    );

    initial begin
        repeat (3) @(negedge clk); rst_n=1;
        for (y=0; y<8; y=y+1) begin
            for (x=0; x<16; x=x+4) begin
                @(negedge clk); in_valid=1;
                for (p=0; p<4; p=p+1) begin
                    in_l[p*12 +: 12] = 100 + x+p + y*3;
                    in_r[p*12 +: 12] = 100 + x+p + y*3;
                end
            end
        end
        @(negedge clk); in_valid=0;
        repeat (6) @(posedge clk); #1; // drain the statistic SRAM read/modify/write pipeline
        if (!done_seen || !ready_bank[0] || overrun)
            $fatal(1, "band completion/ready failed done=%b ready=%b overrun=%b", band_done, ready_bank, overrun);
        rd_disp=1; @(posedge clk); #1;
        if (!rd_valid || rd_count != 64 || rd_sum_l != 7296)
            $fatal(1, "tile0 disp0 count=%0d sum=%0d valid=%b", rd_count, rd_sum_l, rd_valid);
        rd_disp=2; @(posedge clk); #1;
        if (!rd_valid || rd_count != 56) $fatal(1, "tile0 disp+1 count=%0d valid=%b", rd_count, rd_valid);
        rd_tile=1; rd_disp=1; @(posedge clk); #1;
        if (!rd_valid || rd_count != 64 || rd_sum_l != 7808)
            $fatal(1, "tile1 disp0 count=%0d sum=%0d valid=%b", rd_count, rd_sum_l, rd_valid);
        $display("PASS stream stats: 4-pixel beats, tile-boundary split, ZNCC support counts");
        $finish;
    end
endmodule
