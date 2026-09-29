module tb_dual_pd_zncc_stats_macro_model;
    logic clk=0, rd_en=0, wr_en=0;
    logic [4:0] rd_addr=0, wr_addr=0;
    logic [185:0] rd_data, wr_data=0;
    logic rd_valid;
    always #5 clk=~clk;

    zncc_stats_32x186_1r1w dut (.*);

    initial begin
        @(negedge clk); wr_en=1; wr_addr=5'd7; wr_data=186'h2a5;
        @(negedge clk); wr_en=0; rd_en=1; rd_addr=5'd7;
        @(posedge clk); #1;
        if (!rd_valid || rd_data !== 186'h2a5)
            $fatal(1, "sync SRAM readback failed valid=%b data=%h", rd_valid, rd_data);
        @(negedge clk); rd_en=0;
        $display("PASS sync stats SRAM model: registered read, 186-bit word");
        $finish;
    end
endmodule
