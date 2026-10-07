module tb_dual_pd_zncc_pooled_sram_score_top;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0;
    logic zone_stats_valid = 0;
    logic [4:0] zone_stats_addr = 0;
    logic [17*184-1:0] zone_stats_records = '0;
    logic zone_stats_ready;
    logic score_row_start = 0;
    logic score_row_ready;
    logic busy, out_valid;
    logic [4:0] out_zone_addr;
    logic [9:0] phase_q4_4;
    logic [7:0] confidence_u8;
    logic [15:0] peak_zncc_q15, second_zncc_q15;
    logic low_texture;
    integer out_count = 0;
    logic refill_done = 0;

    dual_pd_zncc_pooled_sram_score_top dut (.*);

    function automatic [183:0] make_record;
        make_record = {12'd100,40'd425000,40'd500000,40'd500000,
                       26'd5000,26'd5000};
    endfunction

    task automatic write_zone(input logic [4:0] address);
        begin
            @(negedge clk);
            zone_stats_addr = address;
            zone_stats_records = {17{make_record()}};
            zone_stats_valid = 1;
            while (!zone_stats_ready) @(negedge clk);
            @(negedge clk);
            zone_stats_valid = 0;
        end
    endtask

    always @(posedge clk) begin
        if (rst_n && out_valid) begin
            if (out_zone_addr !== out_count[4:0])
                $fatal(1,"score order mismatch got %0d expected %0d",
                       out_zone_addr,out_count);
            if (low_texture)
                $fatal(1,"unexpected low-texture result at zone %0d",out_zone_addr);
            out_count <= out_count + 1;
        end
    end

    initial begin
        integer i;
        repeat (3) @(negedge clk);
        rst_n = 1;
        for (i=0;i<32;i=i+1) write_zone(5'(i));
        if (!score_row_ready) $fatal(1,"row did not become score-ready");

        @(negedge clk); score_row_start = 1;
        @(negedge clk); score_row_start = 0;

        // Address zero may be refilled only after its old record has been
        // sampled by all 17 SRAM read ports.
        if (zone_stats_ready) $fatal(1,"unread SRAM row was released early");
        write_zone(5'd0);
        refill_done = 1;

        wait(out_count == 32);
        if (!refill_done) $fatal(1,"next-row write did not overlap scoring");
        if (score_row_ready) $fatal(1,"partial next row reported ready");
        $display("PASS: 32-zone SRAM row scan and read-before-reuse overlap");
        $finish;
    end

    initial begin
        #10000000;
        $fatal(1,"timeout waiting for pooled SRAM score row");
    end
endmodule
