module dual_pd_zncc_pipe1_synth_top (
    input logic clk,rst_n,in_valid,
    input logic [47:0] in_l,in_r,
    input logic [3:0] in_mask_l,in_mask_r,
    output logic stats_valid
);
    logic [33:0] rd_en,rd_valid,wr_en;
    logic [169:0] rd_addr,wr_addr;
    logic [34*673-1:0] rd_data,wr_data;
    (* keep_hierarchy = 1 *)
    dual_pd_zncc_stream_stats_4phase_pipe1 u_core (
        .clk,.rst_n,.in_valid,.in_l,.in_r,.in_mask_l,.in_mask_r,
        .mem_rd_en(rd_en),.mem_rd_addr(rd_addr),.mem_rd_valid(rd_valid),.mem_rd_data(rd_data),
        .mem_wr_en(wr_en),.mem_wr_addr(wr_addr),.mem_wr_data(wr_data),.stats_valid);
    (* keep_hierarchy = 1 *)
    dual_pd_zncc_stats_4phase_macro_farm u_mem (
        .clk,.rd_en,.rd_addr,.rd_valid,.rd_data,.wr_en,.wr_addr,.wr_data);
endmodule
