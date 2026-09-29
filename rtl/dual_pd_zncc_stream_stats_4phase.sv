// Four-pixel/beat, row-streaming Bayer-phase ZNCC statistics accumulator.
// Candidate shifts are -MAX_SHIFT..+MAX_SHIFT in two-sensor-pixel steps.
// Each 673-bit SRAM word contains four independent 168-bit phase records
// plus one epoch bit. Tile ownership follows the L sample; the matching R
// sample may lie in the neighboring tile, but never outside the frame.
module dual_pd_zncc_stream_stats_4phase #(
    parameter integer FRAME_W = 4000,
    parameter integer FRAME_H = 3000,
    parameter integer TILE_COLS = 32,
    parameter integer TILE_ROWS = 24,
    parameter integer PIX_W = 12,
    parameter integer INPUT_PIXELS = 4,
    parameter integer MAX_SHIFT = 16
) (
    input logic clk, rst_n, in_valid,
    input logic [INPUT_PIXELS*PIX_W-1:0] in_l, in_r,
    input logic [INPUT_PIXELS-1:0] in_mask_l, in_mask_r,
    output logic band_done, band_done_bank,
    input logic rd_bank,
    input logic [4:0] rd_tile,
    input logic [4:0] rd_disp,
    output logic rd_valid,
    output logic [671:0] rd_stats,
    input logic [1:0] release_bank,
    output logic [1:0] ready_bank,
    output logic overrun
);
    localparam integer TILE_W=FRAME_W/TILE_COLS;
    localparam integer TILE_H=FRAME_H/TILE_ROWS;
    localparam integer NDISP=MAX_SHIFT+1;
    localparam integer X_W=$clog2(FRAME_W);
    localparam integer Y_W=$clog2(FRAME_H);
    localparam integer PHASE_W=168;

    logic [X_W-1:0] sensor_x;
    logic [Y_W-1:0] sensor_y;
    logic [$clog2(TILE_H)-1:0] band_y;
    logic write_bank;
    logic [1:0] active_epoch, bank_ready;
    assign ready_bank=bank_ready;

    logic [PIX_W-1:0] hist_l [0:MAX_SHIFT-1];
    logic [PIX_W-1:0] hist_r [0:MAX_SHIFT-1];
    logic [MAX_SHIFT-1:0] hist_mask_l, hist_mask_r;

    wire [671:0] beat_delta0 [0:NDISP-1];
    wire [671:0] beat_delta1 [0:NDISP-1];
    wire [4:0] beat_tile0 [0:NDISP-1];
    wire [4:0] beat_tile1 [0:NDISP-1];
    wire [NDISP-1:0] beat_valid0, beat_valid1;

    // The per-phase fields are unsigned exact sums; only the scorer performs
    // mean subtraction. Counts and sums are dimensioned for 125x125 tiles.
    function automatic [671:0] add_stats(input logic [671:0] a,b);
        reg [671:0] v;
        integer ph, off;
        begin
            v='0;
            for (ph=0; ph<4; ph=ph+1) begin
                off=ph*PHASE_W;
                v[off+0 +: 24]=a[off+0 +: 24]+b[off+0 +: 24];
                v[off+24 +: 24]=a[off+24 +: 24]+b[off+24 +: 24];
                v[off+48 +: 36]=a[off+48 +: 36]+b[off+48 +: 36];
                v[off+84 +: 36]=a[off+84 +: 36]+b[off+84 +: 36];
                v[off+120 +: 36]=a[off+120 +: 36]+b[off+120 +: 36];
                v[off+156 +: 12]=a[off+156 +: 12]+b[off+156 +: 12];
            end
            add_stats=v;
        end
    endfunction

    function automatic [671:0] pair_record(
        input logic [PIX_W-1:0] a,b,
        input logic [1:0] phase
    );
        reg [671:0] v;
        reg [2*PIX_W-1:0] aa,bb,ab;
        integer off;
        begin
            v='0; off=phase*PHASE_W;
            aa=a*a; bb=b*b; ab=a*b;
            v[off+0 +: 24]=a;
            v[off+24 +: 24]=b;
            v[off+48 +: 36]=aa;
            v[off+84 +: 36]=bb;
            v[off+120 +: 36]=ab;
            v[off+156 +: 12]=12'd1;
            pair_record=v;
        end
    endfunction

    for (genvar g=0; g<NDISP; g=g+1) begin : gen_disp
        localparam integer SHIFT=2*(g-MAX_SHIFT/2);
        logic [671:0] v0,v1,pair;
        logic [4:0] tile0,tile1;
        logic valid0,valid1,mask_a,mask_b;
        logic [PIX_W-1:0] a,b;
        integer lane, lx, rx, owner_tile, hi;
        logic [1:0] phase;
        always_comb begin
            v0='0; v1='0; tile0='0; tile1='0;
            valid0=0; valid1=0;
            a='0; b='0; mask_a=0; mask_b=0;
            lx=0; rx=0; owner_tile=0; hi=0; phase='0; pair='0;
            for (lane=0; lane<INPUT_PIXELS; lane=lane+1) begin
                if (SHIFT>0) begin
                    lx=int'(sensor_x)+lane-SHIFT;
                    rx=int'(sensor_x)+lane;
                    b=in_r[lane*PIX_W +: PIX_W];
                    mask_b=in_mask_r[lane];
                    if (lane>=SHIFT) begin
                        a=in_l[(lane-SHIFT)*PIX_W +: PIX_W];
                        mask_a=in_mask_l[lane-SHIFT];
                    end else begin
                        hi=SHIFT-lane-1;
                        a=hist_l[hi];
                        mask_a=(sensor_x!=0) && hist_mask_l[hi];
                    end
                end else begin
                    lx=int'(sensor_x)+lane;
                    rx=lx+SHIFT;
                    a=in_l[lane*PIX_W +: PIX_W];
                    mask_a=in_mask_l[lane];
                    if (SHIFT<0 && lane< -SHIFT) begin
                        hi=-SHIFT-lane-1;
                        b=hist_r[hi];
                        mask_b=(sensor_x!=0) && hist_mask_r[hi];
                    end else begin
                        b=in_r[(lane+SHIFT)*PIX_W +: PIX_W];
                        mask_b=in_mask_r[lane+SHIFT];
                    end
                end
                if (lx>=0 && lx<FRAME_W && rx>=0 && rx<FRAME_W &&
                    mask_a && mask_b) begin
                    owner_tile=lx/TILE_W;
                    phase={sensor_y[0],1'(lx & 1)};
                    pair=pair_record(a,b,phase);
                    if (!valid0 || owner_tile==int'(tile0)) begin
                        if (!valid0) tile0=5'(owner_tile);
                        v0=add_stats(v0,pair);
                        valid0=1;
                    end else begin
                        if (!valid1) tile1=5'(owner_tile);
                        v1=add_stats(v1,pair);
                        valid1=1;
                    end
                end
            end
        end
        assign beat_delta0[g]=v0;
        assign beat_delta1[g]=v1;
        assign beat_tile0[g]=tile0;
        assign beat_tile1[g]=tile1;
        assign beat_valid0[g]=valid0;
        assign beat_valid1[g]=valid1;
    end

    logic pipe_valid, pipe_bank, pipe_epoch;
    logic [671:0] pipe_delta0 [0:NDISP-1], pipe_delta1 [0:NDISP-1];
    logic [4:0] pipe_tile0 [0:NDISP-1], pipe_tile1 [0:NDISP-1];
    logic [NDISP-1:0] pipe_v0,pipe_v1;
    logic [NDISP-1:0] carry_valid;
    logic [671:0] carry_delta [0:NDISP-1];
    logic [4:0] carry_tile [0:NDISP-1];
    logic [NDISP-1:0] carry_bank,carry_epoch;
    logic [NDISP-1:0] tx_valid,tx_bank,tx_epoch;
    logic [671:0] tx_delta [0:NDISP-1];
    logic [4:0] tx_tile [0:NDISP-1];
    logic [NDISP-1:0] tx_collision;

    for (genvar g=0; g<NDISP; g=g+1) begin : gen_tx
        always_comb begin
            tx_valid[g]=carry_valid[g] || (pipe_valid && pipe_v0[g]);
            tx_bank[g]=carry_valid[g] ? carry_bank[g] : pipe_bank;
            tx_epoch[g]=carry_valid[g] ? carry_epoch[g] : pipe_epoch;
            tx_tile[g]=carry_valid[g] ? carry_tile[g] : pipe_tile0[g];
            tx_delta[g]=carry_valid[g] ? carry_delta[g] : '0;
            tx_collision[g]=carry_valid[g] && pipe_valid && pipe_v0[g] &&
                (carry_tile[g]!=pipe_tile0[g] || carry_bank[g]!=pipe_bank);
            if (pipe_valid && pipe_v0[g] && !tx_collision[g])
                tx_delta[g]=add_stats(tx_delta[g],pipe_delta0[g]);
        end
    end

    logic [33:0] mem_rd_en, mem_update_rd, mem_rd_valid, mem_wr_en;
    logic [169:0] mem_rd_addr,mem_wr_addr;
    logic [34*673-1:0] mem_rd_data,mem_wr_data;
    logic [33:0] req_valid,req_epoch;
    logic [4:0] req_addr [0:33];
    logic [671:0] req_delta [0:33];
    logic [33:0] bypass_valid;
    logic [672:0] bypass_data [0:33];
    logic ext_accept,ext_sel_valid,ext_sel_bank,ext_sel_epoch;
    logic [4:0] ext_sel_disp;
    integer m,j,idx;

    always_comb begin
        mem_rd_en='0; mem_update_rd='0; mem_rd_addr='0;
        mem_wr_en='0; mem_wr_addr='0; mem_wr_data='0;
        ext_accept=0; idx=0;
        for (m=0;m<34;m=m+1) begin
            if (req_valid[m] && mem_rd_valid[m]) begin
                mem_wr_en[m]=1;
                mem_wr_addr[m*5 +: 5]=req_addr[m];
                if ((bypass_valid[m]?bypass_data[m][672]:mem_rd_data[m*673+672])==req_epoch[m])
                    mem_wr_data[m*673 +: 673]={req_epoch[m],add_stats(
                        bypass_valid[m]?bypass_data[m][671:0]:mem_rd_data[m*673 +: 672],
                        req_delta[m])};
                else mem_wr_data[m*673 +: 673]={req_epoch[m],req_delta[m]};
            end
        end
        for (j=0;j<NDISP;j=j+1) begin
            if (tx_valid[j]) begin
                idx=tx_bank[j]*NDISP+j;
                mem_rd_en[idx]=1; mem_update_rd[idx]=1;
                mem_rd_addr[idx*5 +: 5]=tx_tile[j];
            end
        end
        if (rd_bank!=write_bank && bank_ready[rd_bank] && rd_disp<NDISP) begin
            idx=rd_bank*NDISP+rd_disp;
            if (!mem_rd_en[idx]) begin
                mem_rd_en[idx]=1;
                mem_rd_addr[idx*5 +: 5]=rd_tile;
                ext_accept=1;
            end
        end
    end

    dual_pd_zncc_stats_4phase_macro_farm u_stats_mem (
        .clk, .rd_en(mem_rd_en), .rd_addr(mem_rd_addr),
        .rd_valid(mem_rd_valid), .rd_data(mem_rd_data),
        .wr_en(mem_wr_en), .wr_addr(mem_wr_addr), .wr_data(mem_wr_data)
    );

    always_comb begin
        rd_valid=0; rd_stats='0;
        for (integer k=0;k<34;k=k+1) begin
            if (ext_sel_bank*NDISP+ext_sel_disp==k) begin
                rd_valid=ext_sel_valid && mem_rd_valid[k] &&
                    (mem_rd_data[k*673+672]==ext_sel_epoch);
                if (rd_valid) rd_stats=mem_rd_data[k*673 +: 672];
            end
        end
    end

    logic [2:0] flush_count;
    logic flush_bank;
    always_ff @(posedge clk or negedge rst_n) begin : stream_ctrl
        integer i,k,mi;
        if (!rst_n) begin
            sensor_x<='0; sensor_y<='0; band_y<='0; write_bank<=0;
            active_epoch<=0; bank_ready<=0; band_done<=0;
            band_done_bank<=0; overrun<=0; flush_count<=0; flush_bank<=0;
            pipe_valid<=0; pipe_bank<=0; pipe_epoch<=0; pipe_v0<='0; pipe_v1<='0;
            carry_valid<='0; carry_bank<='0; carry_epoch<='0;
            req_valid<='0; req_epoch<='0; bypass_valid<='0;
            ext_sel_valid<=0; ext_sel_bank<=0; ext_sel_epoch<=0; ext_sel_disp<=0;
            hist_mask_l<='0; hist_mask_r<='0;
            for (i=0;i<MAX_SHIFT;i=i+1) begin hist_l[i]<='0; hist_r[i]<='0; end
            for (i=0;i<NDISP;i=i+1) begin
                pipe_delta0[i]<='0; pipe_delta1[i]<='0;
                pipe_tile0[i]<=0; pipe_tile1[i]<=0;
                carry_delta[i]<='0; carry_tile[i]<=0;
            end
            for (i=0;i<34;i=i+1) begin
                req_addr[i]<=0; req_delta[i]<='0; bypass_data[i]<='0;
            end
        end else begin
            band_done<=0;
            if (release_bank[0]) bank_ready[0]<=0;
            if (release_bank[1]) bank_ready[1]<=0;
            if (flush_count!=0) begin
                flush_count<=flush_count-1'b1;
                if (flush_count==1) begin
                    band_done<=1; band_done_bank<=flush_bank;
                    bank_ready[flush_bank]<=1;
                end
            end
            for (i=0;i<34;i=i+1) begin
                req_valid[i]<=0;
                bypass_valid[i]<=mem_wr_en[i] && mem_update_rd[i] &&
                    (mem_wr_addr[i*5 +: 5]==mem_rd_addr[i*5 +: 5]);
                if (mem_wr_en[i] && mem_update_rd[i] &&
                    mem_wr_addr[i*5 +: 5]==mem_rd_addr[i*5 +: 5])
                    bypass_data[i]<=mem_wr_data[i*673 +: 673];
            end
            if (ext_accept) begin
                ext_sel_valid<=1; ext_sel_bank<=rd_bank;
                ext_sel_epoch<=active_epoch[rd_bank]; ext_sel_disp<=rd_disp;
            end else ext_sel_valid<=0;

            for (i=0;i<NDISP;i=i+1) begin
                if (tx_collision[i]) overrun<=1;
                if (tx_valid[i]) begin
                    mi=tx_bank[i]*NDISP+i;
                    req_valid[mi]<=1;
                    req_epoch[mi]<=tx_epoch[i];
                    req_addr[mi]<=tx_tile[i];
                    req_delta[mi]<=tx_delta[i];
                end
                if (pipe_valid) begin
                    carry_valid[i]<=pipe_v1[i];
                    if (pipe_v1[i]) begin
                        carry_bank[i]<=pipe_bank;
                        carry_epoch[i]<=pipe_epoch;
                        carry_tile[i]<=pipe_tile1[i];
                        carry_delta[i]<=pipe_delta1[i];
                    end
                end else if (carry_valid[i]) carry_valid[i]<=0;
            end

            pipe_valid<=in_valid;
            if (in_valid) begin
                pipe_bank<=write_bank; pipe_epoch<=active_epoch[write_bank];
                for (i=0;i<NDISP;i=i+1) begin
                    pipe_v0[i]<=beat_valid0[i]; pipe_v1[i]<=beat_valid1[i];
                    pipe_tile0[i]<=beat_tile0[i]; pipe_tile1[i]<=beat_tile1[i];
                    pipe_delta0[i]<=beat_delta0[i]; pipe_delta1[i]<=beat_delta1[i];
                end
                for (i=MAX_SHIFT-1;i>=INPUT_PIXELS;i=i-1) begin
                    hist_l[i]<=hist_l[i-INPUT_PIXELS];
                    hist_r[i]<=hist_r[i-INPUT_PIXELS];
                    hist_mask_l[i]<=hist_mask_l[i-INPUT_PIXELS];
                    hist_mask_r[i]<=hist_mask_r[i-INPUT_PIXELS];
                end
                for (i=0;i<INPUT_PIXELS;i=i+1) begin
                    hist_l[i]<=in_l[(INPUT_PIXELS-1-i)*PIX_W +: PIX_W];
                    hist_r[i]<=in_r[(INPUT_PIXELS-1-i)*PIX_W +: PIX_W];
                    hist_mask_l[i]<=in_mask_l[INPUT_PIXELS-1-i];
                    hist_mask_r[i]<=in_mask_r[INPUT_PIXELS-1-i];
                end
                if (sensor_x==FRAME_W-INPUT_PIXELS) begin
                    sensor_x<=0;
                    if (sensor_y==FRAME_H-1) sensor_y<=0;
                    else sensor_y<=sensor_y+1'b1;
                    if (band_y==TILE_H-1) begin
                        band_y<=0;
                        flush_count<=3; flush_bank<=write_bank;
                        write_bank<=~write_bank;
                        if (bank_ready[~write_bank] && !release_bank[~write_bank]) overrun<=1;
                        active_epoch[~write_bank]<=~active_epoch[~write_bank];
                    end else band_y<=band_y+1'b1;
                end else sensor_x<=sensor_x+INPUT_PIXELS;
            end
        end
    end
endmodule
