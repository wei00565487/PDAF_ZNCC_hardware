// Macro-backed row-reuse backend for the pooled ZNCC design.
// The raster/pseudo-luma accumulator presents one completed zone's 17 pooled
// sufficient-statistics records at a time.  A single 32-deep farm is reused:
// the old zone record is read and copied into the serial scorer before that
// address is released for the next zone row's write.
module dual_pd_zncc_pooled_sram_score_top (
    input  logic clk,
    input  logic rst_n,
    input  logic zone_stats_valid,
    input  logic [4:0] zone_stats_addr,
    input  logic [17*184-1:0] zone_stats_records,
    output logic zone_stats_ready,
    input  logic score_row_start,
    output logic score_row_ready,
    output logic busy,
    output logic out_valid,
    output logic [4:0] out_zone_addr,
    output logic [9:0] phase_q4_4,
    output logic [7:0] confidence_u8,
    output logic [15:0] peak_zncc_q15,
    output logic [15:0] second_zncc_q15,
    output logic low_texture
);
    typedef enum logic [1:0] {IDLE, ISSUE_READ, WAIT_READ, SCORE} state_t;
    state_t state;

    logic [31:0] valid_map;
    logic [4:0] scan_addr;
    logic [16:0] rd_en, rd_valid, wr_en;
    logic [4:0] rd_addr, wr_addr;
    logic [17*185-1:0] rd_data, wr_data;
    logic [17*184-1:0] scorer_records;
    logic scorer_start, scorer_busy, scorer_valid;
    logic signed [9:0] scorer_phase;
    logic [7:0] scorer_confidence;
    logic signed [15:0] scorer_peak, scorer_second;
    logic scorer_low_texture;

    assign zone_stats_ready = !valid_map[zone_stats_addr];
    assign score_row_ready = (state == IDLE) && (&valid_map);
    assign busy = (state != IDLE) || scorer_busy;
    assign rd_addr = scan_addr;
    assign wr_addr = zone_stats_addr;

    genvar c;
    generate for (c = 0; c < 17; c = c + 1) begin : gen_record_pack
        assign wr_data[c*185 +: 185] = {1'b0, zone_stats_records[c*184 +: 184]};
        assign scorer_records[c*184 +: 184] = rd_data[c*185 +: 184];
    end endgenerate

    assign wr_en = {17{zone_stats_valid && zone_stats_ready}};
    dual_pd_zncc_stats_pooled_macro_farm u_stats (
        .clk,
        .rd_en,
        .rd_addr,
        .rd_valid,
        .rd_data,
        .wr_en,
        .wr_addr,
        .wr_data
    );

    dual_pd_zncc_scorer_pooled u_scorer (
        .clk,
        .rst_n,
        .start(scorer_start),
        .stats_records(scorer_records),
        .busy(scorer_busy),
        .out_valid(scorer_valid),
        .phase_q4_4(scorer_phase),
        .score_u8(),
        .confidence_u8(scorer_confidence),
        .peak_zncc_q15(scorer_peak),
        .second_zncc_q15(scorer_second),
        .low_texture(scorer_low_texture)
    );

    always_comb begin
        rd_en = '0;
        if (state == ISSUE_READ)
            rd_en = '1;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            valid_map <= '0;
            scan_addr <= '0;
            scorer_start <= 1'b0;
            out_valid <= 1'b0;
            out_zone_addr <= '0;
            phase_q4_4 <= '0;
            confidence_u8 <= '0;
            peak_zncc_q15 <= '0;
            second_zncc_q15 <= '0;
            low_texture <= 1'b1;
        end else begin
            scorer_start <= 1'b0;
            out_valid <= 1'b0;

            if (zone_stats_valid && zone_stats_ready)
                valid_map[zone_stats_addr] <= 1'b1;

            case (state)
                IDLE: if (score_row_start && score_row_ready) begin
                    scan_addr <= 0;
                    state <= ISSUE_READ;
                end
                ISSUE_READ: state <= WAIT_READ;
                WAIT_READ: if (&rd_valid) begin
                    // Release this address only after its old contents have
                    // been sampled by every candidate SRAM read port.
                    valid_map[scan_addr] <= 1'b0;
                    scorer_start <= 1'b1;
                    state <= SCORE;
                end
                SCORE: if (scorer_valid) begin
                    out_valid <= 1'b1;
                    out_zone_addr <= scan_addr;
                    phase_q4_4 <= scorer_phase;
                    confidence_u8 <= scorer_confidence;
                    peak_zncc_q15 <= scorer_peak;
                    second_zncc_q15 <= scorer_second;
                    low_texture <= scorer_low_texture;
                    if (scan_addr == 5'd31) begin
                        state <= IDLE;
                    end else begin
                        scan_addr <= scan_addr + 1'b1;
                        state <= ISSUE_READ;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
