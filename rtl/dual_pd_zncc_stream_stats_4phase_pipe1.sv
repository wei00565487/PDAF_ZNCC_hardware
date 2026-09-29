// P&R-oriented serialized scheduler. A beat is captured, then 17 candidates
// and four phases are processed by one arithmetic slot.
module dual_pd_zncc_stream_stats_4phase_pipe1 #(
    parameter integer PIX_W=12, FRAME_W=4000, TILE_W=125
) (
    input logic clk,rst_n,in_valid,
    input logic [4*PIX_W-1:0] in_l,in_r,
    input logic [3:0] in_mask_l,in_mask_r,
    output logic [33:0] mem_rd_en,
    output logic [169:0] mem_rd_addr,
    input logic [33:0] mem_rd_valid,
    input logic [34*673-1:0] mem_rd_data,
    output logic [33:0] mem_wr_en,
    output logic [169:0] mem_wr_addr,
    output logic [34*673-1:0] mem_wr_data,
    output logic stats_valid
);
    logic busy; logic [4:0] candidate; logic [1:0] phase; logic [11:0] x;
    logic [20*PIX_W-1:0] l_window,r_window; logic [19:0] mask_l,mask_r;
    logic [4*PIX_W-1:0] beat_l,beat_r; logic [3:0] beat_ml,beat_mr;
    logic [3:0] hist_ml,hist_mr; logic [11:0] hist_l[0:15],hist_r[0:15];
    logic delta_valid; logic [167:0] delta_stats;
    logic [4:0] delta_bank; logic [4:0] delta_tile;
    integer i;
    always_comb begin
        l_window='0; r_window='0; mask_l='0; mask_r='0;
        for(i=0;i<16;i=i+1) begin
            l_window[i*PIX_W +: PIX_W]=hist_l[i]; r_window[i*PIX_W +: PIX_W]=hist_r[i];
            mask_l[i]=1'b1; mask_r[i]=1'b1;
        end
        for(i=0;i<4;i=i+1) begin
            l_window[(16+i)*PIX_W +: PIX_W]=beat_l[i*PIX_W +: PIX_W];
            r_window[(16+i)*PIX_W +: PIX_W]=beat_r[i*PIX_W +: PIX_W];
            mask_l[16+i]=beat_ml[i]; mask_r[16+i]=beat_mr[i];
        end
    end
    dual_pd_zncc_candidate_onephase u_candidate (
        .candidate,.phase_sel(phase),.valid(busy),.x_parity(x[0]),.y_parity(1'b0),
        .l_window,.r_window,.mask_l,.mask_r,.delta_valid,.delta_stats);
    always_comb begin
        delta_bank=candidate; delta_tile=x/TILE_W;
    end
    dual_pd_zncc_stats_update_onephase u_update (
        .clk,.rst_n,.delta_valid,.delta_phase(phase),.delta_epoch(1'b0),.delta_bank,.delta_tile,
        .delta_stats,.mem_rd_en,.mem_rd_addr,.mem_rd_valid,.mem_rd_data,
        .mem_wr_en,.mem_wr_addr,.mem_wr_data);
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            busy<=0; candidate<=0; phase<=0; x<=0; stats_valid<=0; hist_ml<=0; hist_mr<=0;
            beat_l<=0; beat_r<=0; beat_ml<=0; beat_mr<=0;
            for(i=0;i<16;i=i+1) begin hist_l[i]<=0; hist_r[i]<=0; end
        end else begin
            stats_valid<=0;
            if(!busy && in_valid) begin
                busy<=1; candidate<=0; phase<=0;
                beat_l<=in_l; beat_r<=in_r; beat_ml<=in_mask_l; beat_mr<=in_mask_r;
                for(i=15;i>=4;i=i-1) begin hist_l[i]<=hist_l[i-4]; hist_r[i]<=hist_r[i-4]; end
                for(i=0;i<4;i=i+1) begin hist_l[i]<=in_l[(3-i)*PIX_W +: PIX_W]; hist_r[i]<=in_r[(3-i)*PIX_W +: PIX_W]; end
                hist_ml<=in_mask_l; hist_mr<=in_mask_r;
            end else if(busy) begin
                if(phase==3) begin
                    phase<=0;
                    if(candidate==16) begin busy<=0; stats_valid<=1; if(x>=FRAME_W-4) x<=0; else x<=x+4; end
                    else candidate<=candidate+1'b1;
                end else phase<=phase+1'b1;
            end
        end
    end
endmodule
