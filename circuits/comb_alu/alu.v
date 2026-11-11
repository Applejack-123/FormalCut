module alu(
    input wire [3:0] a,
    input wire [3:0] b,
    input wire       mask, 
    output wire [3:0] out
);
    assign out = mask ? 4'b0000 : (a & b);
endmodule