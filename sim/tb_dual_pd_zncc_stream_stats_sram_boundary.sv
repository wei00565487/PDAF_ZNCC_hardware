module tb_dual_pd_zncc_stream_stats_sram_boundary;
    logic clk=0, rst_n=0, in_valid=0;
    logic [47:0] in_l=0, in_r=0;
    logic band_done, band_done_bank, rd_bank=0;
    logic [0:0] rd_tile=0;
    logic [1:0] rd_disp=1;
    logic rd_valid;
    logic [16:0] rd_sum_l, rd_sum_r;
    logic [28:0] rd_sum_ll, rd_sum_rr, rd_sum_lr;
    logic [3:0] rd_count;
    logic [1:0] release_bank=0, ready_bank;
    logic overrun, done_seen=0;
    integer x,y,p;
    always #5 clk=~clk;
    always @(posedge clk) if (band_done) done_seen<=1'b1;

    dual_pd_zncc_stream_stats #(
        .FRAME_W(12), .FRAME_H(2), .TILE_COLS(2), .TILE_ROWS(1),
        .TILE_W(6), .TILE_H(2), .INPUT_PIXELS(4), .MAX_D(1),
        .SUM_W(17), .SQ_W(29), .CNT_W(4), .COL_W(1), .DISP_W(2), .CTX_COUNT(12)
    ) dut (
        .clk, .rst_n, .in_valid, .in_l, .in_r, .band_done, .band_done_bank,
        .rd_bank, .rd_tile, .rd_disp, .rd_valid, .rd_sum_l, .rd_sum_r,
        .rd_sum_ll, .rd_sum_rr, .rd_sum_lr, .rd_count, .release_bank,
        .ready_bank, .overrun
    );

    initial begin
        repeat (3) @(negedge clk); rst_n=1;
        for (y=0; y<2; y=y+1) begin
            for (x=0; x<12; x=x+4) begin
                @(negedge clk); in_valid=1;
                for (p=0; p<4; p=p+1) begin
                    in_l[p*12 +: 12]=1+x+p+y*12;
                    in_r[p*12 +: 12]=1+x+p+y*12;
                end
            end
        end
        @(negedge clk); in_valid=0;
        repeat (8) @(posedge clk); #1;
        if (!done_seen || !ready_bank[0] || overrun) $fatal(1, "boundary band completion failed");
        rd_tile=0; rd_disp=1; @(posedge clk); #1;
        if (!rd_valid || rd_count!=12 || rd_sum_l!=114)
            $fatal(1, "left boundary tile count=%0d sum=%0d valid=%b", rd_count, rd_sum_l, rd_valid);
        rd_tile=1; @(posedge clk); #1;
        if (!rd_valid || rd_count!=12 || rd_sum_l!=186)
            $fatal(1, "right boundary tile count=%0d sum=%0d valid=%b", rd_count, rd_sum_l, rd_valid);
        $display("PASS SRAM stats: 4-pixel beat crossing a 6-pixel tile boundary");
        $finish;
    end
endmodule
