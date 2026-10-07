// Shared serial normalizer for pooled pseudo-luma statistics.
// REPORT work is deliberately spread over multiple cycles for 180 MHz closure.
module dual_pd_zncc_scorer_pooled #(
    parameter integer MAX_SHIFT = 16,
    parameter integer MIN_PAIRS = 32
) (
    input logic clk,rst_n,start,
    input logic [((MAX_SHIFT+1)*184)-1:0] stats_records,
    output logic busy,out_valid,
    output logic signed [9:0] phase_q4_4,
    output logic [7:0] score_u8,
    output logic [7:0] confidence_u8,
    output logic signed [15:0] peak_zncc_q15,
    output logic signed [15:0] second_zncc_q15,
    output logic low_texture
);
    localparam integer NDISP=MAX_SHIFT+1;
    localparam integer ACC_W=56;
    localparam integer DIV_W=ACC_W+16;
    localparam integer U8_DIV_W=24;
    typedef enum logic [3:0] {
        IDLE,PREP,SQRT,DIVIDE,SCAN_PEAK,SCAN_SECOND,
        INTERP_SETUP,INTERP_DIV,QUALITY_PREP,QUALITY_MUL1,
        QUALITY_MUL2,QUALITY_MUL3,QUALITY_U8_PREP,QUALITY_U8_DIV
    } state_t;
    state_t state;
    logic [NDISP*184-1:0] records_reg;
    logic signed [15:0] scores [0:NDISP-1];
    logic [11:0] pair_counts [0:NDISP-1];
    logic [4:0] score_idx,scan_idx,best_idx;
    logic [4:0] valid_count;
    logic signed [15:0] best_score,second_score;

    logic [2*ACC_W-1:0] den2_reg;
    logic signed [ACC_W:0] cov_reg;
    logic [ACC_W-1:0] sqrt_root,divisor_reg;
    logic [2*ACC_W+1:0] sqrt_rem;
    logic [$clog2(ACC_W+1)-1:0] sqrt_idx;
    logic [DIV_W-1:0] dividend_shift,quotient_reg;
    logic [ACC_W:0] div_rem;
    logic [$clog2(DIV_W+1)-1:0] div_idx;

    logic signed [5:0] interp_offset;
    logic [31:0] interp_dividend,interp_quotient;
    logic [32:0] interp_remainder;
    logic [31:0] interp_divisor;
    logic [5:0] interp_idx;
    logic interp_negative;
    logic [31:0] curvature_reg;

    logic [14:0] peak_factor,margin_factor,curv_factor,pair_factor;
    logic [14:0] quality_q15;
    logic [U8_DIV_W-1:0] u8_dividend,u8_quotient;
    logic [15:0] u8_remainder;
    logic [4:0] u8_idx;
    assign busy=(state!=IDLE);
    assign confidence_u8=score_u8;

    always_ff @(posedge clk or negedge rst_n) begin : scorer
        integer i,k;
        logic [183:0] rec;
        logic [11:0] n;
        logic [25:0] sl,sr;
        logic [39:0] sll,srr,slr;
        logic signed [63:0] cov_expr,vl_expr,vr_expr;
        logic signed [ACC_W-1:0] cov_tmp,vl_tmp,vr_tmp;
        logic [2*ACC_W+1:0] rem_tmp;
        logic [ACC_W+1:0] trial_tmp,rem_div_tmp;
        logic [ACC_W-1:0] root_next;
        logic [DIV_W-1:0] quotient_next,magnitude;
        logic [U8_DIV_W-1:0] u8_quotient_next;
        logic [15:0] u8_rem_next;
        logic signed [15:0] score_next,ym,yp;
        logic signed [31:0] peak,second,curvature,den,numerator;
        logic signed [31:0] signed_interp;
        logic [31:0] margin,peak_f,margin_f,curv_f,pair_f;
        logic [31:0] quality_next;
        logic [4:0] valid_count_next;
        logic neighbors_valid;
        if(!rst_n) begin
            state<=IDLE; records_reg<='0; score_idx<=0; scan_idx<=0;
            best_idx<=0; valid_count<=0; best_score<=-16'sd32768;
            second_score<=-16'sd32768; den2_reg<='0; cov_reg<='0;
            sqrt_root<='0; divisor_reg<='0; sqrt_rem<='0; sqrt_idx<='0;
            dividend_shift<='0; quotient_reg<='0; div_rem<='0; div_idx<='0;
            interp_offset<='0; interp_dividend<='0; interp_quotient<='0;
            interp_remainder<='0; interp_divisor<='0; interp_idx<='0;
            interp_negative<=0; curvature_reg<=0;
            peak_factor<=0; margin_factor<=0; curv_factor<=0; pair_factor<=0;
            quality_q15<=0; u8_dividend<=0; u8_quotient<=0;
            u8_remainder<=0; u8_idx<=0;
            phase_q4_4<=0; score_u8<=0; out_valid<=0;
            peak_zncc_q15<=-16'sd32768; second_zncc_q15<=-16'sd32768;
            low_texture<=1;
            for(i=0;i<NDISP;i=i+1) begin
                scores[i]<=-16'sd32768; pair_counts[i]<=0;
            end
        end else begin
            out_valid<=0;
            case(state)
                IDLE: if(start) begin
                    records_reg<=stats_records;
                    score_idx<=0;
                    for(i=0;i<NDISP;i=i+1) begin
                        scores[i]<=-16'sd32768; pair_counts[i]<=0;
                    end
                    state<=PREP;
                end
                PREP: begin
                    rec=records_reg[score_idx*184 +: 184];
                    n=rec[172 +: 12];
                    sl=rec[0 +: 26]; sr=rec[26 +: 26];
                    sll=rec[52 +: 40]; srr=rec[92 +: 40]; slr=rec[132 +: 40];
                    cov_expr=$signed(64'(n)*64'(slr))-$signed(64'(sl)*64'(sr));
                    vl_expr=$signed(64'(n)*64'(sll))-$signed(64'(sl)*64'(sl));
                    vr_expr=$signed(64'(n)*64'(srr))-$signed(64'(sr)*64'(sr));
                    cov_tmp=cov_expr[ACC_W-1:0];
                    vl_tmp=vl_expr[ACC_W-1:0];
                    vr_tmp=vr_expr[ACC_W-1:0];
                    pair_counts[score_idx]<=n;
                    if(n<MIN_PAIRS || vl_tmp<=0 || vr_tmp<=0) begin
                        scores[score_idx]<=-16'sd32768;
                        if(score_idx==NDISP-1) begin
                            scan_idx<=0; best_score<=-16'sd32768;
                            best_idx<=0; valid_count<=0; state<=SCAN_PEAK;
                        end else begin score_idx<=score_idx+1'b1; state<=PREP; end
                    end else begin
                        cov_reg<={cov_tmp[ACC_W-1],cov_tmp};
                        den2_reg<=$unsigned(vl_tmp)*$unsigned(vr_tmp);
                        sqrt_root<=0; sqrt_rem<=0; sqrt_idx<=ACC_W-1;
                        state<=SQRT;
                    end
                end
                SQRT: begin
                    rem_tmp=(sqrt_rem<<2)|((den2_reg>>(sqrt_idx*2))&2'b11);
                    trial_tmp=(sqrt_root<<2)|1'b1;
                    if(rem_tmp>=trial_tmp) begin
                        rem_tmp=rem_tmp-trial_tmp;
                        root_next=(sqrt_root<<1)|1'b1;
                    end else root_next=sqrt_root<<1;
                    sqrt_root<=root_next; sqrt_rem<=rem_tmp;
                    if(sqrt_idx==0) begin
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
                    if(rem_div_tmp>={1'b0,divisor_reg}) begin
                        rem_div_tmp=rem_div_tmp-{1'b0,divisor_reg};
                        quotient_next[0]=1'b1;
                    end
                    div_rem<=rem_div_tmp; quotient_reg<=quotient_next;
                    dividend_shift<=dividend_shift<<1;
                    if(div_idx==0) begin
                        if(cov_reg[ACC_W]) begin
                            if(quotient_next>32767) score_next=-16'sd32767;
                            else score_next=-$signed(quotient_next[15:0]);
                        end else begin
                            if(quotient_next>32767) score_next=16'sd32767;
                            else score_next=$signed(quotient_next[15:0]);
                        end
                        scores[score_idx]<=score_next;
                        if(score_idx==NDISP-1) begin
                            scan_idx<=0; best_score<=-16'sd32768;
                            best_idx<=0; valid_count<=0; state<=SCAN_PEAK;
                        end else begin score_idx<=score_idx+1'b1; state<=PREP; end
                    end else div_idx<=div_idx-1'b1;
                end
                SCAN_PEAK: begin
                    valid_count_next=valid_count;
                    if(scores[scan_idx]!=-16'sd32768) valid_count_next=valid_count+1'b1;
                    valid_count<=valid_count_next;
                    if(scores[scan_idx]>best_score) begin
                        best_score<=scores[scan_idx]; best_idx<=scan_idx;
                    end
                    if(scan_idx==NDISP-1) begin
                        scan_idx<=0; second_score<=-16'sd32768; state<=SCAN_SECOND;
                    end else scan_idx<=scan_idx+1'b1;
                end
                SCAN_SECOND: begin
                    second=second_score;
                    if((scan_idx+1<best_idx || scan_idx>best_idx+1) &&
                       scores[scan_idx]>second) second=scores[scan_idx];
                    second_score<=16'(second);
                    if(scan_idx==NDISP-1) begin
                        peak_zncc_q15<=best_score;
                        if(second==-16'sd32768) second_zncc_q15<=best_score;
                        else second_zncc_q15<=16'(second);
                        if(valid_count<3) begin
                            phase_q4_4<=0; score_u8<=0; low_texture<=1;
                            out_valid<=1; state<=IDLE;
                        end else begin
                            low_texture<=0; state<=INTERP_SETUP;
                        end
                    end else scan_idx<=scan_idx+1'b1;
                end
                INTERP_SETUP: begin
                    ym=-16'sd32768; yp=-16'sd32768;
                    if(best_idx>0) ym=scores[best_idx-1'b1];
                    if(best_idx<NDISP-1) yp=scores[best_idx+1'b1];
                    neighbors_valid=(best_idx>0 && best_idx<NDISP-1 &&
                        ym!=-16'sd32768 && yp!=-16'sd32768);
                    curvature=0; numerator=0; den=0;
                    if(neighbors_valid) begin
                        curvature=2*$signed(best_score)-$signed(ym)-$signed(yp);
                        if(curvature>0) begin
                            den=$signed(ym)-2*$signed(best_score)+$signed(yp);
                            numerator=16*($signed(ym)-$signed(yp));
                        end else curvature=0;
                    end
                    curvature_reg<=32'(curvature);
                    if(curvature>0 && den!=0) begin
                        interp_negative=(numerator<0)^(den<0);
                        interp_dividend<=32'(numerator<0 ? -numerator : numerator);
                        interp_divisor<=32'(den<0 ? -den : den);
                        interp_quotient<=0; interp_remainder<=0; interp_idx<=31;
                        interp_negative<=interp_negative;
                        state<=INTERP_DIV;
                    end else begin
                        interp_offset<=0;
                        state<=QUALITY_PREP;
                    end
                end
                INTERP_DIV: begin
                    rem_tmp=0;
                    rem_tmp[32:0]=(interp_remainder<<1)|interp_dividend[31];
                    quotient_next=0;
                    quotient_next[31:0]=interp_quotient<<1;
                    if(rem_tmp[32:0]>={1'b0,interp_divisor}) begin
                        rem_tmp[32:0]=rem_tmp[32:0]-{1'b0,interp_divisor};
                        quotient_next[0]=1'b1;
                    end
                    interp_remainder<=rem_tmp[32:0];
                    interp_quotient<=quotient_next[31:0];
                    interp_dividend<=interp_dividend<<1;
                    if(interp_idx==0) begin
                        signed_interp=interp_negative ? -$signed(quotient_next[31:0]) : $signed(quotient_next[31:0]);
                        if(signed_interp>16) interp_offset<=6'sd16;
                        else if(signed_interp< -16) interp_offset<=-6'sd16;
                        else interp_offset<=6'(signed_interp);
                        state<=QUALITY_PREP;
                    end else interp_idx<=interp_idx-1'b1;
                end
                QUALITY_PREP: begin
                    peak=best_score;
                    second=(second_score==-16'sd32768)?best_score:second_score;
                    margin=peak-second;
                    if(margin<0) margin=0;
                    peak_f=(peak>0)?32'(peak):0;
                    margin_f=(margin*4>32767)?32767:32'(margin*4);
                    curv_f=(curvature_reg*20/3>32767)?32767:(32'(curvature_reg)*20/3);
                    pair_f=(32'(pair_counts[best_idx])*32767/128>32767)?32767:
                        (32'(pair_counts[best_idx])*32767/128);
                    peak_factor<=15'(peak_f); margin_factor<=15'(margin_f);
                    curv_factor<=15'(curv_f); pair_factor<=15'(pair_f);
                    phase_q4_4<=10'(($signed({1'b0,best_idx})-MAX_SHIFT/2)*32+$signed(interp_offset));
                    state<=QUALITY_MUL1;
                end
                QUALITY_MUL1: begin
                    quality_next=(32'(peak_factor)*32'(margin_factor))>>15;
                    quality_q15<=15'(quality_next);
                    state<=QUALITY_MUL2;
                end
                QUALITY_MUL2: begin
                    quality_next=(32'(quality_q15)*32'(curv_factor))>>15;
                    quality_q15<=15'(quality_next);
                    state<=QUALITY_MUL3;
                end
                QUALITY_MUL3: begin
                    quality_next=(32'(quality_q15)*32'(pair_factor))>>15;
                    if(best_idx==0 || best_idx==NDISP-1) quality_next=0;
                    quality_q15<=15'(quality_next);
                    state<=QUALITY_U8_PREP;
                end
                QUALITY_U8_PREP: begin
                    // Rounded scale from unsigned Q0.15 to [0,255], using
                    // an iterative constant divider rather than a long path.
                    u8_dividend<=U8_DIV_W'(({9'b0,quality_q15}<<8)-
                                           {9'b0,quality_q15}+24'd16383);
                    u8_quotient<=0; u8_remainder<=0; u8_idx<=U8_DIV_W-1;
                    state<=QUALITY_U8_DIV;
                end
                QUALITY_U8_DIV: begin
                    u8_rem_next={u8_remainder[14:0],u8_dividend[U8_DIV_W-1]};
                    u8_quotient_next=u8_quotient<<1;
                    if(u8_rem_next>=16'd32767) begin
                        u8_rem_next=u8_rem_next-16'd32767;
                        u8_quotient_next[0]=1'b1;
                    end
                    u8_remainder<=u8_rem_next;
                    u8_quotient<=u8_quotient_next;
                    u8_dividend<=u8_dividend<<1;
                    if(u8_idx==0) begin
                        score_u8<=u8_quotient_next[7:0];
                        out_valid<=1; state<=IDLE;
                    end else u8_idx<=u8_idx-1'b1;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
