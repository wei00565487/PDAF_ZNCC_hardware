`timescale 1ns/1ps
module tb_dual_pd_zncc_freepdk45_macro;
    logic clk=0, rd_en=0, wr_en=0;
    logic [4:0] rd_addr=0, wr_addr=0;
    logic [185:0] rd_data, wr_data=0;
    logic rd_valid;
    always #5 clk=~clk;
    zncc_stats_32x186_1r1w dut (.*);

    initial begin
        // OpenRAM's behavioral model updates memory/read output after the
        // falling edge; sample well after that model-only arbitrary delay.
        @(negedge clk); #1; wr_en=1; wr_addr=7; wr_data=186'h2a5;
        @(negedge clk); #1; wr_en=0; rd_en=1; rd_addr=7;
        @(negedge clk); #4;
        if (!rd_valid || rd_data !== 186'h2a5)
            $fatal(1, "FreePDK45 readback failed valid=%b data=%h", rd_valid, rd_data);
        // One port can write while the other reads a *different* address.
        #2; wr_en=1; wr_addr=8; wr_data=186'h1d3;
        @(negedge clk); #1; rd_addr=7;
        @(negedge clk); #4;
        if (rd_data !== 186'h2a5)
            $fatal(1, "FreePDK45 simultaneous distinct-address read failed: %h", rd_data);
        wr_en=0; rd_addr=8;
        @(negedge clk); #4;
        if (!rd_valid || rd_data !== 186'h1d3)
            $fatal(1, "FreePDK45 concurrent port test failed: %h", rd_data);
        $display("PASS FreePDK45 32x192 1RW+1R macro binding");
        $finish;
    end
endmodule
