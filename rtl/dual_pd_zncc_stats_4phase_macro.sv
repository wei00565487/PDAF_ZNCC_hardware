// Storage contract for repository-compatible four-Bayer-phase ZNCC stats.
// Each phase: 2x24-bit sums, 3x36-bit second moments, 12-bit pair count.
// Four phases plus one epoch bit = 673 logical bits. The selected physical
// partition is 3x192 + 104 = 680 bits; only seven tail bits are unused.
`ifndef FREEPDK45_4PHASE_SRAM_MACRO
`ifdef SYNTHESIS
(* blackbox *)
`endif
`endif
module zncc_stats_32x673_1r1w (
    input logic clk,
    input logic rd_en,
    input logic [4:0] rd_addr,
    output logic rd_valid,
    output logic [672:0] rd_data,
    input logic wr_en,
    input logic [4:0] wr_addr,
    input logic [672:0] wr_data
);
`ifdef FREEPDK45_4PHASE_SRAM_MACRO
    wire [191:0] q0, q1, q2;
    wire [103:0] q3;
    zncc_stats_32x192_1rw1r_freepdk45 u_slice0 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0),
        .addr0(wr_addr), .din0(wr_data[191:0]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1(rd_addr), .dout1(q0)
    );
    zncc_stats_32x192_1rw1r_freepdk45 u_slice1 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0),
        .addr0(wr_addr), .din0(wr_data[383:192]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1(rd_addr), .dout1(q1)
    );
    zncc_stats_32x192_1rw1r_freepdk45 u_slice2 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0),
        .addr0(wr_addr), .din0(wr_data[575:384]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1(rd_addr), .dout1(q2)
    );
    zncc_stats_32x104_1rw1r_freepdk45 u_slice3 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0),
        .addr0(wr_addr), .din0({7'b0, wr_data[672:576]}), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1(rd_addr), .dout1(q3)
    );
    assign rd_data = {q3[96:0],q2,q1,q0};
`else
    logic [672:0] mem [0:31];
    always_ff @(posedge clk) begin
        if (rd_en) rd_data <= mem[rd_addr];
        if (wr_en) mem[wr_addr] <= wr_data;
    end
    always_ff @(posedge clk) rd_valid <= rd_en;
`endif
`ifdef FREEPDK45_4PHASE_SRAM_MACRO
    always_ff @(posedge clk) rd_valid <= rd_en;
`endif
endmodule

module dual_pd_zncc_stats_4phase_macro_farm (
    input logic clk,
    input logic [33:0] rd_en,
    input logic [169:0] rd_addr,
    output logic [33:0] rd_valid,
    output logic [34*673-1:0] rd_data,
    input logic [33:0] wr_en,
    input logic [169:0] wr_addr,
    input logic [34*673-1:0] wr_data
);
    for (genvar b=0; b<34; b=b+1) begin : gen_bank
        zncc_stats_32x673_1r1w u_mem (
            .clk(clk), .rd_en(rd_en[b]), .rd_addr(rd_addr[b*5 +: 5]),
            .rd_valid(rd_valid[b]), .rd_data(rd_data[b*673 +: 673]),
            .wr_en(wr_en[b]), .wr_addr(wr_addr[b*5 +: 5]),
            .wr_data(wr_data[b*673 +: 673])
        );
    end
endmodule
