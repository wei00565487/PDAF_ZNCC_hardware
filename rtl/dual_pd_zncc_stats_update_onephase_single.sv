// P&R abstraction: one serialized SRAM port. The physical wrapper below
// retains all 34 SRAM banks; the logic core avoids a 34x673 dynamic mux.
module dual_pd_zncc_stats_update_onephase_single (
    input logic clk,rst_n,
    input logic delta_valid,
    input logic [1:0] delta_phase,
    input logic delta_epoch,
    input logic [4:0] delta_tile,
    input logic [4:0] delta_bank,
    input logic [167:0] delta_stats,
    output logic mem_rd_en,
    output logic [4:0] mem_rd_addr,
    input logic mem_rd_valid,
    input logic [672:0] mem_rd_data,
    output logic mem_wr_en,
    output logic [4:0] mem_wr_addr,
    output logic [4:0] mem_wr_bank,
    output logic [672:0] mem_wr_data
);
    logic req_valid,req_epoch; logic [1:0] req_phase; logic [4:0] req_tile,req_bank;
    logic [167:0] req_stats; logic [167:0] old_phase,add_phase; logic [672:0] new_word;
    always_comb begin
        mem_rd_en=delta_valid; mem_rd_addr=delta_tile; mem_wr_en=0; mem_wr_addr=req_tile; mem_wr_bank=req_bank; mem_wr_data='0;
        old_phase=mem_rd_data[req_phase*168 +: 168]; add_phase='0;
        add_phase[23:0]=old_phase[23:0]+req_stats[23:0];
        add_phase[47:24]=old_phase[47:24]+req_stats[47:24];
        add_phase[83:48]=old_phase[83:48]+req_stats[83:48];
        add_phase[119:84]=old_phase[119:84]+req_stats[119:84];
        add_phase[155:120]=old_phase[155:120]+req_stats[155:120];
        add_phase[167:156]=old_phase[167:156]+req_stats[167:156];
        new_word=mem_rd_data; new_word[req_phase*168 +: 168]=add_phase;
        if(req_valid && mem_rd_valid) begin mem_wr_en=1; mem_wr_data={req_epoch,new_word[671:0]}; end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin req_valid<=0; req_epoch<=0; req_phase<=0; req_tile<=0; req_bank<=0; req_stats<='0; end
        else begin req_valid<=delta_valid; req_epoch<=delta_epoch; req_phase<=delta_phase; req_tile<=delta_tile; req_bank<=delta_bank; req_stats<=delta_stats; end
    end
endmodule
