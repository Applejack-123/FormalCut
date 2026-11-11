module mask_test(
    input wire a,
    input wire b,
    input wire mask,
    output wire out
);
    // 如果 mask 为 1，输出恒定为 0，屏蔽所有故障
    assign out = mask ? 1'b0 : (a & b);
endmodule