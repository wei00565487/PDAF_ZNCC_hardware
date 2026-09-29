`timescale 1ns/1ps
module tb_dual_pd_zncc_4phase_macro;
    logic clk=0, rd_en=0, wr_en=0;
    logic [4:0] rd_addr=0, wr_addr=0;
    logic [672:0] rd_data, wr_data=0;
    logic rd_valid;
    always #5 clk=~clk;
    zncc_stats_32x673_1r1w dut (.*);

    initial begin
        @(negedge clk); #1;
        wr_en=1; wr_addr=17;
        wr_data='0;
        wr_data[0]=1'b1;
        wr_data[191]=1'b1; wr_data[192]=1'b1;
        wr_data[383]=1'b1; wr_data[384]=1'b1;
        wr_data[575]=1'b1; wr_data[576]=1'b1;
        wr_data[671]=1'b1; wr_data[672]=1'b1;
        @(negedge clk); #1; wr_en=0; rd_en=1; rd_addr=17;
`ifdef FREEPDK45_4PHASE_SRAM_MACRO
        @(negedge clk); #4;
`else
        @(posedge clk); #1;
`endif
        if (!rd_valid || rd_data !== wr_data)
            $fatal(1, "four-phase 673-bit macro readback failed");
        $display("PASS four-phase 673-bit macro binding");
        $finish;
    end
endmodule
