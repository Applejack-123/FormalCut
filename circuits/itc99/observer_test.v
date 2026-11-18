module observer_test(
    input wire clk,
    input wire rst,
    output wire out
);
    // 加上 (* keep *) 防止被 Yosys 优化掉
    (* keep *) reg dummy; 
    (* keep *) reg dummy2;

    always @(posedge clk) begin
        if (rst) begin
            dummy <= 1'b0;
            dummy2 <= 1'b0;
        end else begin
            dummy <= ~dummy;
            dummy2 <= dummy; 
        end
    end

    // 核心设计：把内部状态通过常量与的方式输出，无论 dummy 是什么，out 永远是 0
    // 这样它既被保留了，又绝对不可能影响最终输出
    assign out = dummy & 1'b0; 
endmodule