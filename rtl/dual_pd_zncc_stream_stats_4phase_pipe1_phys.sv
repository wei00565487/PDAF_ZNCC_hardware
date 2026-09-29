module dual_pd_zncc_stream_stats_4phase_pipe1_phys #(
    parameter integer PIX_W=12, FRAME_W=4000, TILE_W=125
) (
    input logic clk,rst_n,in_valid, input logic [4*PIX_W-1:0] in_l,in_r,
    input logic [3:0] in_mask_l,in_mask_r,
    output logic mem_rd_en, output logic [4:0] mem_rd_addr, output logic [4:0] mem_rd_bank,input logic mem_rd_valid,
    input logic [672:0] mem_rd_data,output logic mem_wr_en,output logic [4:0] mem_wr_addr, output logic [4:0] mem_wr_bank,
    output logic [672:0] mem_wr_data,output logic stats_valid
);
    logic busy; logic [4:0] candidate; logic [1:0] phase; logic [11:0] x;
    logic [20*PIX_W-1:0] lw,rw; logic [19:0] ml,mr; logic [11:0] hl[0:15],hr[0:15];
    logic [4*PIX_W-1:0] bl,br; logic [3:0] bml,bmr; logic dv; logic [167:0] ds; logic [4:0] tile; integer i;
    always_comb begin
        lw='0; rw='0; ml='0; mr='0;
        for(i=0;i<16;i=i+1) begin lw[i*PIX_W +: PIX_W]=hl[i]; rw[i*PIX_W +: PIX_W]=hr[i]; ml[i]=1; mr[i]=1; end
        for(i=0;i<4;i=i+1) begin lw[(16+i)*PIX_W +: PIX_W]=bl[i*PIX_W +: PIX_W]; rw[(16+i)*PIX_W +: PIX_W]=br[i*PIX_W +: PIX_W]; ml[16+i]=bml[i]; mr[16+i]=bmr[i]; end
    end
    dual_pd_zncc_candidate_onephase u_candidate(.candidate,.phase_sel(phase),.valid(busy),.x_parity(x[0]),.y_parity(1'b0),.l_window(lw),.r_window(rw),.mask_l(ml),.mask_r(mr),.delta_valid(dv),.delta_stats(ds));
    always_comb begin
        tile=x/TILE_W;
        // One 673-bit word stores one candidate and all four phases.
        // Candidate is therefore the bank selector, while tile is the row address.
        mem_rd_bank=candidate;
    end
    dual_pd_zncc_stats_update_onephase_single u_update(.clk,.rst_n,.delta_valid(dv),.delta_phase(phase),.delta_epoch(1'b0),.delta_tile(tile),.delta_bank(candidate),.delta_stats(ds),.mem_rd_en,.mem_rd_addr,.mem_rd_valid,.mem_rd_data,.mem_wr_en,.mem_wr_addr,.mem_wr_bank,.mem_wr_data);
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin busy<=0;candidate<=0;phase<=0;x<=0;stats_valid<=0;bl<=0;br<=0;bml<=0;bmr<=0; for(i=0;i<16;i=i+1) begin hl[i]<=0;hr[i]<=0;end end
        else begin stats_valid<=0;
            if(!busy && in_valid) begin busy<=1;candidate<=0;phase<=0;bl<=in_l;br<=in_r;bml<=in_mask_l;bmr<=in_mask_r;for(i=15;i>=4;i=i-1)begin hl[i]<=hl[i-4];hr[i]<=hr[i-4];end for(i=0;i<4;i=i+1)begin hl[i]<=in_l[(3-i)*PIX_W +: PIX_W];hr[i]<=in_r[(3-i)*PIX_W +: PIX_W];end end
            else if(busy) begin if(phase==3)begin phase<=0;if(candidate==16)begin busy<=0;stats_valid<=1;if(x>=FRAME_W-4)x<=0;else x<=x+4;end else candidate<=candidate+1'b1;end else phase<=phase+1'b1;end
        end
    end
endmodule
