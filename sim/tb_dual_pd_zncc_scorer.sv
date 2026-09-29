module tb_dual_pd_zncc_scorer;
    logic clk=0, rst_n=0, start=0;
    logic [56:0] stats_sum_l=0, stats_sum_r=0;
    logic [92:0] stats_sum_ll=0, stats_sum_rr=0, stats_sum_lr=0;
    logic [20:0] stats_count=0;
    logic busy, out_valid, low_texture;
    logic signed [8:0] phase_q4_4;
    logic [7:0] confidence_u8;
    always #5 clk=~clk;
    dual_pd_zncc_scorer #(.TILE_W(8), .TILE_H(8), .MAX_D(1),
        .SUM_W(19), .SQ_W(31), .CNT_W(7)) dut (
        .clk, .rst_n, .start, .stats_sum_l, .stats_sum_r,
        .stats_sum_ll, .stats_sum_rr, .stats_sum_lr, .stats_count,
        .busy, .out_valid, .phase_q4_4, .confidence_u8, .low_texture
    );
    initial begin
        repeat (3) @(negedge clk); rst_n=1;
        stats_sum_l[2*19 +: 19]=3;
        stats_sum_r[2*19 +: 19]=3;
        stats_sum_ll[2*31 +: 31]=5;
        stats_sum_rr[2*31 +: 31]=5;
        stats_sum_lr[2*31 +: 31]=5;
        stats_count[2*7 +: 7]=2;
        @(negedge clk); start=1;
        @(negedge clk); start=0;
        wait(out_valid);
        if (low_texture || phase_q4_4!=16 || confidence_u8!=255)
            $fatal(1,"perfect +1px candidate mismatch phase=%0d conf=%0d",phase_q4_4,confidence_u8);
        @(negedge clk);
        stats_sum_l='0; stats_sum_r='0; stats_sum_ll='0; stats_sum_rr='0;
        stats_sum_lr='0; stats_count='0; start=1;
        @(negedge clk); start=0;
        wait(out_valid);
        if (!low_texture || phase_q4_4!=0 || confidence_u8!=0)
            $fatal(1,"flat statistics not rejected");
        $display("PASS shared scorer: +1px Q4.4/confidence and flat rejection");
        $finish;
    end
endmodule
