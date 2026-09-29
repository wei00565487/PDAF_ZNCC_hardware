// Single-bank, single-phase read-modify-write update.
module dual_pd_zncc_stats_update_onephase (
    input logic clk,rst_n,
    input logic delta_valid,
    input logic [1:0] delta_phase,
    input logic delta_epoch,
    input logic [4:0] delta_bank,delta_tile,
    input logic [167:0] delta_stats,
    output logic [33:0] mem_rd_en,
    output logic [169:0] mem_rd_addr,
    input logic [33:0] mem_rd_valid,
    input logic [34*673-1:0] mem_rd_data,
    output logic [33:0] mem_wr_en,
    output logic [169:0] mem_wr_addr,
    output logic [34*673-1:0] mem_wr_data
);
    logic req_valid,req_epoch;
    logic [1:0] req_phase;
    logic [4:0] req_bank,req_tile;
    logic [167:0] req_stats;
    logic [672:0] old_word,new_word;
    logic [167:0] old_phase,add_phase;
    integer b;
    always_comb begin
        mem_rd_en='0; mem_rd_addr='0; mem_wr_en='0; mem_wr_addr='0; mem_wr_data='0;
        if (delta_valid) begin
            mem_rd_en[delta_bank]=1'b1;
            mem_rd_addr[delta_bank*5 +: 5]=delta_tile;
        end
        old_word='0;
        for (b=0;b<34;b=b+1) begin
            if (req_bank==b) old_word=mem_rd_data[b*673 +: 673];
        end
        old_phase=old_word[req_phase*168 +: 168];
        add_phase='0;
        add_phase[23:0]=old_phase[23:0]+req_stats[23:0];
        add_phase[47:24]=old_phase[47:24]+req_stats[47:24];
        add_phase[83:48]=old_phase[83:48]+req_stats[83:48];
        add_phase[119:84]=old_phase[119:84]+req_stats[119:84];
        add_phase[155:120]=old_phase[155:120]+req_stats[155:120];
        add_phase[167:156]=old_phase[167:156]+req_stats[167:156];
        new_word=old_word;
        new_word[req_phase*168 +: 168]=add_phase;
        if (req_valid && mem_rd_valid[req_bank]) begin
            mem_wr_en[req_bank]=1'b1;
            mem_wr_addr[req_bank*5 +: 5]=req_tile;
            mem_wr_data[req_bank*673 +: 673]={req_epoch,new_word[671:0]};
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            req_valid<=0; req_phase<=0; req_epoch<=0; req_bank<=0; req_tile<=0; req_stats<='0;
        end else begin
            req_valid<=delta_valid; req_phase<=delta_phase; req_epoch<=delta_epoch;
            req_bank<=delta_bank; req_tile<=delta_tile; req_stats<=delta_stats;
        end
    end
endmodule
