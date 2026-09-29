// Four-way shared read-modify-write scheduler for the 34-bank 673-bit farm.
module dual_pd_zncc_stats_update4 (
    input logic clk,rst_n,
    input logic [3:0] delta_valid,
    input logic [3:0] delta_epoch,
    input logic [4*5-1:0] delta_bank,
    input logic [4*5-1:0] delta_tile,
    input logic [4*672-1:0] delta_stats,
    output logic [33:0] mem_rd_en,
    output logic [169:0] mem_rd_addr,
    input logic [33:0] mem_rd_valid,
    input logic [34*673-1:0] mem_rd_data,
    output logic [33:0] mem_wr_en,
    output logic [169:0] mem_wr_addr,
    output logic [34*673-1:0] mem_wr_data
);
    function automatic [671:0] add_stats(input logic [671:0] a,b);
        reg [671:0] v; integer p,o;
        begin
            v='0;
            for(p=0;p<4;p=p+1) begin
                o=p*168;
                v[o +: 24]=a[o +: 24]+b[o +: 24];
                v[o+24 +: 24]=a[o+24 +: 24]+b[o+24 +: 24];
                v[o+48 +: 36]=a[o+48 +: 36]+b[o+48 +: 36];
                v[o+84 +: 36]=a[o+84 +: 36]+b[o+84 +: 36];
                v[o+120 +: 36]=a[o+120 +: 36]+b[o+120 +: 36];
                v[o+156 +: 12]=a[o+156 +: 12]+b[o+156 +: 12];
            end
            add_stats=v;
        end
    endfunction
    logic [3:0] req_valid,req_epoch;
    logic [4:0] req_bank[0:3],req_tile[0:3];
    logic [671:0] req_stats[0:3];
    integer s,b;
    always_comb begin
        mem_rd_en='0; mem_rd_addr='0; mem_wr_en='0;
        mem_wr_addr='0; mem_wr_data='0;
        for(s=0;s<4;s=s+1) begin
            if(delta_valid[s]) begin
                mem_rd_en[delta_bank[s*5 +: 5]]=1'b1;
                mem_rd_addr[delta_bank[s*5 +: 5]*5 +: 5]=delta_tile[s*5 +: 5];
            end
            if(req_valid[s] && mem_rd_valid[req_bank[s]]) begin
                mem_wr_en[req_bank[s]]=1'b1;
                mem_wr_addr[req_bank[s]*5 +: 5]=req_tile[s];
                mem_wr_data[req_bank[s]*673 +: 673]={req_epoch[s],
                    add_stats(mem_rd_data[req_bank[s]*673 +: 672],req_stats[s])};
            end
        end
    end
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            req_valid<='0;
            for(b=0;b<4;b=b+1) begin req_bank[b]<='0;req_tile[b]<='0;req_stats[b]<='0;req_epoch[b]<=0; end
        end else begin
            for(b=0;b<4;b=b+1) begin
                req_valid[b]<=delta_valid[b];
                req_bank[b]<=delta_bank[b*5 +: 5];
                req_tile[b]<=delta_tile[b*5 +: 5];
                req_stats[b]<=delta_stats[b*672 +: 672];
                req_epoch[b]<=delta_epoch[b];
            end
        end
    end
endmodule
