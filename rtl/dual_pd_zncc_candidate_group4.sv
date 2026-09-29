// Synthesis-friendly candidate front end.
// Four physical candidate slots are reused for five groups: 4+4+4+4+1
// candidates. The shift choices are compile-time case branches, so the
// original 17-way variable-index datapath is not replicated.
module dual_pd_zncc_candidate_group4 #(
    parameter integer PIX_W=12,
    parameter integer MAX_SHIFT=16
) (
    input logic [2:0] group,
    input logic valid,
    input logic x_parity,y_parity,
    input logic [20*PIX_W-1:0] l_window,
    input logic [20*PIX_W-1:0] r_window,
    input logic [19:0] mask_l,mask_r,
    output logic [3:0] delta_valid,
    output logic [4*672-1:0] delta_stats
);
    function automatic integer shift_for(input integer slot,input logic [2:0] g);
        begin
            case (g)
                3'd0: shift_for=-16+slot*2;
                3'd1: shift_for=-8+slot*2;
                3'd2: shift_for=0+slot*2;
                3'd3: shift_for=8+slot*2;
                default: shift_for=16+slot*2;
            endcase
        end
    endfunction
    function automatic [PIX_W-1:0] sample_at(
        input logic [20*PIX_W-1:0] bus,input integer index);
        begin
            case(index)
                0:sample_at=bus[0*PIX_W +: PIX_W]; 1:sample_at=bus[1*PIX_W +: PIX_W];
                2:sample_at=bus[2*PIX_W +: PIX_W]; 3:sample_at=bus[3*PIX_W +: PIX_W];
                4:sample_at=bus[4*PIX_W +: PIX_W]; 5:sample_at=bus[5*PIX_W +: PIX_W];
                6:sample_at=bus[6*PIX_W +: PIX_W]; 7:sample_at=bus[7*PIX_W +: PIX_W];
                8:sample_at=bus[8*PIX_W +: PIX_W]; 9:sample_at=bus[9*PIX_W +: PIX_W];
                10:sample_at=bus[10*PIX_W +: PIX_W]; 11:sample_at=bus[11*PIX_W +: PIX_W];
                12:sample_at=bus[12*PIX_W +: PIX_W]; 13:sample_at=bus[13*PIX_W +: PIX_W];
                14:sample_at=bus[14*PIX_W +: PIX_W]; 15:sample_at=bus[15*PIX_W +: PIX_W];
                16:sample_at=bus[16*PIX_W +: PIX_W]; 17:sample_at=bus[17*PIX_W +: PIX_W];
                18:sample_at=bus[18*PIX_W +: PIX_W]; default:sample_at=bus[19*PIX_W +: PIX_W];
            endcase
        end
    endfunction
    function automatic logic mask_at(input logic [19:0] bus,input integer index);
        begin
            case(index)
                0:mask_at=bus[0];1:mask_at=bus[1];2:mask_at=bus[2];3:mask_at=bus[3];
                4:mask_at=bus[4];5:mask_at=bus[5];6:mask_at=bus[6];7:mask_at=bus[7];
                8:mask_at=bus[8];9:mask_at=bus[9];10:mask_at=bus[10];11:mask_at=bus[11];
                12:mask_at=bus[12];13:mask_at=bus[13];14:mask_at=bus[14];15:mask_at=bus[15];
                16:mask_at=bus[16];17:mask_at=bus[17];18:mask_at=bus[18];default:mask_at=bus[19];
            endcase
        end
    endfunction

    integer s,l,sh,li,ri,ph,off;
    logic [PIX_W-1:0] a,b;
    logic [2*PIX_W-1:0] aa,bb,ab;
    logic [671:0] v;
    always_comb begin
        delta_valid='0; delta_stats='0;
        for (s=0;s<4;s=s+1) begin
            v='0; sh=shift_for(s,group); a='0; b='0; aa='0; bb='0; ab='0;
            l=0; li=0; ri=0; ph=0; off=0;
            if (valid && !(group==3'd4 && s!=0)) begin
                for (l=0;l<4;l=l+1) begin
                    li=8+l;
                    ri=li+sh;
                    if (ri>=0 && ri<20 && mask_at(mask_l,li) && mask_at(mask_r,ri)) begin
                        a=sample_at(l_window,li); b=sample_at(r_window,ri);
                        aa=a*a; bb=b*b; ab=a*b;
                        ph={y_parity,x_parity^(li[0])}; off=ph*168;
                        v[off+0 +: 24]=v[off+0 +: 24]+a;
                        v[off+24 +: 24]=v[off+24 +: 24]+b;
                        v[off+48 +: 36]=v[off+48 +: 36]+aa;
                        v[off+84 +: 36]=v[off+84 +: 36]+bb;
                        v[off+120 +: 36]=v[off+120 +: 36]+ab;
                        v[off+156 +: 12]=v[off+156 +: 12]+1'b1;
                    end
                end
                delta_valid[s]=1'b1;
            end
            delta_stats[s*672 +: 672]=v;
        end
    end
endmodule
