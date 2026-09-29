// 4-pixel/beat, horizontal-only, 32-area-column statistics architecture.
// The core reuses 17 candidate banks, each with 32 area-column words, while
// processing four Bayer phases in time. The 16-sample history plus the
// current four-pixel beat form the horizontal delay window.
module dual_pd_zncc_pipe1_32col_top(
    input logic clk,rst_n,in_valid,
    input logic [47:0] in_l,in_r,
    input logic [3:0] in_mask_l,in_mask_r,
    output logic stats_valid);
    logic rd_en,rd_valid,wr_en;
    logic [4:0] rd_addr,wr_addr,rd_bank,wr_bank;
    logic [672:0] rd_data,wr_data;
    (* keep_hierarchy=1 *) dual_pd_zncc_stream_stats_4phase_pipe1_phys u_core(
        .clk,.rst_n,.in_valid,.in_l,.in_r,.in_mask_l,.in_mask_r,
        .mem_rd_en(rd_en),.mem_rd_addr(rd_addr),.mem_rd_bank(rd_bank),.mem_rd_valid(rd_valid),
        .mem_rd_data(rd_data),.mem_wr_en(wr_en),.mem_wr_addr(wr_addr),
        .mem_wr_data(wr_data),.stats_valid);
    (* keep_hierarchy=1 *) dual_pd_zncc_stats_32col_macro_farm u_stats(
        .clk,.rd_en,.rd_addr,.rd_bank,.rd_valid,.rd_data,
        .wr_en,.wr_addr,.wr_bank,.wr_data);
endmodule
