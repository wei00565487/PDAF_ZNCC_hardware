// 17 reusable 32-entry statistics banks for one raster row of area columns.
// Each word contains one candidate x 4 Bayer phases (673 bits).  The bank
// selector is the candidate and the row address is the area column.
module dual_pd_zncc_stats_32col_macro_farm(
    input logic clk,input logic rd_en,input logic [4:0] rd_addr,input logic [4:0] rd_bank,
    output logic rd_valid,output logic [672:0] rd_data,
    input logic wr_en,input logic [4:0] wr_addr,input logic [4:0] wr_bank,input logic [672:0] wr_data);
    logic [16:0] rv;
    logic [16:0][672:0] q;
    genvar b;
    generate for (b=0;b<17;b=b+1) begin: gen_candidate_bank
        zncc_stats_32x673_1r1w u_bank(
            .clk,.rd_en(rd_en && (rd_bank==b)),.rd_addr,
            .rd_valid(rv[b]),.rd_data(q[b]),
            .wr_en(wr_en && (wr_bank==b)),.wr_addr,.wr_data);
    end endgenerate
    always_comb begin
        rd_valid = rv[rd_bank];
        rd_data = q[rd_bank];
    end
endmodule
