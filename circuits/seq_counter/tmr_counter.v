module tmr_counter(
    input wire clk,
    input wire rst,
    input wire en,
    output wire [3:0] out
);
    // 3 个冗余的计数器
    wire [3:0] c1, c2, c3;
    
    counter u1(.clk(clk), .rst(rst), .en(en), .count(c1));
    counter u2(.clk(clk), .rst(rst), .en(en), .count(c2));
    counter u3(.clk(clk), .rst(rst), .en(en), .count(c3));

    // 多数表决器（Majority Voter）
    // 只要 3 个副本中有 2 个输出一致，最终的 out 就输出那个正确的值
    assign out = (c1 & c2) | (c2 & c3) | (c1 & c3);
endmodule