// AI-generated demonstration circuit for FormaCut.
//
// Two observation points:
//   out : triple-modular-redundant counter, passed through a majority voter
//   raw : a plain counter driven by the same inputs
//
// A single-bit SEU on one of the three TMR counters is masked by the voter,
// while the same fault on `raw` reaches the output.  The expected form of the
// report is therefore "TMR bits PRUNED, raw bits KEEP", which makes the
// reduction visible instead of showing an uninteresting 0% or 100%.
module tmr_demo(
    input wire clk,
    input wire rst,
    input wire en,
    output wire [3:0] out,
    output wire [3:0] raw
);
    reg [3:0] c1;
    reg [3:0] c2;
    reg [3:0] c3;
    reg [3:0] raw_q;

    always @(posedge clk) begin
        if (rst) begin
            c1 <= 4'b0000;
            c2 <= 4'b0000;
            c3 <= 4'b0000;
            raw_q <= 4'b0000;
        end else if (en) begin
            c1 <= c1 + 1'b1;
            c2 <= c2 + 1'b1;
            c3 <= c3 + 1'b1;
            raw_q <= raw_q + 1'b1;
        end
    end

    // Bitwise majority: out[i] = majority(c1[i], c2[i], c3[i])
    assign out = (c1 & c2) | (c2 & c3) | (c1 & c3);

    // Unprotected observation point: any single-bit fault is visible.
    assign raw = raw_q;
endmodule
