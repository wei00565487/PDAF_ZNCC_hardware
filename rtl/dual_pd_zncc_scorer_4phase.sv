// Sequential, shared normalizer for seventeen 4-phase ZNCC candidates.
// Input records are ordered -16,-14,...,+16 sensor pixels. Each 168-bit
// Bayer phase record is {count[11:0],sumLR[35:0],sumRR[35:0],sumLL[35:0],
// sumR[23:0],sumL[23:0]}, with phase index 2*y_parity+x_parity.
// score_u8 is the uncalibrated repository quality score, not a probability.
module dual_pd_zncc_scorer_4phase #(
    parameter integer MAX_SHIFT=16,
    parameter integer FRAC=4,
    parameter integer MIN_PAIRS=32
) (
    input logic clk,rst_n,start,
    input logic [((MAX_SHIFT+1)*672)-1:0] stats_records,
    output logic busy,out_valid,
    output logic signed [9:0] phase_q4_4,
    output logic [7:0] score_u8,
    output logic [7:0] confidence_u8,
    output logic signed [15:0] peak_zncc_q15,
    output logic signed [15:0] second_zncc_q15,
    output logic low_texture
);
    localparam integer NDISP=MAX_SHIFT+1;
    localparam integer Q=12;
    localparam integer ACC_W=56;
    localparam integer DIV_W=ACC_W+16;
    typedef enum logic [2:0] {IDLE,PREP,SQRT,DIVIDE,REPORT} state_t;
    state_t state;
    logic [NDISP*672-1:0] records_reg;
    logic signed [15:0] scores [0:NDISP-1];
    logic [13:0] pair_counts [0:NDISP-1];
    logic [4:0] score_idx;
    logic [2*ACC_W-1:0] den2_reg;
    logic signed [ACC_W:0] cov_reg;
    logic [ACC_W-1:0] sqrt_root,divisor_reg;
    logic [2*ACC_W+1:0] sqrt_rem;
    logic [$clog2(ACC_W+1)-1:0] sqrt_idx;
    logic [DIV_W-1:0] dividend_shift,quotient_reg;
    logic [ACC_W:0] div_rem;
    logic [$clog2(DIV_W+1)-1:0] div_idx;
    assign busy=(state!=IDLE);
    assign confidence_u8=score_u8;

    always_ff @(posedge clk or negedge rst_n) begin : engine
        integer i,ph,off,k,best,valid_candidates;
        logic [671:0] rec;
        logic [11:0] n;
        logic [23:0] sl,sr;
        logic [35:0] sll,srr,slr;
        logic signed [63:0] cov_num,cov_sum;
        logic [63:0] vl_num,vr_num,vl_sum,vr_sum;
        logic [13:0] pairs;
        logic [2*ACC_W+1:0] rem_tmp;
        logic [ACC_W+1:0] trial_tmp,rem_div_tmp;
        logic [ACC_W-1:0] root_next;
        logic [DIV_W-1:0] quotient_next,magnitude;
        logic signed [15:0] score_next,peak,second,ym,yp;
        logic signed [31:0] curvature,den,interp_num,interp_q4,margin;
        logic [31:0] peak_factor,margin_factor,curv_factor,pair_factor,quality;
        logic neighbors_valid;
        if (!rst_n) begin
            state<=IDLE; records_reg<='0; score_idx<=0;
            den2_reg<='0; cov_reg<='0; sqrt_root<='0; sqrt_rem<='0;
            sqrt_idx<=0; divisor_reg<=0; dividend_shift<=0;
            quotient_reg<=0; div_rem<=0; div_idx<=0;
            phase_q4_4<=0; score_u8<=0; out_valid<=0;
            peak_zncc_q15<=-16'sd32768;
            second_zncc_q15<=-16'sd32768;
            low_texture<=1;
            for (i=0;i<NDISP;i=i+1) begin
                scores[i]<=-16'sd32768; pair_counts[i]<=0;
            end
        end else begin
            out_valid<=0;
            case (state)
                IDLE: if (start) begin
                    records_reg<=stats_records;
                    for (i=0;i<NDISP;i=i+1) begin
                        scores[i]<=-16'sd32768; pair_counts[i]<=0;
                    end
                    score_idx<=0; state<=PREP;
                end
                PREP: begin
                    rec=records_reg[score_idx*672 +: 672];
                    cov_sum=0; vl_sum=0; vr_sum=0; pairs=0;
                    n=0; sl=0; sr=0; sll=0; srr=0; slr=0;
                    cov_num=0; vl_num=0; vr_num=0;
                    for (ph=0;ph<4;ph=ph+1) begin
                        off=ph*168;
                        n=rec[off+156 +: 12];
                        if (n>=3) begin
                            sl=rec[off+0 +: 24];
                            sr=rec[off+24 +: 24];
                            sll=rec[off+48 +: 36];
                            srr=rec[off+84 +: 36];
                            slr=rec[off+120 +: 36];
                            cov_num=$signed(64'(n)*64'(slr))-$signed(64'(sl)*64'(sr));
                            vl_num=64'(n)*64'(sll)-64'(sl)*64'(sl);
                            vr_num=64'(n)*64'(srr)-64'(sr)*64'(sr);
                            cov_sum=cov_sum+(cov_num*(64'sd1<<<Q))/$signed({1'b0,n});
                            vl_sum=vl_sum+((vl_num<<Q)/n);
                            vr_sum=vr_sum+((vr_num<<Q)/n);
                            pairs=pairs+n;
                        end
                    end
                    pair_counts[score_idx]<=pairs;
                    if (pairs<MIN_PAIRS || vl_sum==0 || vr_sum==0) begin
                        scores[score_idx]<=-16'sd32768;
                        if (score_idx==NDISP-1) state<=REPORT;
                        else score_idx<=score_idx+1'b1;
                    end else begin
                        cov_reg<=cov_sum[ACC_W:0];
                        den2_reg<=vl_sum[ACC_W-1:0]*vr_sum[ACC_W-1:0];
                        sqrt_root<=0; sqrt_rem<=0; sqrt_idx<=ACC_W-1;
                        state<=SQRT;
                    end
                end
                SQRT: begin
                    rem_tmp=(sqrt_rem<<2)|((den2_reg>>(sqrt_idx*2))&2'b11);
                    trial_tmp=(sqrt_root<<2)|1'b1;
                    if (rem_tmp>=trial_tmp) begin
                        rem_tmp=rem_tmp-trial_tmp;
                        root_next=(sqrt_root<<1)|1'b1;
                    end else root_next=sqrt_root<<1;
                    sqrt_root<=root_next; sqrt_rem<=rem_tmp;
                    if (sqrt_idx==0) begin
                        divisor_reg<=root_next;
                        magnitude=cov_reg[ACC_W] ? -cov_reg : cov_reg;
                        dividend_shift<=magnitude<<15;
                        quotient_reg<=0; div_rem<=0; div_idx<=DIV_W-1;
                        state<=DIVIDE;
                    end else sqrt_idx<=sqrt_idx-1'b1;
                end
                DIVIDE: begin
                    rem_div_tmp=(div_rem<<1)|dividend_shift[DIV_W-1];
                    quotient_next=quotient_reg<<1;
                    if (rem_div_tmp>={1'b0,divisor_reg}) begin
                        rem_div_tmp=rem_div_tmp-{1'b0,divisor_reg};
                        quotient_next[0]=1;
                    end
                    div_rem<=rem_div_tmp; quotient_reg<=quotient_next;
                    dividend_shift<=dividend_shift<<1;
                    if (div_idx==0) begin
                        if (cov_reg[ACC_W]) begin
                            if (quotient_next>32767) score_next=-16'sd32767;
                            else score_next=-$signed(quotient_next[15:0]);
                        end else begin
                            if (quotient_next>32767) score_next=16'sd32767;
                            else score_next=$signed(quotient_next[15:0]);
                        end
                        scores[score_idx]<=score_next;
                        if (score_idx==NDISP-1) state<=REPORT;
                        else begin score_idx<=score_idx+1'b1; state<=PREP; end
                    end else div_idx<=div_idx-1'b1;
                end
                REPORT: begin
                    peak=-16'sd32768; second=-16'sd32768;
                    best=0; valid_candidates=0;
                    for (k=0;k<NDISP;k=k+1) begin
                        if (scores[k]!=-16'sd32768) valid_candidates=valid_candidates+1;
                        if (scores[k]>peak) begin peak=scores[k]; best=k; end
                    end
                    for (k=0;k<NDISP;k=k+1)
                        if ((k<best-1 || k>best+1) && scores[k]>second)
                            second=scores[k];
                    if (second==-16'sd32768) second=peak;
                    peak_zncc_q15<=peak;
                    second_zncc_q15<=second;
                    if (valid_candidates<3) begin
                        phase_q4_4<=0; score_u8<=0; low_texture<=1;
                    end else begin
                        low_texture<=0;
                        ym=-16'sd32768; yp=-16'sd32768;
                        if (best>0) ym=scores[best-1];
                        if (best<NDISP-1) yp=scores[best+1];
                        neighbors_valid=(best>0 && best<NDISP-1 &&
                            ym!=-16'sd32768 && yp!=-16'sd32768);
                        curvature=0; interp_q4=0;
                        if (neighbors_valid) begin
                            curvature=2*$signed(peak)-$signed(ym)-$signed(yp);
                            if (curvature>0) begin
                                den=$signed(ym)-2*$signed(peak)+$signed(yp);
                                interp_num=16*($signed(ym)-$signed(yp));
                                interp_q4=interp_num/den;
                                if (interp_q4>16) interp_q4=16;
                                if (interp_q4< -16) interp_q4= -16;
                            end else curvature=0;
                        end
                        phase_q4_4<=10'((best-MAX_SHIFT/2)*32+interp_q4);
                        margin=$signed(peak)-$signed(second);
                        if (margin<0) margin=0;
                        peak_factor=(peak>0)?32'(peak):0;
                        margin_factor=(margin*4>32767)?32767:32'(margin*4);
                        curv_factor=(curvature*20/3>32767)?32767:32'(curvature*20/3);
                        pair_factor=(32'(pair_counts[best])*32767/128>32767)?
                            32767:32'(pair_counts[best])*32767/128;
                        quality=peak_factor;
                        quality=(quality*margin_factor)>>15;
                        quality=(quality*curv_factor)>>15;
                        quality=(quality*pair_factor)>>15;
                        if (best==0 || best==NDISP-1) quality=0;
                        score_u8<=8'((quality*255+16383)/32767);
                    end
                    out_valid<=1; state<=IDLE;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
