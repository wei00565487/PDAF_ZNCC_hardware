module tb_dual_pd_zncc_system;
    localparam integer W=32, H=24, TC=4, TR=3, TW=8, TH=8;
    logic clk=0, rst_n=0, sensor_valid=0;
    logic [47:0] sensor_l=0, sensor_r=0;
    logic [7:0] ram_en, ram_we;
    logic [8*6-1:0] ram_addr;
    logic [8*24-1:0] ram_wdata, ram_rdata;
    logic [3:0] result_valid, result_low_texture;
    logic [19:0] result_tile_col;
    logic [1:0] result_tile_row;
    logic [35:0] result_phase_q4_4;
    logic [31:0] result_confidence_u8;
    logic overrun;
    logic [23:0] mem[0:7][0:63];
    integer i, j, k, results=0, timeout=0;

    always #5 clk=~clk;
    dual_pd_zncc_system #(.FRAME_W(W), .FRAME_H(H), .TILE_COLS(TC),
        .TILE_ROWS(TR), .TILE_W(TW), .TILE_H(TH), .LANES(4),
        .INPUT_PIXELS(4), .ADDR_W(6)) dut (
        .clk, .rst_n, .sensor_valid, .sensor_l, .sensor_r,
        .ram_en, .ram_we, .ram_addr, .ram_wdata, .ram_rdata,
        .result_valid, .result_tile_col, .result_tile_row,
        .result_phase_q4_4, .result_confidence_u8, .result_low_texture, .overrun
    );

    always_ff @(posedge clk) begin
        for (integer b=0; b<8; b=b+1) begin
            if (ram_en[b]) begin
                if (ram_we[b]) mem[b][ram_addr[b*6 +: 6]] <= ram_wdata[b*24 +: 24];
                else ram_rdata[b*24 +: 24] <= mem[b][ram_addr[b*6 +: 6]];
            end
        end
        results <= results + $countones(result_valid);
    end

    initial begin
        repeat (4) @(negedge clk); rst_n=1;
        for (i=0; i<H; i=i+1) begin
            for (j=0; j<W; j=j+4) begin
                @(negedge clk); sensor_valid=1;
                for (k=0; k<4; k=k+1) begin
                    sensor_l[k*12 +: 12] = (((((j+k)*7+i*11) ^ ((j+k)>>1)) & 12'h3ff) + 100);
                    sensor_r[k*12 +: 12] = sensor_l[k*12 +: 12];
                end
            end
            if (i == 7) begin
                @(posedge clk); #1;
                for (k=0; k<4; k=k+1)
                    if (mem[k][0][23:12] !== ((((k*7) ^ (k>>1)) & 12'h3ff) + 100))
                        $fatal(1, "4-pixel bank %0d write/packing mismatch", k);
            end
        end
        @(negedge clk); sensor_valid=0;
        while ((results < TC*TR) && (timeout < 20000)) begin
            @(negedge clk); timeout=timeout+1;
        end
        if (results != TC*TR) $fatal(1, "result count %0d, expected %0d", results, TC*TR);
        if (overrun) $fatal(1, "band buffer overrun");
        $display("PASS system results=%0d cycles_after_input=%0d", results, timeout);
        $finish;
    end
endmodule
