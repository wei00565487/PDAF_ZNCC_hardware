module dual_pd_zncc_stats_4phase_macro_farm_single(input logic clk,input logic rd_en,input logic [4:0] rd_addr,output logic rd_valid,output logic [672:0] rd_data,input logic wr_en,input logic [4:0] wr_addr,input logic [672:0] wr_data);
    zncc_stats_32x673_1r1w u_bank0(.clk,.rd_en,.rd_addr,.rd_valid,.rd_data,.wr_en,.wr_addr,.wr_data);
    for(genvar b=1;b<34;b=b+1) begin: gen_bank
        wire rv; wire [672:0] rdata; zncc_stats_32x673_1r1w u_mem(.clk,.rd_en(1'b0),.rd_addr(5'b0),.rd_valid(rv),.rd_data(rdata),.wr_en(1'b0),.wr_addr(5'b0),.wr_data(673'b0));
    end
endmodule
