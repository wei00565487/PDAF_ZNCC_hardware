// Optimized 4-pixel/beat front end. Candidate groups are time-multiplexed
// over five cycles while the input history and SRAM update are shared.
module dual_pd_zncc_stream_stats_4phase_opt #(
    parameter integer PIX_W=12,
    parameter integer FRAME_W=4000,
    parameter integer TILE_W=125
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
    logic [2:0] group;
    logic [20*PIX_W-1:0] l_window,r_window;
    logic [19:0] mask_l,mask_r;
    logic [3:0] delta_valid;
    logic [4*5-1:0] delta_bank,delta_tile;
    logic [3:0] delta_epoch;
    logic [4*672-1:0] delta_stats;
    logic [11:0] history_l[0:15],history_r[0:15];
    logic [15:0] history_ml,history_mr;
    logic [11:0] x;
    integer i;

    always_comb begin
        l_window='0; r_window='0; mask_l='0; mask_r='0;
        for(i=0;i<16;i=i+1) begin
            l_window[i*PIX_W +: PIX_W]=history_l[i];
            r_window[i*PIX_W +: PIX_W]=history_r[i];
            mask_l[i]=history_ml[i]; mask_r[i]=history_mr[i];
        end
        for(i=0;i<4;i=i+1) begin
            l_window[(16+i)*PIX_W +: PIX_W]=in_l[i*PIX_W +: PIX_W];
            r_window[(16+i)*PIX_W +: PIX_W]=in_r[i*PIX_W +: PIX_W];
            mask_l[16+i]=in_mask_l[i]; mask_r[16+i]=in_mask_r[i];
        end
    end

    dual_pd_zncc_candidate_group4 u_candidates (
        .group,.valid(in_valid),.x_parity(x[0]),.y_parity(1'b0),
        .l_window,.r_window,.mask_l,.mask_r,.delta_valid,.delta_stats
    );

    always_comb begin
        for(i=0;i<4;i=i+1) begin
            delta_bank[i*5 +: 5]=group*4+i;
            delta_tile[i*5 +: 5]=x/TILE_W;
            delta_epoch[i]=1'b0;
        end
    end

    dual_pd_zncc_stats_update4 u_update (
        .clk,.rst_n,.delta_valid,.delta_epoch,.delta_bank,.delta_tile,
        .delta_stats,.mem_rd_en,.mem_rd_addr,.mem_rd_valid,.mem_rd_data,
        .mem_wr_en,.mem_wr_addr,.mem_wr_data
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            group<=0; x<=0; stats_valid<=0; history_ml<=0; history_mr<=0;
            for(i=0;i<16;i=i+1) begin history_l[i]<=0; history_r[i]<=0; end
        end else begin
            stats_valid<=1'b0;
            if(in_valid) begin
                if(group==3'd4) begin group<=0; stats_valid<=1'b1; end
                else group<=group+1'b1;
                if(x>=FRAME_W-4) x<=0; else x<=x+4;
                for(i=15;i>=4;i=i-1) begin
                    history_l[i]<=history_l[i-4]; history_r[i]<=history_r[i-4];
                    history_ml[i]<=history_ml[i-4]; history_mr[i]<=history_mr[i-4];
                end
                for(i=0;i<4;i=i+1) begin
                    history_l[i]<=in_l[(3-i)*PIX_W +: PIX_W];
                    history_r[i]<=in_r[(3-i)*PIX_W +: PIX_W];
                    history_ml[i]<=in_mask_l[3-i]; history_mr[i]<=in_mask_r[3-i];
                end
            end
        end
    end
endmodule
