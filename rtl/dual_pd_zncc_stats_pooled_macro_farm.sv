// Seventeen candidate banks, each storing one pooled 184-bit record plus
// one epoch bit. One spare bit pads the logical 185-bit word to the existing
// 186-bit 32x192 1RW1R proxy wrapper.
module dual_pd_zncc_stats_pooled_macro_farm (
    input logic clk,
    input logic [16:0] rd_en,
    input logic [4:0] rd_addr,
    output logic [16:0] rd_valid,
    output logic [17*185-1:0] rd_data,
    input logic [16:0] wr_en,
    input logic [4:0] wr_addr,
    input logic [17*185-1:0] wr_data
);
    genvar c;
    generate for (c=0;c<17;c=c+1) begin : gen_pooled_candidate_bank
        logic [185:0] q;
        zncc_stats_32x186_1r1w u_bank (
            .clk,
            .rd_en(rd_en[c]), .rd_addr,
            .rd_valid(rd_valid[c]), .rd_data(q),
            .wr_en(wr_en[c]), .wr_addr,
            .wr_data({1'b0,wr_data[c*185 +: 185]})
        );
        assign rd_data[c*185 +: 185]=q[184:0];
    end endgenerate
endmodule
