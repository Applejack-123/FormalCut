module miter_wrapper(
    input wire clk,
    input wire rst,
    input wire en,
    output wire [3:0] count_golden,
    output wire [3:0] count_faulty
);
    // 正常电路
    counter golden_inst (
        .clk(clk), .rst(rst), .en(en), .count(count_golden)
    );

    // 故障电路（通过 Yosys 在网表中强行断开 counter 的内部寄存器 Q 端来实现）
    counter faulty_inst (
        .clk(clk), .rst(rst), .en(en), .count(count_faulty)
    );

    // 核心断言：只要发生故障，正常输出必须等于故障输出
    always @(*) begin
        assert(count_golden == count_faulty);
    end
endmodule