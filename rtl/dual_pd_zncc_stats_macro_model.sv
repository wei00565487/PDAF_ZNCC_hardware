// Macro binding contract for the row-streaming statistics store.
// Instantiate 17 banks per ping-pong side: depth=32 tiles, width=186 bits
// (185 statistics bits plus one epoch tag per tile/disparity entry).
// FREEPDK45_SRAM_MACRO maps each logical bank onto one generated 32x192
// OpenRAM 1RW1R macro (six high bits unused). This is a research-PDK proxy.
// SKY130_SRAM_MACRO maps each logical bank onto six available compact
// 32x256 1RW1R macros (192 physical bits; upper six data bits unused). The separate
// read port preserves concurrent read/modify/write and scanout bandwidth.
`ifdef FREEPDK45_SRAM_MACRO
module zncc_stats_32x186_1r1w (
    input logic clk,
    input logic rd_en,
    input logic [4:0] rd_addr,
    output logic rd_valid,
    output logic [185:0] rd_data,
    input logic wr_en,
    input logic [4:0] wr_addr,
    input logic [185:0] wr_data
);
    wire [191:0] rd_word;
    zncc_stats_32x192_1rw1r_freepdk45 u_macro (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0),
        .addr0(wr_addr), .din0({6'b0, wr_data}), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1(rd_addr), .dout1(rd_word)
    );
    assign rd_data = rd_word[185:0];
    always_ff @(posedge clk) rd_valid <= rd_en;
endmodule
`elsif SKY130_SRAM_MACRO
module zncc_stats_32x186_1r1w (
    input logic clk,
    input logic rd_en,
    input logic [4:0] rd_addr,
    output logic rd_valid,
    output logic [185:0] rd_data,
    input logic wr_en,
    input logic [4:0] wr_addr,
    input logic [185:0] wr_data
);
    wire [31:0] q0, q1, q2, q3, q4, q5;
    sram_1rw1r_32_256_8_sky130 m0 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0), .wmask0(4'hf),
        .addr0({3'b0,wr_addr}), .din0(wr_data[31:0]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1({3'b0,rd_addr}), .dout1(q0));
    sram_1rw1r_32_256_8_sky130 m1 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0), .wmask0(4'hf),
        .addr0({3'b0,wr_addr}), .din0(wr_data[63:32]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1({3'b0,rd_addr}), .dout1(q1));
    sram_1rw1r_32_256_8_sky130 m2 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0), .wmask0(4'hf),
        .addr0({3'b0,wr_addr}), .din0(wr_data[95:64]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1({3'b0,rd_addr}), .dout1(q2));
    sram_1rw1r_32_256_8_sky130 m3 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0), .wmask0(4'hf),
        .addr0({3'b0,wr_addr}), .din0(wr_data[127:96]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1({3'b0,rd_addr}), .dout1(q3));
    sram_1rw1r_32_256_8_sky130 m4 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0), .wmask0(4'hf),
        .addr0({3'b0,wr_addr}), .din0(wr_data[159:128]), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1({3'b0,rd_addr}), .dout1(q4));
    sram_1rw1r_32_256_8_sky130 m5 (
        .clk0(clk), .csb0(~wr_en), .web0(1'b0), .wmask0(4'b0011),
        .addr0({3'b0,wr_addr}), .din0({6'b0,wr_data[185:160]}), .dout0(),
        .clk1(clk), .csb1(~rd_en), .addr1({3'b0,rd_addr}), .dout1(q5));
    always_comb rd_data = {q5[25:0],q4,q3,q2,q1,q0};
    always_ff @(posedge clk) rd_valid <= rd_en;
endmodule
`elsif SYNTHESIS
(* blackbox *)
module zncc_stats_32x186_1r1w (
    input logic clk,
    input logic rd_en,
    input logic [4:0] rd_addr,
    output logic rd_valid,
    output logic [185:0] rd_data,
    input logic wr_en,
    input logic [4:0] wr_addr,
    input logic [185:0] wr_data
);
endmodule
`else
module zncc_stats_32x186_1r1w (
    input logic clk,
    input logic rd_en,
    input logic [4:0] rd_addr,
    output logic rd_valid,
    output logic [185:0] rd_data,
    input logic wr_en,
    input logic [4:0] wr_addr,
    input logic [185:0] wr_data
);
    logic [185:0] mem [0:31];
    always_ff @(posedge clk) begin
        rd_valid <= rd_en;
        if (rd_en) rd_data <= mem[rd_addr];
        if (wr_en) mem[wr_addr] <= wr_data;
    end
endmodule
`endif

module dual_pd_zncc_stats_macro_farm (
    input logic clk,
    input logic [33:0] rd_en,
    input logic [169:0] rd_addr,
    output logic [33:0] rd_valid,
    output logic [34*186-1:0] rd_data,
    input logic [33:0] wr_en,
    input logic [169:0] wr_addr,
    input logic [34*186-1:0] wr_data
);
    genvar b;
    generate for (b=0;b<34;b=b+1) begin : gen_stat_mem
        zncc_stats_32x186_1r1w u_mem (
            .clk(clk), .rd_en(rd_en[b]), .rd_addr(rd_addr[b*5 +: 5]),
            .rd_valid(rd_valid[b]), .rd_data(rd_data[b*186 +: 186]),
            .wr_en(wr_en[b]), .wr_addr(wr_addr[b*5 +: 5]),
            .wr_data(wr_data[b*186 +: 186])
        );
    end endgenerate
endmodule
