`timescale 1ns/1ps
module tb_dual_pd_zncc_scorer_4phase;
    logic clk=0,rst_n=0,start=0,busy,out_valid,low_texture;
    logic [17*672-1:0] stats_records=0;
    logic signed [9:0] phase_q4_4;
    logic [7:0] score_u8,confidence_u8;
    logic signed [15:0] peak_zncc_q15,second_zncc_q15;
    always #5 clk=~clk;
    dual_pd_zncc_scorer_4phase dut (.*);

    function automatic [11:0] pix(input integer x,y);
        reg [31:0] z;
        begin
            z=32'(x*1103515245+y*1234567+93);
            z=z^(z>>13); z=z*32'd2654435761;
            pix=z[23:12];
        end
    endfunction

    longint unsigned sl[0:3],sr[0:3],sll[0:3],srr[0:3],slr[0:3];
    integer n[0:3];
    integer i,ph,x,y,d,rx,off,a,b;
    initial begin
        for (i=0;i<17;i=i+1) begin
            for (ph=0;ph<4;ph=ph+1) begin
                sl[ph]=0;sr[ph]=0;sll[ph]=0;srr[ph]=0;slr[ph]=0;n[ph]=0;
            end
            d=2*(i-8);
            for (y=0;y<8;y=y+1) begin
                for (x=0;x<32;x=x+1) begin
                    rx=x+d;
                    if (rx>=0 && rx<64) begin
                        ph=2*(y%2)+(x%2);
                        a=pix(x,y);
                        b=(rx>=4)?pix(rx-4,y):pix(rx+100,y);
                        sl[ph]=sl[ph]+a; sr[ph]=sr[ph]+b;
                        sll[ph]=sll[ph]+a*a; srr[ph]=srr[ph]+b*b;
                        slr[ph]=slr[ph]+a*b; n[ph]=n[ph]+1;
                    end
                end
            end
            for (ph=0;ph<4;ph=ph+1) begin
                off=i*672+ph*168;
                stats_records[off+0 +: 24]=24'(sl[ph]);
                stats_records[off+24 +: 24]=24'(sr[ph]);
                stats_records[off+48 +: 36]=36'(sll[ph]);
                stats_records[off+84 +: 36]=36'(srr[ph]);
                stats_records[off+120 +: 36]=36'(slr[ph]);
                stats_records[off+156 +: 12]=12'(n[ph]);
            end
        end
        repeat (3) @(negedge clk); rst_n=1;
        @(negedge clk); start=1;
        @(negedge clk); start=0;
        wait(out_valid); #1;
        if (phase_q4_4!==10'sd64 || low_texture || score_u8<220 ||
            confidence_u8!==score_u8)
            $fatal(1,"scorer phase=%0d score=%0d peak=%0d second=%0d low=%b",
                phase_q4_4,score_u8,peak_zncc_q15,second_zncc_q15,low_texture);
        @(negedge clk); stats_records='0; start=1;
        @(negedge clk); start=0;
        wait(out_valid); #1;
        if (!low_texture || score_u8!=0)
            $fatal(1,"flat/empty statistics should be invalid");
        $display("PASS four-phase scorer: +4px, quality and invalid case");
        $finish;
    end
    initial begin #100000; $fatal(1,"timeout"); end
endmodule
