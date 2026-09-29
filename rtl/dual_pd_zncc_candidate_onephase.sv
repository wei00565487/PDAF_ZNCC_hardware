// One candidate / one Bayer phase engine.
// The engine is intentionally serialized so the wide 4-phase statistic bus
// is not replicated in the candidate datapath.
module dual_pd_zncc_candidate_onephase #(
    parameter integer PIX_W=12
) (
    input logic [4:0] candidate,
    input logic [1:0] phase_sel,
    input logic valid,
    input logic x_parity,y_parity,
    input logic [20*PIX_W-1:0] l_window,
    input logic [20*PIX_W-1:0] r_window,
    input logic [19:0] mask_l,mask_r,
    output logic delta_valid,
    output logic [167:0] delta_stats
);
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
                0:mask_at=bus[0]; 1:mask_at=bus[1]; 2:mask_at=bus[2]; 3:mask_at=bus[3];
                4:mask_at=bus[4]; 5:mask_at=bus[5]; 6:mask_at=bus[6]; 7:mask_at=bus[7];
                8:mask_at=bus[8]; 9:mask_at=bus[9]; 10:mask_at=bus[10]; 11:mask_at=bus[11];
                12:mask_at=bus[12]; 13:mask_at=bus[13]; 14:mask_at=bus[14]; 15:mask_at=bus[15];
                16:mask_at=bus[16]; 17:mask_at=bus[17]; 18:mask_at=bus[18]; default:mask_at=bus[19];
            endcase
        end
    endfunction

    integer l,li,ri,shift,ph;
    logic [23:0] sum_l,sum_r;
    logic [35:0] sum_aa,sum_bb,sum_ab;
    logic [11:0] count;
    logic [PIX_W-1:0] a,b;
    logic [2*PIX_W-1:0] aa,bb,ab;
    always_comb begin
        sum_l='0; sum_r='0; sum_aa='0; sum_bb='0; sum_ab='0; count='0;
        a='0; b='0; aa='0; bb='0; ab='0; l=0; li=0; ri=0; ph=0; shift=0;
        shift = -16 + candidate*2;
        if (valid) begin
            for (l=0;l<4;l=l+1) begin
                li=8+l; ri=li+shift;
                ph={y_parity,x_parity ^ li[0]};
                if (ri>=0 && ri<20 && ph==phase_sel && mask_at(mask_l,li) && mask_at(mask_r,ri)) begin
                    a=sample_at(l_window,li); b=sample_at(r_window,ri);
                    aa=a*a; bb=b*b; ab=a*b;
                    sum_l=sum_l+a; sum_r=sum_r+b;
                    sum_aa=sum_aa+aa; sum_bb=sum_bb+bb; sum_ab=sum_ab+ab;
                    count=count+1'b1;
                end
            end
        end
        delta_valid=valid;
        delta_stats={count,sum_ab,sum_bb,sum_aa,sum_r,sum_l};
    end
endmodule
