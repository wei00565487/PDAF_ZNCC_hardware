`timescale 1ns/1ps

module tb_dual_pd_zncc_tile;
    localparam integer W = 16;
    localparam integer H = 8;
    logic clk = 0;
    logic rst_n = 0;
    logic in_valid = 0;
    logic [11:0] in_l = 0, in_r = 0;
    logic in_ready, out_valid, low_texture;
    logic signed [8:0] phase_q4_4;
    logic [7:0] confidence_u8;
    integer x, y, sent;
    logic [11:0] row_l [0:W-1];
    logic [11:0] row_r [0:W-1];

    always #5 clk = ~clk;

    dual_pd_zncc_tile #(.TILE_W(W), .TILE_H(H), .MAX_D(2)) dut (
        .clk, .rst_n, .in_valid, .in_l, .in_r, .in_ready,
        .out_valid, .phase_q4_4, .confidence_u8, .low_texture
    );

    initial begin
        repeat (4) @(negedge clk);
        rst_n = 1;
        sent = 0;
        for (y = 0; y < H; y = y+1) begin
            for (x = 0; x < W; x = x+1)
                row_l[x] = (x*211 + y*379 + x*y*17 + 53) & 12'hfff;
            for (x = 0; x < W; x = x+1) begin
                if (x >= 2) row_r[x] = row_l[x-2];
                else row_r[x] = (x*619 + y*127 + 901) & 12'hfff;
            end
            for (x = 0; x < W; x = x+1) begin
                @(negedge clk);
                while (!in_ready) @(negedge clk);
                in_valid = 1;
                in_l = row_l[x];
                in_r = row_r[x];
                sent = sent + 1;
            end
        end
        @(negedge clk);
        in_valid = 0;
        wait (out_valid);
        if (low_texture || phase_q4_4 !== 9'sd32 || confidence_u8 < 200) begin
            $display("FAIL phase=%0d confidence=%0d low_texture=%0d sent=%0d",
                     phase_q4_4, confidence_u8, low_texture, sent);
            $fatal(1);
        end
        $display("PASS phase=%0d/16 px confidence=%0d sent=%0d",
                 phase_q4_4, confidence_u8, sent);

        // A second, flat tile must be rejected as low texture.
        sent = 0;
        for (y = 0; y < H; y = y+1) begin
            for (x = 0; x < W; x = x+1) begin
                @(negedge clk);
                while (!in_ready) @(negedge clk);
                in_valid = 1;
                in_l = 12'd700;
                in_r = 12'd700;
                sent = sent + 1;
            end
        end
        @(negedge clk);
        in_valid = 0;
        wait (out_valid);
        if (!low_texture || confidence_u8 != 0) begin
            $display("FAIL flat confidence=%0d low_texture=%0d", confidence_u8, low_texture);
            $fatal(1);
        end
        $display("PASS flat tile rejected; confidence=%0d", confidence_u8);
        $finish;
    end
endmodule
