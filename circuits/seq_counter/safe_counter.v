module safe_counter(
    input wire clk, rst, en, mode,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst) count <= 0;
        else if (mode) count <= 0; // 安全模式
        else if (en) count <= count + 1;
    end
endmodule