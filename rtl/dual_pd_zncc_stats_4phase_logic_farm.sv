// Logic-only P&R proxy for the external SRAM farm.
// The real macro is evaluated separately from its LEF area and liberty timing.
module dual_pd_zncc_stats_4phase_logic_farm(
    input logic clk,input logic rd_en,input logic [4:0] rd_addr,
    output logic rd_valid,output logic [672:0] rd_data,
    input logic wr_en,input logic [4:0] wr_addr,input logic [672:0] wr_data);
    logic [672:0] mem [0:31];
    always_ff @(posedge clk) begin
        rd_valid <= rd_en;
        if (rd_en) rd_data <= mem[rd_addr];
        if (wr_en) mem[wr_addr] <= wr_data;
    end
endmodule
