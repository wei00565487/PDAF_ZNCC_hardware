// One-tile streaming ZNCC engine.
// The upstream tile scheduler must provide one tile at a time and must not
// mix samples from adjacent tiles. One accepted beat is one paired L/R pixel.
module dual_pd_zncc_tile #(
    parameter integer PIX_W = 12,
    parameter integer TILE_W = 125,
    parameter integer TILE_H = 125,
    parameter integer MAX_D = 8,
    parameter integer FRAC = 4
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 in_valid,
    input  logic [PIX_W-1:0]     in_l,
    input  logic [PIX_W-1:0]     in_r,
    output logic                 in_ready,
    output logic                 out_valid,
    output logic signed [8:0]    phase_q4_4,
    output logic [7:0]           confidence_u8,
    output logic                 low_texture
);
    localparam integer NDISP = 2*MAX_D + 1;
    localparam integer SUM_W = PIX_W + $clog2(TILE_W*TILE_H) + 1;
    localparam integer SQ_W  = 2*PIX_W + $clog2(TILE_W*TILE_H) + 1;
    localparam integer VAR_W = 2*SUM_W;
    localparam integer SCORE_W = VAR_W + 16;
    localparam integer CNT_W = $clog2(TILE_W*TILE_H + 1);

    typedef enum logic [2:0] {CAPTURE, PREP, SQRT, DIVIDE, REPORT} state_t;
    state_t state;
    logic [$clog2(TILE_W)-1:0] x;
    logic [$clog2(TILE_H)-1:0] y;
    logic [PIX_W-1:0] l_hist [0:MAX_D-1];
    logic [PIX_W-1:0] r_hist [0:MAX_D-1];

    logic [SUM_W-1:0] sum_l [0:NDISP-1];
    logic [SUM_W-1:0] sum_r [0:NDISP-1];
    logic [SQ_W-1:0]  sum_ll[0:NDISP-1];
    logic [SQ_W-1:0]  sum_rr[0:NDISP-1];
    logic [SQ_W-1:0]  sum_lr[0:NDISP-1];
    logic [CNT_W-1:0] count [0:NDISP-1];
    logic signed [15:0] scores [0:NDISP-1]; // signed Q1.15; -32768 = invalid
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

    assign in_ready = (state == CAPTURE);

    // The statistics are unsigned exact integer sums. Normalization uses
    // N*sum(x^2)-sum(x)^2 to avoid mean subtraction at every pixel.
    always_ff @(posedge clk or negedge rst_n) begin : engine
        logic [PIX_W-1:0] a, b;
        logic [2*PIX_W-1:0] aa, bb, ab;
        logic [SUM_W-1:0] nx, ax, bx;
        logic [SQ_W-1:0] aax, bbx, abx;
        logic [VAR_W-1:0] vl_tmp, vr_tmp;
        logic [2*VAR_W-1:0] den2_tmp;
        logic [CNT_W+SQ_W-1:0] n_sll_tmp, n_srr_tmp, n_slr_tmp;
        logic [2*SUM_W-1:0] sl_sq_tmp, sr_sq_tmp, sl_sr_tmp;
        logic signed [VAR_W:0] cv_tmp;
        logic [2*VAR_W+1:0] rem_tmp;
        logic [VAR_W+1:0] trial_tmp;
        logic [VAR_W-1:0] root_next_tmp;
        logic [VAR_W:0] rem_div_tmp;
        logic [SCORE_W-1:0] quotient_tmp;
        logic [SCORE_W-1:0] magnitude_tmp;
        logic [15:0] confidence_tmp;
        logic signed [15:0] score_tmp;
        logic signed [15:0] peak_tmp, second_tmp;
        logic [4:0] peak_index_tmp;
        logic signed [31:0] interp_num_tmp, interp_den_tmp, interp_tmp;
        logic signed [31:0] conf_num_tmp, conf_den_tmp, conf_tmp;
        logic signed [15:0] ym_tmp, y0_tmp, yp_tmp;
        logic signed [19:0] interp_num_small;
        logic signed [17:0] interp_den_small;
        logic [23:0] conf_num_small;
        logic [15:0] conf_den_small;
        integer k, disp;
        if (!rst_n) begin
            state <= CAPTURE;
            x <= '0; y <= '0;
            score_idx <= '0;
            den2_reg <= '0; cov_reg <= '0;
            sqrt_root <= '0; sqrt_rem <= '0; sqrt_idx <= '0;
            divisor_reg <= '0; dividend_shift <= '0; quotient_reg <= '0;
            div_rem <= '0; div_idx <= '0;
            out_valid <= 1'b0;
            phase_q4_4 <= '0;
            confidence_u8 <= '0;
            low_texture <= 1'b1;
            for (i = 0; i < MAX_D; i = i+1) begin
                l_hist[i] <= '0;
                r_hist[i] <= '0;
            end
            for (i = 0; i < NDISP; i = i+1) begin
                sum_l[i] <= '0; sum_r[i] <= '0;
                sum_ll[i] <= '0; sum_rr[i] <= '0; sum_lr[i] <= '0;
                count[i] <= '0; scores[i] <= -16'sd32768;
            end
        end else begin
            out_valid <= 1'b0;
            case (state)
                CAPTURE: if (in_valid) begin
                    for (k = 0; k < MAX_D; k = k+1) begin
                        if (k == 0) begin
                            l_hist[k] <= in_l;
                            r_hist[k] <= in_r;
                        end else begin
                            l_hist[k] <= l_hist[k-1];
                            r_hist[k] <= r_hist[k-1];
                        end
                    end
                    for (k = 0; k < NDISP; k = k+1) begin
                        disp = k - MAX_D;
                        if (disp > 0) begin
                            a = l_hist[disp-1]; b = in_r;
                        end else if (disp < 0) begin
                            a = in_l; b = r_hist[-disp-1];
                        end else begin
                            a = in_l; b = in_r;
                        end
                        if ((disp == 0) || (x >= ((disp < 0) ? -disp : disp))) begin
                            aa = {{PIX_W{1'b0}}, a} * {{PIX_W{1'b0}}, a};
                            bb = {{PIX_W{1'b0}}, b} * {{PIX_W{1'b0}}, b};
                            ab = {{PIX_W{1'b0}}, a} * {{PIX_W{1'b0}}, b};
                            sum_l[k] <= sum_l[k] + a;
                            sum_r[k] <= sum_r[k] + b;
                            sum_ll[k] <= sum_ll[k] + aa;
                            sum_rr[k] <= sum_rr[k] + bb;
                            sum_lr[k] <= sum_lr[k] + ab;
                            count[k] <= count[k] + 1'b1;
                        end
                    end
                    if (x == TILE_W-1) begin
                        x <= '0;
                        if (y == TILE_H-1) begin
                            y <= '0;
                            state <= PREP;
                            score_idx <= '0;
                        end else y <= y + 1'b1;
                    end else x <= x + 1'b1;
                end
                PREP: begin
                    k = score_idx;
                    nx = count[k]; ax = sum_l[k]; bx = sum_r[k];
                    aax = sum_ll[k]; bbx = sum_rr[k]; abx = sum_lr[k];
                    n_sll_tmp = nx * aax;
                    sl_sq_tmp = ax * ax;
                    n_srr_tmp = nx * bbx;
                    sr_sq_tmp = bx * bx;
                    n_slr_tmp = nx * abx;
                    sl_sr_tmp = ax * bx;
                    vl_tmp = n_sll_tmp - sl_sq_tmp;
                    vr_tmp = n_srr_tmp - sr_sq_tmp;
                    cv_tmp = $signed({1'b0, n_slr_tmp}) - $signed({1'b0, sl_sr_tmp});
                    den2_tmp = vl_tmp * vr_tmp;
                    if ((vl_tmp == 0) || (vr_tmp == 0)) begin
                        score_tmp = -16'sd32768;
                        scores[k] <= score_tmp;
                        if (score_idx == NDISP-1) state <= REPORT;
                        else begin score_idx <= score_idx + 1'b1; state <= PREP; end
                    end else begin
                        den2_reg <= den2_tmp;
                        cov_reg <= cv_tmp;
                        sqrt_root <= '0;
                        sqrt_rem <= '0;
                        sqrt_idx <= VAR_W-1;
                        state <= SQRT;
                    end
                end
                SQRT: begin
                    rem_tmp = (sqrt_rem << 2) |
                              ((den2_reg >> (sqrt_idx*2)) & {{(2*VAR_W){1'b0}}, 2'b11});
                    trial_tmp = (sqrt_root << 2) | {{VAR_W{1'b0}}, 1'b1};
                    if (rem_tmp >= trial_tmp) begin
                        rem_tmp = rem_tmp - trial_tmp;
                        root_next_tmp = (sqrt_root << 1) | 1'b1;
                    end else begin
                        root_next_tmp = sqrt_root << 1;
                    end
                    sqrt_root <= root_next_tmp;
                    sqrt_rem <= rem_tmp;
                    if (sqrt_idx == 0) begin
                        divisor_reg <= root_next_tmp;
                        magnitude_tmp = cov_reg[VAR_W] ? -cov_reg : cov_reg;
                        dividend_shift <= magnitude_tmp << 15;
                        quotient_reg <= '0;
                        div_rem <= '0;
                        div_idx <= SCORE_W-1;
                        state <= DIVIDE;
                    end else sqrt_idx <= sqrt_idx - 1'b1;
                end
                DIVIDE: begin
                    rem_div_tmp = (div_rem << 1) | dividend_shift[SCORE_W-1];
                    quotient_tmp = quotient_reg << 1;
                    if (rem_div_tmp >= {1'b0, divisor_reg}) begin
                        rem_div_tmp = rem_div_tmp - {1'b0, divisor_reg};
                        quotient_tmp[0] = 1'b1;
                    end
                    div_rem <= rem_div_tmp;
                    quotient_reg <= quotient_tmp;
                    dividend_shift <= dividend_shift << 1;
                    if (div_idx == 0) begin
                        if (cov_reg[VAR_W]) begin
                            if (quotient_tmp > 32767) score_tmp = -16'sd32767;
                            else score_tmp = -$signed(quotient_tmp[15:0]);
                        end else begin
                            if (quotient_tmp > 32767) score_tmp = 16'sd32767;
                            else score_tmp = $signed(quotient_tmp[15:0]);
                        end
                        scores[score_idx] <= score_tmp;
                        if (score_idx == NDISP-1) state <= REPORT;
                        else begin score_idx <= score_idx + 1'b1; state <= PREP; end
                    end else div_idx <= div_idx - 1'b1;
                end
                REPORT: begin
                    peak_tmp = -16'sd32768;
                    peak_index_tmp = '0;
                    second_tmp = -16'sd32768;
                    for (k = 0; k < NDISP; k = k+1) begin
                        if (scores[k] > peak_tmp) begin
                            peak_tmp = scores[k];
                            peak_index_tmp = k[4:0];
                        end
                    end
                    for (k = 0; k < NDISP; k = k+1) begin
                        if ((k+1 < peak_index_tmp || k > peak_index_tmp+1) &&
                            scores[k] > second_tmp) second_tmp = scores[k];
                    end
                    conf_num_small = (peak_tmp - second_tmp) * 255;
                    conf_den_small = 32767 - second_tmp;
                    confidence_tmp = (conf_den_small != 0) ? conf_num_small / conf_den_small : 0;
                    interp_num_small = 0;
                    interp_den_small = 0;
                    if ((peak_index_tmp > 0) && (peak_index_tmp < NDISP-1)) begin
                        interp_num_small = 8 * (scores[peak_index_tmp-1] - scores[peak_index_tmp+1]);
                        interp_den_small = scores[peak_index_tmp-1] - 2*scores[peak_index_tmp] + scores[peak_index_tmp+1];
                    end
                    interp_tmp = (interp_den_small < 0) ? interp_num_small / interp_den_small : 0;
                    if (interp_tmp > 8) interp_tmp = 8;
                    if (interp_tmp < -8) interp_tmp = -8;
                    if (peak_tmp == -16'sd32768) begin
                        phase_q4_4 <= '0;
                        confidence_u8 <= '0;
                        low_texture <= 1'b1;
                    end else begin
                        disp = peak_index_tmp;
                        disp = disp - MAX_D;
                        phase_q4_4 <= disp * (1 << FRAC) + interp_tmp;
                        confidence_u8 <= confidence_tmp[7:0];
                        low_texture <= 1'b0;
                    end
                    out_valid <= 1'b1;
                    state <= CAPTURE;
                    x <= '0; y <= '0;
                    for (i = 0; i < NDISP; i = i+1) begin
                        sum_l[i] <= '0; sum_r[i] <= '0;
                        sum_ll[i] <= '0; sum_rr[i] <= '0; sum_lr[i] <= '0;
                        count[i] <= '0;
                    end
                end
                default: state <= CAPTURE;
            endcase
        end
    end
endmodule
