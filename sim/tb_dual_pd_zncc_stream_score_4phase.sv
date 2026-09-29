`timescale 1ns/1ps
module tb_dual_pd_zncc_stream_score_4phase;
    logic clk=0,rst_n=0,in_valid=0;
    logic [47:0] in_l=0,in_r=0;
    logic [3:0] in_mask_l=4'hf,in_mask_r=4'hf;
    logic band_done,band_done_bank,rd_bank=0,rd_valid,overrun;
    logic [4:0] rd_tile=0,rd_disp=0;
    logic [671:0] rd_stats;
    logic [1:0] release_bank=0,ready_bank;
    logic start=0,busy,out_valid,low_texture;
    logic [17*672-1:0] stats_records=0;
    logic signed [9:0] phase_q4_4;
    logic [7:0] score_u8,confidence_u8;
    logic signed [15:0] peak_zncc_q15,second_zncc_q15;
    always #5 clk=~clk;
    dual_pd_zncc_stream_stats_4phase #(
        .FRAME_W(64),.FRAME_H(8),.TILE_COLS(2),.TILE_ROWS(1)
    ) u_stream (
        .clk,.rst_n,.in_valid,.in_l,.in_r,.in_mask_l,.in_mask_r,
        .band_done,.band_done_bank,.rd_bank,.rd_tile,.rd_disp,
        .rd_valid,.rd_stats,.release_bank,.ready_bank,.overrun
    );
    dual_pd_zncc_scorer_4phase u_score (
        .clk,.rst_n,.start,.stats_records,.busy,.out_valid,.phase_q4_4,
        .score_u8,.confidence_u8,.peak_zncc_q15,.second_zncc_q15,.low_texture
    );
    function automatic [11:0] pix(input integer x,y);
        reg [31:0] z;
        begin
            z=32'(x*1103515245+y*1234567+93);
            z=z^(z>>13); z=z*32'd2654435761;
            pix=z[23:12];
        end
    endfunction

    integer x,y,p,g;
    initial begin
        repeat (3) @(negedge clk); rst_n=1;
        for (y=0;y<8;y=y+1) begin
            for (x=0;x<64;x=x+4) begin
                @(negedge clk); in_valid=1;
                for (p=0;p<4;p=p+1) begin
                    in_l[p*12 +: 12]=pix(x+p,y);
                    in_r[p*12 +: 12]=(x+p>=4)?pix(x+p-4,y):pix(x+p+100,y);
                end
            end
        end
        @(negedge clk); in_valid=0;
        wait(band_done);
        if (!ready_bank[0] || overrun) $fatal(1,"stream band status bad");
        for (g=0;g<17;g=g+1) begin
            @(negedge clk); rd_tile=0; rd_disp=5'(g);
            @(posedge clk); #1;
            if (!rd_valid) $fatal(1,"missing candidate %0d",g);
            stats_records[g*672 +: 672]=rd_stats;
        end
        @(negedge clk); start=1;
        @(negedge clk); start=0;
        wait(out_valid); #1;
        if (phase_q4_4!==10'sd64 || low_texture || score_u8<220)
            $fatal(1,"end-to-end phase=%0d score=%0d peak=%0d second=%0d",
                phase_q4_4,score_u8,peak_zncc_q15,second_zncc_q15);
        $display("PASS four-phase stream SRAM -> scorer: +4px, score=%0d",score_u8);
        $finish;
    end
    initial begin #100000; $fatal(1,"timeout"); end
endmodule
