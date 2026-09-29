`timescale 1ns/1ps
module tb_dual_pd_zncc_stream_stats_4phase;
    logic clk=0,rst_n=0,in_valid=0;
    logic [47:0] in_l=0,in_r=0;
    logic [3:0] in_mask_l=4'hf,in_mask_r=4'hf;
    logic band_done,band_done_bank,rd_bank=0,rd_valid,overrun;
    logic [4:0] rd_tile=0,rd_disp=0;
    logic [671:0] rd_stats;
    logic [1:0] release_bank=0,ready_bank;
    always #5 clk=~clk;
    dual_pd_zncc_stream_stats_4phase #(
        .FRAME_W(32),.FRAME_H(4),.TILE_COLS(2),.TILE_ROWS(1)
    ) dut (.*);

    task automatic read_check(input integer tile,disp,expected);
        integer ph,n,off;
        begin
            @(negedge clk); rd_tile=5'(tile); rd_disp=5'(disp);
            @(posedge clk); #1;
            if (!rd_valid) $fatal(1,"missing read tile=%0d disp=%0d",tile,disp);
            n=0;
            for (ph=0;ph<4;ph=ph+1) begin
                off=ph*168+156;
                n=n+rd_stats[off +: 12];
            end
            if (n!=expected)
                $fatal(1,"count tile=%0d disp=%0d expected=%0d got=%0d",tile,disp,expected,n);
        end
    endtask

    integer x,y,p;
    initial begin
        repeat (3) @(negedge clk);
        rst_n=1;
        for (y=0;y<4;y=y+1) begin
            for (x=0;x<32;x=x+4) begin
                @(negedge clk);
                in_valid=1;
                for (p=0;p<4;p=p+1) begin
                    in_l[p*12 +: 12]=12'(x+p+y*100);
                    in_r[p*12 +: 12]=12'(x+p+y*100+11);
                end
            end
        end
        @(negedge clk); in_valid=0;
        wait(band_done);
        @(negedge clk);
        if (!ready_bank[0] || overrun) $fatal(1,"band status ready=%b overrun=%b",ready_bank,overrun);
        read_check(0,10,64); // +4, R halo crosses into tile 1
        read_check(1,10,48); // +4, right frame edge clips four columns
        read_check(0,6,48);  // -4, left frame edge clips four columns
        read_check(1,6,64);  // -4, R halo crosses into tile 0
        read_check(0,8,64);  // zero shift
        $display("PASS four-phase stream, 4px/beat, cross-tile halo and frame clipping");
        $finish;
    end
    initial begin #100000; $fatal(1,"timeout"); end
endmodule
