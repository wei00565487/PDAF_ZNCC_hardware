// Raster-to-four-core controller. Image storage is external SRAM so that
// LibreLane can map the compute core independently of a foundry memory macro.
// SRAM organization: ping/pong x four x-mod-4 banks, 125000 x 24 bits each.
module dual_pd_zncc_system #(
    parameter integer FRAME_W = 4000,
    parameter integer FRAME_H = 3000,
    parameter integer TILE_COLS = 32,
    parameter integer TILE_ROWS = 24,
    parameter integer PIX_W = 12,
    parameter integer INPUT_PIXELS = 4,
    parameter integer LANES = 4,
    parameter integer TILE_W = FRAME_W / TILE_COLS,
    parameter integer TILE_H = FRAME_H / TILE_ROWS,
    parameter integer WORDS_PER_BAND = FRAME_W*TILE_H/4,
    parameter integer ADDR_W = $clog2(WORDS_PER_BAND)
) (
    input  logic                         clk,
    input  logic                         rst_n,
    input  logic                         sensor_valid,
    input  logic [INPUT_PIXELS*PIX_W-1:0] sensor_l,
    input  logic [INPUT_PIXELS*PIX_W-1:0] sensor_r,

    // Eight synchronous 1RW SRAM macros: 2 ping/pong banks x 4 interleaves.
    output logic [7:0]                   ram_en,
    output logic [7:0]                   ram_we,
    output logic [8*ADDR_W-1:0]          ram_addr,
    output logic [8*(2*PIX_W)-1:0]       ram_wdata,
    input  logic [8*(2*PIX_W)-1:0]       ram_rdata,

    output logic [LANES-1:0]             result_valid,
    output logic [LANES*5-1:0]           result_tile_col,
    output logic [$clog2(TILE_ROWS)-1:0] result_tile_row,
    output logic [LANES*9-1:0]           result_phase_q4_4,
    output logic [LANES*8-1:0]           result_confidence_u8,
    output logic [LANES-1:0]             result_low_texture,
    output logic                         overrun
);
    localparam integer X_W = $clog2(FRAME_W);
    localparam integer Y_W = $clog2(FRAME_H);
    localparam integer T_W = $clog2(TILE_W);
    localparam integer TY_W = $clog2(TILE_H);
    localparam integer COL_W = $clog2(TILE_COLS);
    localparam integer ROW_W = $clog2(TILE_ROWS);

`ifndef SYNTHESIS
    initial begin
        if ((INPUT_PIXELS < 1) || ((4 % INPUT_PIXELS) != 0) ||
            ((FRAME_W % INPUT_PIXELS) != 0))
            $fatal(1, "INPUT_PIXELS must divide 4 and FRAME_W");
    end
`endif

    typedef enum logic [1:0] {IDLE, READ_TILE, WAIT_TILE} reader_state_t;
    reader_state_t reader_state;
    logic [X_W-1:0] sensor_x;
    logic [Y_W-1:0] sensor_y;
    logic [TY_W-1:0] write_y;
    logic write_bank;
    logic [1:0] band_valid;
    logic [ROW_W-1:0] band_number [0:1];

    logic active_read_bank;
    logic [ROW_W-1:0] active_band_row;
    logic [2:0] group_index;
    logic [T_W-1:0] tile_x;
    logic [TY_W-1:0] tile_y;
    logic read_issue;
    logic read_issue_q;
    logic read_bank_q;
    logic [1:0] read_lane_bank_q [0:LANES-1];
    logic [LANES-1:0] core_ready, core_valid;
    logic [LANES*9-1:0] core_phase;
    logic [LANES*8-1:0] core_confidence;
    logic [LANES-1:0] core_low_texture;
    logic all_core_done;
    integer lane, macro_bank, macro_lane, input_pixel;
    integer absolute_x;
    integer word_address;

    assign all_core_done = &core_valid;
    assign result_valid = core_valid;
    assign result_phase_q4_4 = core_phase;
    assign result_confidence_u8 = core_confidence;
    assign result_low_texture = core_low_texture;
    assign result_tile_row = active_band_row;

    // Each aligned input beat writes four adjacent pixels to the four x-mod-4
    // SRAM banks at one word address. Smaller supported beats may use a subset.
    always_comb begin
        ram_en = '0;
        ram_we = '0;
        ram_addr = '0;
        ram_wdata = '0;
        macro_bank = 0;
        macro_lane = 0;
        absolute_x = 0;
        word_address = 0;
        input_pixel = 0;
        read_issue = (reader_state == READ_TILE) && (&core_ready);

        if (sensor_valid) begin
            for (input_pixel = 0; input_pixel < INPUT_PIXELS; input_pixel = input_pixel+1) begin
                macro_bank = (sensor_x + input_pixel) % 4;
                word_address = write_y * (FRAME_W/4) + ((sensor_x + input_pixel)/4);
                macro_lane = write_bank*4 + macro_bank;
                ram_en[macro_lane] = 1'b1;
                ram_we[macro_lane] = 1'b1;
                ram_addr[macro_lane*ADDR_W +: ADDR_W] = word_address[ADDR_W-1:0];
                ram_wdata[macro_lane*(2*PIX_W) +: 2*PIX_W] = {
                    sensor_l[input_pixel*PIX_W +: PIX_W],
                    sensor_r[input_pixel*PIX_W +: PIX_W]};
            end
        end

        if (read_issue) begin
            for (macro_bank = 0; macro_bank < 4; macro_bank = macro_bank+1) begin
                macro_lane = (macro_bank - tile_x + 4) % 4;
                absolute_x = group_index*TILE_W*LANES + macro_lane*TILE_W + tile_x;
                word_address = tile_y*(FRAME_W/4) + (absolute_x/4);
                ram_en[active_read_bank*4 + macro_bank] = 1'b1;
                ram_we[active_read_bank*4 + macro_bank] = 1'b0;
                ram_addr[(active_read_bank*4 + macro_bank)*ADDR_W +: ADDR_W] = word_address[ADDR_W-1:0];
            end
        end
    end

    genvar g;
    generate for (g = 0; g < LANES; g = g+1) begin : gen_core
        logic [2*PIX_W-1:0] selected_pair;
        assign selected_pair = ram_rdata[(read_bank_q*4 + read_lane_bank_q[g])*(2*PIX_W) +: 2*PIX_W];
        dual_pd_zncc_tile #(.PIX_W(PIX_W), .TILE_W(TILE_W), .TILE_H(TILE_H), .MAX_D(8)) u_tile (
            .clk(clk), .rst_n(rst_n), .in_valid(read_issue_q),
            .in_l(selected_pair[2*PIX_W-1:PIX_W]),
            .in_r(selected_pair[PIX_W-1:0]),
            .in_ready(core_ready[g]), .out_valid(core_valid[g]),
            .phase_q4_4(core_phase[g*9 +: 9]),
            .confidence_u8(core_confidence[g*8 +: 8]),
            .low_texture(core_low_texture[g])
        );
        assign result_tile_col[g*5 +: 5] = group_index*LANES + g;
    end endgenerate

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sensor_x <= '0;
            sensor_y <= '0;
            write_y <= '0;
            write_bank <= 1'b0;
            band_valid <= 2'b00;
            band_number[0] <= '0;
            band_number[1] <= '0;
            reader_state <= IDLE;
            active_read_bank <= 1'b0;
            active_band_row <= '0;
            group_index <= '0;
            tile_x <= '0;
            tile_y <= '0;
            read_issue_q <= 1'b0;
            read_bank_q <= 1'b0;
            overrun <= 1'b0;
            for (lane = 0; lane < LANES; lane = lane+1) read_lane_bank_q[lane] <= '0;
        end else begin
            read_issue_q <= read_issue;
            if (read_issue) begin
                read_bank_q <= active_read_bank;
                for (lane = 0; lane < LANES; lane = lane+1)
                    read_lane_bank_q[lane] <= (lane + tile_x) % 4;
                if (tile_x == TILE_W-1) begin
                    tile_x <= '0;
                    if (tile_y == TILE_H-1) begin
                        tile_y <= '0;
                        reader_state <= WAIT_TILE;
                    end else tile_y <= tile_y + 1'b1;
                end else tile_x <= tile_x + 1'b1;
            end

            if (sensor_valid) begin
                if (sensor_x == FRAME_W-INPUT_PIXELS) begin
                    sensor_x <= '0;
                    sensor_y <= (sensor_y == FRAME_H-1) ? '0 : sensor_y + 1'b1;
                    if (write_y == TILE_H-1) begin
                        if (band_valid[write_bank]) overrun <= 1'b1;
                        band_valid[write_bank] <= 1'b1;
                        band_number[write_bank] <= sensor_y / TILE_H;
                        write_y <= '0;
                        write_bank <= ~write_bank;
                    end else write_y <= write_y + 1'b1;
                end else sensor_x <= sensor_x + INPUT_PIXELS;
            end

            if (reader_state == IDLE) begin
                if (band_valid[0]) begin
                    active_read_bank <= 1'b0;
                    active_band_row <= band_number[0];
                    band_valid[0] <= 1'b0;
                    group_index <= '0; tile_x <= '0; tile_y <= '0;
                    reader_state <= READ_TILE;
                end else if (band_valid[1]) begin
                    active_read_bank <= 1'b1;
                    active_band_row <= band_number[1];
                    band_valid[1] <= 1'b0;
                    group_index <= '0; tile_x <= '0; tile_y <= '0;
                    reader_state <= READ_TILE;
                end
            end else if ((reader_state == WAIT_TILE) && all_core_done) begin
                if (group_index == TILE_COLS/LANES-1) begin
                    reader_state <= IDLE;
                end else begin
                    group_index <= group_index + 1'b1;
                    tile_x <= '0; tile_y <= '0;
                    reader_state <= READ_TILE;
                end
            end
        end
    end
endmodule
