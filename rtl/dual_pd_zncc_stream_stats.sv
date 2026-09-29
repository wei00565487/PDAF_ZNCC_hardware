// SRAM-backed four-pixel/beat row-streaming ZNCC statistics accumulator.
// Statistics are stored as 34 synchronous 32x186 1R1W macros: 17 disparities
// on each ping-pong side, with a per-entry epoch tag in bit 185.
module dual_pd_zncc_stream_stats #(
    parameter integer FRAME_W = 4000,
    parameter integer FRAME_H = 3000,
    parameter integer TILE_COLS = 32,
    parameter integer TILE_ROWS = 24,
    parameter integer TILE_W = FRAME_W / TILE_COLS,
    parameter integer TILE_H = FRAME_H / TILE_ROWS,
    parameter integer PIX_W = 12,
    parameter integer INPUT_PIXELS = 4,
    parameter integer MAX_D = 8,
    parameter integer SUM_W = PIX_W + $clog2(TILE_W*TILE_H) + 1,
    parameter integer SQ_W = 2*PIX_W + $clog2(TILE_W*TILE_H) + 1,
    parameter integer CNT_W = $clog2(TILE_W*TILE_H + 1),
    parameter integer COL_W = $clog2(TILE_COLS),
    parameter integer DISP_W = $clog2(2*MAX_D+1),
    parameter integer CTX_COUNT = 2*TILE_COLS*(2*MAX_D+1),
    parameter integer CTX_W = $clog2(CTX_COUNT)
) (
    input logic clk, rst_n, in_valid,
    input logic [INPUT_PIXELS*PIX_W-1:0] in_l, in_r,
    output logic band_done, band_done_bank,
    input logic rd_bank,
    input logic [COL_W-1:0] rd_tile,
    input logic [DISP_W-1:0] rd_disp,
    output logic rd_valid,
    output logic [SUM_W-1:0] rd_sum_l, rd_sum_r,
    output logic [SQ_W-1:0] rd_sum_ll, rd_sum_rr, rd_sum_lr,
    output logic [CNT_W-1:0] rd_count,
    input logic [1:0] release_bank,
    output logic [1:0] ready_bank,
    output logic overrun
);
    localparam integer NDISP=2*MAX_D+1;
    localparam integer SRAM_DISP=17;
    localparam integer X_W=$clog2(FRAME_W);
    localparam integer STAT_BITS=2*SUM_W+3*SQ_W+CNT_W;
    localparam integer N_OFF=2*SUM_W+3*SQ_W;

    logic [X_W-1:0] sensor_x;
    logic [COL_W-1:0] tile_col_x;
    logic [$clog2(TILE_W)-1:0] tile_col_offset;
    logic [$clog2(TILE_H)-1:0] tile_band_y;
    logic write_bank;
    logic [1:0] active_epoch, bank_ready;
    assign ready_bank=bank_ready;

    logic [PIX_W-1:0] hist_l [0:MAX_D-1], hist_r [0:MAX_D-1];
    logic [PIX_W-1:0] hist_l_work [0:MAX_D-1], hist_r_work [0:MAX_D-1];
    logic [MAX_D*PIX_W-1:0] hist_l_bus, hist_r_bus;
    wire [SUM_W-1:0] d0_l [0:NDISP-1], d0_r [0:NDISP-1];
    wire [SQ_W-1:0] d0_ll [0:NDISP-1], d0_rr [0:NDISP-1], d0_lr [0:NDISP-1];
    wire [CNT_W-1:0] d0_n [0:NDISP-1];
    wire [SUM_W-1:0] d1_l [0:NDISP-1], d1_r [0:NDISP-1];
    wire [SQ_W-1:0] d1_ll [0:NDISP-1], d1_rr [0:NDISP-1], d1_lr [0:NDISP-1];
    wire [CNT_W-1:0] d1_n [0:NDISP-1];
    logic pipe_valid, pipe_bank, pipe_epoch, pipe_last;
    logic [COL_W-1:0] pipe_tile0, pipe_tile1;
    logic [184:0] pipe_stats0 [0:NDISP-1], pipe_stats1 [0:NDISP-1];

    logic carry_valid, carry_bank, carry_epoch;
    logic [COL_W-1:0] carry_tile;
    logic [184:0] carry_stats [0:NDISP-1];
    logic tx_valid, tx_bank, tx_epoch;
    logic [COL_W-1:0] tx_tile;
    logic [184:0] tx_stats [0:NDISP-1];

    logic [33:0] mem_rd_en, mem_update_rd, mem_rd_valid, mem_wr_en;
    logic [169:0] mem_rd_addr, mem_wr_addr;
    logic [34*186-1:0] mem_rd_data, mem_wr_data;
    logic [33:0] req_valid, req_bank, req_epoch, req_last;
    logic [4:0] req_addr [0:33];
    logic [184:0] req_delta [0:33];
    logic [33:0] bypass_valid;
    logic [185:0] bypass_data [0:33];
    logic ext_sel_valid, ext_sel_bank, ext_sel_epoch;
    logic [DISP_W-1:0] ext_sel_disp;
    logic ext_accept;
    integer t0, t1, h, q, m, mem_calc_idx, out_m;

    genvar g;
    generate for (g=0; g<NDISP; g=g+1) begin : gen_disp
        dual_pd_zncc_disp4 #(
            .PIX_W(PIX_W), .INPUT_PIXELS(INPUT_PIXELS), .MAX_D(MAX_D),
            .DISP(g-MAX_D), .TILE_W(TILE_W), .SUM_W(SUM_W), .SQ_W(SQ_W), .CNT_W(CNT_W)
        ) u_disp (
            .in_l(in_l), .in_r(in_r), .hist_l(hist_l_bus), .hist_r(hist_r_bus),
            .x_offset(tile_col_offset), .delta0_l(d0_l[g]), .delta0_r(d0_r[g]),
            .delta0_ll(d0_ll[g]), .delta0_rr(d0_rr[g]), .delta0_lr(d0_lr[g]),
            .delta0_n(d0_n[g]), .delta1_l(d1_l[g]), .delta1_r(d1_r[g]),
            .delta1_ll(d1_ll[g]), .delta1_rr(d1_rr[g]), .delta1_lr(d1_lr[g]),
            .delta1_n(d1_n[g])
        );
    end endgenerate

    function automatic [184:0] pack_stats(
        input logic [SUM_W-1:0] sl, sr,
        input logic [SQ_W-1:0] sll, srr, slr,
        input logic [CNT_W-1:0] n
    );
        reg [184:0] v;
        begin
            v='0;
            v[0 +: SUM_W]=sl;
            v[SUM_W +: SUM_W]=sr;
            v[2*SUM_W +: SQ_W]=sll;
            v[2*SUM_W+SQ_W +: SQ_W]=srr;
            v[2*SUM_W+2*SQ_W +: SQ_W]=slr;
            v[N_OFF +: CNT_W]=n;
            pack_stats=v;
        end
    endfunction

    function automatic [184:0] add_stats(input logic [184:0] a, b);
        reg [184:0] v;
        begin
            v='0;
            v[0 +: SUM_W]=a[0 +: SUM_W]+b[0 +: SUM_W];
            v[SUM_W +: SUM_W]=a[SUM_W +: SUM_W]+b[SUM_W +: SUM_W];
            v[2*SUM_W +: SQ_W]=a[2*SUM_W +: SQ_W]+b[2*SUM_W +: SQ_W];
            v[2*SUM_W+SQ_W +: SQ_W]=a[2*SUM_W+SQ_W +: SQ_W]+b[2*SUM_W+SQ_W +: SQ_W];
            v[2*SUM_W+2*SQ_W +: SQ_W]=a[2*SUM_W+2*SQ_W +: SQ_W]+b[2*SUM_W+2*SQ_W +: SQ_W];
            v[N_OFF +: CNT_W]=a[N_OFF +: CNT_W]+b[N_OFF +: CNT_W];
            add_stats=v;
        end
    endfunction

    always_comb begin
        t0=tile_col_x;
        t1=tile_col_x+((tile_col_offset+INPUT_PIXELS-1)>=TILE_W);
        hist_l_bus='0; hist_r_bus='0;
        for (h=0; h<MAX_D; h=h+1) begin
            hist_l_work[h]=(sensor_x==0)?'0:hist_l[h];
            hist_r_work[h]=(sensor_x==0)?'0:hist_r[h];
            hist_l_bus[h*PIX_W +: PIX_W]=hist_l_work[h];
            hist_r_bus[h*PIX_W +: PIX_W]=hist_r_work[h];
        end
        tx_valid=pipe_valid||carry_valid;
        tx_bank=pipe_valid?pipe_bank:carry_bank;
        tx_epoch=pipe_valid?pipe_epoch:carry_epoch;
        tx_tile=pipe_valid?pipe_tile0:carry_tile;
        for (q=0; q<NDISP; q=q+1) begin
            tx_stats[q]=pipe_valid?pipe_stats0[q]:185'b0;
            if (carry_valid) tx_stats[q]=add_stats(tx_stats[q],carry_stats[q]);
        end

        mem_rd_en='0; mem_update_rd='0; mem_rd_addr='0;
        mem_wr_en='0; mem_wr_addr='0; mem_wr_data='0;
        ext_accept=1'b0; mem_calc_idx=0;
        for (m=0; m<34; m=m+1) begin
            if (req_valid[m] && mem_rd_valid[m]) begin
                mem_wr_en[m]=1'b1;
                mem_wr_addr[m*5 +: 5]=req_addr[m];
                if ((bypass_valid[m]?bypass_data[m][185]:mem_rd_data[m*186+185])==req_epoch[m])
                    mem_wr_data[m*186 +: 186]={req_epoch[m],add_stats(
                        bypass_valid[m]?bypass_data[m][184:0]:mem_rd_data[m*186 +: 185],req_delta[m])};
                else mem_wr_data[m*186 +: 186]={req_epoch[m],req_delta[m]};
            end
        end
        for (q=0; q<NDISP; q=q+1) begin
            if (tx_valid && (tx_stats[q][N_OFF +: CNT_W]!=0)) begin
                mem_calc_idx=tx_bank*SRAM_DISP+q;
                mem_rd_en[mem_calc_idx]=1'b1; mem_update_rd[mem_calc_idx]=1'b1;
                mem_rd_addr[mem_calc_idx*5 +: 5]=tx_tile;
            end
        end
        // The reader uses the opposite ping-pong side. Update reads have
        // priority if a consumer accidentally addresses the writer side.
        if (rd_bank!=write_bank && bank_ready[rd_bank]) begin
            mem_calc_idx=rd_bank*SRAM_DISP+rd_disp;
            if (!mem_rd_en[mem_calc_idx]) begin
                mem_rd_en[mem_calc_idx]=1'b1;
                mem_rd_addr[mem_calc_idx*5 +: 5]=rd_tile;
                ext_accept=1'b1;
            end
        end
    end

    dual_pd_zncc_stats_macro_farm u_stats_mem (
        .clk, .rd_en(mem_rd_en), .rd_addr(mem_rd_addr), .rd_valid(mem_rd_valid),
        .rd_data(mem_rd_data), .wr_en(mem_wr_en), .wr_addr(mem_wr_addr), .wr_data(mem_wr_data)
    );

    always_comb begin
        rd_valid=1'b0;
        rd_sum_l='0; rd_sum_r='0; rd_sum_ll='0; rd_sum_rr='0; rd_sum_lr='0; rd_count='0;
        for (out_m=0; out_m<34; out_m=out_m+1) begin
            if ((ext_sel_bank*SRAM_DISP+ext_sel_disp)==out_m) begin
                rd_valid=ext_sel_valid && mem_rd_valid[out_m] &&
                         (mem_rd_data[out_m*186+185]==ext_sel_epoch);
                rd_sum_l=rd_valid?mem_rd_data[out_m*186 +: SUM_W]:'0;
                rd_sum_r=rd_valid?mem_rd_data[out_m*186+SUM_W +: SUM_W]:'0;
                rd_sum_ll=rd_valid?mem_rd_data[out_m*186+2*SUM_W +: SQ_W]:'0;
                rd_sum_rr=rd_valid?mem_rd_data[out_m*186+2*SUM_W+SQ_W +: SQ_W]:'0;
                rd_sum_lr=rd_valid?mem_rd_data[out_m*186+2*SUM_W+2*SQ_W +: SQ_W]:'0;
                rd_count=rd_valid?mem_rd_data[out_m*186+N_OFF +: CNT_W]:'0;
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin : stream_ctrl
        integer i, j, wi;
        logic carry_has_data;
        if (!rst_n) begin
            sensor_x<='0; tile_col_x<='0; tile_col_offset<='0; tile_band_y<='0;
            write_bank<=1'b0; active_epoch<=2'b11; bank_ready<=2'b00;
            band_done<=1'b0; band_done_bank<=1'b0; overrun<=1'b0;
            pipe_valid<=1'b0; pipe_bank<=1'b0; pipe_epoch<=1'b0; pipe_last<=1'b0;
            pipe_tile0<='0; pipe_tile1<='0; carry_valid<=1'b0; carry_bank<=1'b0;
            carry_epoch<=1'b0; carry_tile<='0; req_valid<='0; bypass_valid<='0;
            ext_sel_valid<=1'b0; ext_sel_bank<=1'b0; ext_sel_epoch<=1'b0; ext_sel_disp<='0;
            for (i=0; i<MAX_D; i=i+1) begin hist_l[i]<='0; hist_r[i]<='0; end
            for (i=0; i<34; i=i+1) begin req_addr[i]<='0; req_delta[i]<='0; req_bank[i]<=1'b0;
                req_epoch[i]<=1'b0; req_last[i]<=1'b0; bypass_data[i]<='0; end
            for (i=0; i<NDISP; i=i+1) begin pipe_stats0[i]<='0; pipe_stats1[i]<='0; carry_stats[i]<='0; end
        end else begin
            band_done<=1'b0;
            if (release_bank[0]) bank_ready[0]<=1'b0;
            if (release_bank[1]) bank_ready[1]<=1'b0;

            // SRAM synchronous-read response: add the registered delta and
            // write it back. Last-write forwarding handles consecutive beats
            // that update the same tile/disparity address.
            for (i=0; i<34; i=i+1) begin
                req_valid[i]<=1'b0;
                bypass_valid[i]<=mem_wr_en[i] && mem_update_rd[i] &&
                                  (mem_wr_addr[i*5 +: 5]==mem_rd_addr[i*5 +: 5]);
                if (mem_wr_en[i] && mem_update_rd[i] &&
                    (mem_wr_addr[i*5 +: 5]==mem_rd_addr[i*5 +: 5]))
                    bypass_data[i]<=mem_wr_data[i*186 +: 186];
                if (mem_wr_en[i] && req_last[i] && ((i%SRAM_DISP)==MAX_D)) begin
                    band_done<=1'b1; band_done_bank<=req_bank[i];
                    bank_ready[req_bank[i]]<=1'b1;
                end
            end

            if (ext_accept) begin
                ext_sel_valid<=1'b1; ext_sel_bank<=rd_bank;
                ext_sel_disp<=rd_disp; ext_sel_epoch<=active_epoch[rd_bank];
            end else ext_sel_valid<=1'b0;

            if (tx_valid) begin
                for (j=0; j<NDISP; j=j+1) begin
                    if (tx_stats[j][N_OFF +: CNT_W]!=0) begin
                        wi=tx_bank*SRAM_DISP+j;
                        req_valid[wi]<=1'b1; req_bank[wi]<=tx_bank;
                        req_addr[wi]<=tx_tile; req_epoch[wi]<=tx_epoch;
                        req_delta[wi]<=tx_stats[j];
                        req_last[wi]<=pipe_valid && pipe_last && (j==MAX_D);
                    end
                end
            end

            // Consume one deferred new-tile contribution into the next beat's
            // same tile update; this avoids two writes to one disparity SRAM
            // on the beat crossing a tile boundary.
            if (tx_valid && carry_valid) carry_valid<=1'b0;
            carry_has_data=1'b0;
            if (pipe_valid) begin
                for (j=0; j<NDISP; j=j+1) if (pipe_stats1[j][N_OFF +: CNT_W]!=0) carry_has_data=1'b1;
                if (carry_has_data) begin
                    carry_valid<=1'b1; carry_bank<=pipe_bank; carry_epoch<=pipe_epoch;
                    carry_tile<=pipe_tile1;
                    for (j=0; j<NDISP; j=j+1) carry_stats[j]<=pipe_stats1[j];
                end
            end

            pipe_valid<=in_valid;
            if (in_valid) begin
                pipe_bank<=write_bank; pipe_epoch<=active_epoch[write_bank];
                pipe_tile0<=t0[COL_W-1:0]; pipe_tile1<=t1[COL_W-1:0];
                pipe_last<=((sensor_x==FRAME_W-INPUT_PIXELS)&&(tile_band_y==TILE_H-1));
                for (j=0; j<NDISP; j=j+1) begin
                    pipe_stats0[j]<=pack_stats(d0_l[j],d0_r[j],d0_ll[j],d0_rr[j],d0_lr[j],d0_n[j]);
                    pipe_stats1[j]<=pack_stats(d1_l[j],d1_r[j],d1_ll[j],d1_rr[j],d1_lr[j],d1_n[j]);
                end
                for (j=0; j<MAX_D; j=j+1) begin hist_l[j]<=hist_l_work[j]; hist_r[j]<=hist_r_work[j]; end
                if (sensor_x==FRAME_W-INPUT_PIXELS) begin
                    sensor_x<='0; tile_col_x<='0; tile_col_offset<='0;
                    if (tile_band_y==TILE_H-1) begin
                        tile_band_y<='0; write_bank<=~write_bank;
                        if (bank_ready[~write_bank] && !release_bank[~write_bank]) overrun<=1'b1;
                        active_epoch[~write_bank]<=~active_epoch[~write_bank];
                    end else tile_band_y<=tile_band_y+1'b1;
                end else begin
                    sensor_x<=sensor_x+INPUT_PIXELS;
                    if ((tile_col_offset+INPUT_PIXELS)>=TILE_W) begin
                        tile_col_offset<=tile_col_offset+INPUT_PIXELS-TILE_W;
                        tile_col_x<=tile_col_x+1'b1;
                    end else tile_col_offset<=tile_col_offset+INPUT_PIXELS;
                end
            end
        end
    end
endmodule

// One statically selected disparity; lanes from one beat are reduced into
// tile0/tile1 deltas before entering the SRAM update pipeline.
module dual_pd_zncc_disp4 #(
    parameter integer PIX_W=12, INPUT_PIXELS=4, MAX_D=8, DISP=0,
    parameter integer TILE_W=125, SUM_W=30, SQ_W=42, CNT_W=12
) (
    input logic [INPUT_PIXELS*PIX_W-1:0] in_l, in_r,
    input logic [MAX_D*PIX_W-1:0] hist_l, hist_r,
    input logic [$clog2(TILE_W)-1:0] x_offset,
    output logic [SUM_W-1:0] delta0_l, delta0_r,
    output logic [SQ_W-1:0] delta0_ll, delta0_rr, delta0_lr,
    output logic [CNT_W-1:0] delta0_n,
    output logic [SUM_W-1:0] delta1_l, delta1_r,
    output logic [SQ_W-1:0] delta1_ll, delta1_rr, delta1_lr,
    output logic [CNT_W-1:0] delta1_n
);
    integer p, pos, hist_index;
    logic cross_tile;
    logic [PIX_W-1:0] a, b;
    logic [2*PIX_W-1:0] aa, bb, ab;
    always_comb begin
        delta0_l='0; delta0_r='0; delta0_ll='0; delta0_rr='0;
        delta0_lr='0; delta0_n='0;
        delta1_l='0; delta1_r='0; delta1_ll='0; delta1_rr='0;
        delta1_lr='0; delta1_n='0;
        a='0; b='0; aa='0; bb='0; ab='0; pos=0; hist_index=0; cross_tile=0;
        for (p=0; p<INPUT_PIXELS; p=p+1) begin
            pos=x_offset+p;
            cross_tile=(pos>=TILE_W);
            if (cross_tile) pos=pos-TILE_W;
            if (DISP>0) begin
                if (p>=DISP) a=in_l[(p-DISP)*PIX_W +: PIX_W];
                else begin hist_index=DISP-p-1; a=hist_l[hist_index*PIX_W +: PIX_W]; end
                b=in_r[p*PIX_W +: PIX_W];
            end else if (DISP<0) begin
                a=in_l[p*PIX_W +: PIX_W];
                if (p>=-DISP) b=in_r[(p+DISP)*PIX_W +: PIX_W];
                else begin hist_index=-DISP-p-1; b=hist_r[hist_index*PIX_W +: PIX_W]; end
            end else begin
                a=in_l[p*PIX_W +: PIX_W]; b=in_r[p*PIX_W +: PIX_W];
            end
            if (pos>=((DISP<0)?-DISP:DISP)) begin
                aa=a*a; bb=b*b; ab=a*b;
                if (!cross_tile) begin
                    delta0_l=delta0_l+a; delta0_r=delta0_r+b;
                    delta0_ll=delta0_ll+aa; delta0_rr=delta0_rr+bb;
                    delta0_lr=delta0_lr+ab; delta0_n=delta0_n+1'b1;
                end else begin
                    delta1_l=delta1_l+a; delta1_r=delta1_r+b;
                    delta1_ll=delta1_ll+aa; delta1_rr=delta1_rr+bb;
                    delta1_lr=delta1_lr+ab; delta1_n=delta1_n+1'b1;
                end
            end
        end
    end
endmodule
