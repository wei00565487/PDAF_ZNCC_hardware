// Shared ZNCC normalization/peak/confidence engine.
// Loads one tile's 17 accumulated candidate records, then emits one Q4.4 result.
module dual_pd_zncc_scorer #(
    parameter integer PIX_W=12,
    parameter integer TILE_W=125,
    parameter integer TILE_H=125,
    parameter integer MAX_D=8,
    parameter integer FRAC=4,
    parameter integer SUM_W=PIX_W+$clog2(TILE_W*TILE_H)+1,
    parameter integer SQ_W=2*PIX_W+$clog2(TILE_W*TILE_H)+1,
    parameter integer CNT_W=$clog2(TILE_W*TILE_H+1)
) (
    input logic clk, rst_n,
    input logic start,
    input logic [((2*MAX_D+1)*SUM_W)-1:0] stats_sum_l,
    input logic [((2*MAX_D+1)*SUM_W)-1:0] stats_sum_r,
    input logic [((2*MAX_D+1)*SQ_W)-1:0] stats_sum_ll,
    input logic [((2*MAX_D+1)*SQ_W)-1:0] stats_sum_rr,
    input logic [((2*MAX_D+1)*SQ_W)-1:0] stats_sum_lr,
    input logic [((2*MAX_D+1)*CNT_W)-1:0] stats_count,
    output logic busy,
    output logic out_valid,
    output logic signed [8:0] phase_q4_4,
    output logic [7:0] confidence_u8,
    output logic low_texture
);
    localparam integer NDISP=2*MAX_D+1;
    localparam integer VAR_W=2*SUM_W;
    localparam integer SCORE_W=VAR_W+16;
    typedef enum logic [2:0] {IDLE, PREP, SQRT, DIVIDE, REPORT} state_t;
    state_t state;
    logic [SUM_W-1:0] sum_l[0:NDISP-1], sum_r[0:NDISP-1];
    logic [SQ_W-1:0] sum_ll[0:NDISP-1], sum_rr[0:NDISP-1], sum_lr[0:NDISP-1];
    logic [CNT_W-1:0] count[0:NDISP-1];
    logic signed [15:0] scores[0:NDISP-1];
    logic [$clog2(NDISP)-1:0] score_idx;
    logic [2*VAR_W-1:0] den2_reg;
    logic signed [VAR_W:0] cov_reg;
    logic [VAR_W-1:0] sqrt_root, divisor_reg;
    logic [2*VAR_W+1:0] sqrt_rem;
    logic [$clog2(VAR_W+1)-1:0] sqrt_idx;
    logic [SCORE_W-1:0] dividend_shift, quotient_reg;
    logic [VAR_W:0] div_rem;
    logic [$clog2(SCORE_W+1)-1:0] div_idx;
    integer i;
    assign busy=(state!=IDLE);

    always_ff @(posedge clk or negedge rst_n) begin : score_engine
        logic [SUM_W-1:0] nx, ax, bx;
        logic [SQ_W-1:0] aax, bbx, abx;
        logic [CNT_W+SQ_W-1:0] n_sll_tmp, n_srr_tmp, n_slr_tmp;
        logic [2*SUM_W-1:0] sl_sq_tmp, sr_sq_tmp, sl_sr_tmp;
        logic [VAR_W-1:0] vl_tmp, vr_tmp;
        logic signed [VAR_W:0] cv_tmp;
        logic [2*VAR_W-1:0] den2_tmp;
        logic [2*VAR_W+1:0] rem_tmp;
        logic [VAR_W+1:0] trial_tmp;
        logic [VAR_W-1:0] root_next_tmp;
        logic [VAR_W+1:0] rem_div_tmp;
        logic [SCORE_W-1:0] quotient_tmp, magnitude_tmp;
        logic signed [15:0] score_tmp, peak_tmp, second_tmp;
        logic [4:0] peak_index_tmp;
        logic [15:0] confidence_tmp;
        logic [23:0] conf_num_small;
        logic [15:0] conf_den_small;
        logic signed [19:0] interp_num_small;
        logic signed [17:0] interp_den_small;
        logic signed [31:0] interp_tmp;
        integer k, disp;
        if (!rst_n) begin
            state<=IDLE; score_idx<='0; den2_reg<='0; cov_reg<='0;
            sqrt_root<='0; sqrt_rem<='0; sqrt_idx<='0; divisor_reg<='0;
            dividend_shift<='0; quotient_reg<='0; div_rem<='0; div_idx<='0;
            out_valid<=1'b0; phase_q4_4<='0; confidence_u8<='0; low_texture<=1'b1;
            for (i=0;i<NDISP;i=i+1) begin
                sum_l[i]<='0; sum_r[i]<='0; sum_ll[i]<='0; sum_rr[i]<='0; sum_lr[i]<='0;
                count[i]<='0; scores[i]<=-16'sd32768;
            end
        end else begin
            out_valid<=1'b0;
            case (state)
                IDLE: if (start) begin
                    for (i=0;i<NDISP;i=i+1) begin
                        sum_l[i]<=stats_sum_l[i*SUM_W +: SUM_W];
                        sum_r[i]<=stats_sum_r[i*SUM_W +: SUM_W];
                        sum_ll[i]<=stats_sum_ll[i*SQ_W +: SQ_W];
                        sum_rr[i]<=stats_sum_rr[i*SQ_W +: SQ_W];
                        sum_lr[i]<=stats_sum_lr[i*SQ_W +: SQ_W];
                        count[i]<=stats_count[i*CNT_W +: CNT_W];
                        scores[i]<=-16'sd32768;
                    end
                    score_idx<='0; state<=PREP;
                end
                PREP: begin
                    nx=count[score_idx]; ax=sum_l[score_idx]; bx=sum_r[score_idx];
                    aax=sum_ll[score_idx]; bbx=sum_rr[score_idx]; abx=sum_lr[score_idx];
                    n_sll_tmp=nx*aax; sl_sq_tmp=ax*ax;
                    n_srr_tmp=nx*bbx; sr_sq_tmp=bx*bx;
                    n_slr_tmp=nx*abx; sl_sr_tmp=ax*bx;
                    vl_tmp=n_sll_tmp-sl_sq_tmp; vr_tmp=n_srr_tmp-sr_sq_tmp;
                    cv_tmp=$signed({1'b0,n_slr_tmp})-$signed({1'b0,sl_sr_tmp});
                    den2_tmp=vl_tmp*vr_tmp;
                    if ((vl_tmp==0)||(vr_tmp==0)) begin
                        scores[score_idx]<=-16'sd32768;
                        if (score_idx==NDISP-1) state<=REPORT;
                        else begin score_idx<=score_idx+1'b1; state<=PREP; end
                    end else begin
                        den2_reg<=den2_tmp; cov_reg<=cv_tmp;
                        sqrt_root<='0; sqrt_rem<='0; sqrt_idx<=VAR_W-1; state<=SQRT;
                    end
                end
                SQRT: begin
                    rem_tmp=(sqrt_rem<<2)|((den2_reg>>(sqrt_idx*2))&{{(2*VAR_W){1'b0}},2'b11});
                    trial_tmp=(sqrt_root<<2)|{{VAR_W{1'b0}},1'b1};
                    if (rem_tmp>=trial_tmp) begin
                        rem_tmp=rem_tmp-trial_tmp; root_next_tmp=(sqrt_root<<1)|1'b1;
                    end else root_next_tmp=sqrt_root<<1;
                    sqrt_root<=root_next_tmp; sqrt_rem<=rem_tmp;
                    if (sqrt_idx==0) begin
                        divisor_reg<=root_next_tmp;
                        magnitude_tmp=cov_reg[VAR_W] ? -cov_reg : cov_reg;
                        dividend_shift<=magnitude_tmp<<15; quotient_reg<='0;
                        div_rem<='0; div_idx<=SCORE_W-1; state<=DIVIDE;
                    end else sqrt_idx<=sqrt_idx-1'b1;
                end
                DIVIDE: begin
                    rem_div_tmp=(div_rem<<1)|dividend_shift[SCORE_W-1];
                    quotient_tmp=quotient_reg<<1;
                    if (rem_div_tmp>={1'b0,divisor_reg}) begin
                        rem_div_tmp=rem_div_tmp-{1'b0,divisor_reg}; quotient_tmp[0]=1'b1;
                    end
                    div_rem<=rem_div_tmp; quotient_reg<=quotient_tmp;
                    dividend_shift<=dividend_shift<<1;
                    if (div_idx==0) begin
                        if (cov_reg[VAR_W]) begin
                            if (quotient_tmp>32767) score_tmp=-16'sd32767;
                            else score_tmp=-$signed(quotient_tmp[15:0]);
                        end else begin
                            if (quotient_tmp>32767) score_tmp=16'sd32767;
                            else score_tmp=$signed(quotient_tmp[15:0]);
                        end
                        scores[score_idx]<=score_tmp;
                        if (score_idx==NDISP-1) state<=REPORT;
                        else begin score_idx<=score_idx+1'b1; state<=PREP; end
                    end else div_idx<=div_idx-1'b1;
                end
                REPORT: begin
                    peak_tmp=-16'sd32768; peak_index_tmp='0; second_tmp=-16'sd32768;
                    for (k=0;k<NDISP;k=k+1)
                        if (scores[k]>peak_tmp) begin peak_tmp=scores[k]; peak_index_tmp=k[4:0]; end
                    for (k=0;k<NDISP;k=k+1)
                        if ((k+1<peak_index_tmp || k>peak_index_tmp+1) && scores[k]>second_tmp)
                            second_tmp=scores[k];
                    conf_num_small=(peak_tmp-second_tmp)*255;
                    conf_den_small=32767-second_tmp;
                    confidence_tmp=(conf_den_small!=0)?conf_num_small/conf_den_small:0;
                    interp_num_small=0; interp_den_small=0;
                    if ((peak_index_tmp>0)&&(peak_index_tmp<NDISP-1)) begin
                        interp_num_small=8*(scores[peak_index_tmp-1]-scores[peak_index_tmp+1]);
                        interp_den_small=scores[peak_index_tmp-1]-2*scores[peak_index_tmp]+scores[peak_index_tmp+1];
                    end
                    interp_tmp=(interp_den_small<0)?interp_num_small/interp_den_small:0;
                    if (interp_tmp>8) interp_tmp=8;
                    if (interp_tmp< -8) interp_tmp= -8;
                    if (peak_tmp==-16'sd32768) begin
                        phase_q4_4<='0; confidence_u8<='0; low_texture<=1'b1;
                    end else begin
                        disp=peak_index_tmp; disp=disp-MAX_D;
                        phase_q4_4<=disp*(1<<FRAC)+interp_tmp;
                        confidence_u8<=confidence_tmp[7:0]; low_texture<=1'b0;
                    end
                    out_valid<=1'b1; state<=IDLE;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
