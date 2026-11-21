module miter_test(
    input clk, rst, en
);
    wire [3:0] count_ref, count_uut;

    counter ref (.clk(clk), .rst(rst), .en(en), .count(count_ref), .mutsel(1'b0));
    counter uut (.clk(clk), .rst(rst), .en(en), .count(count_uut), .mutsel(1'b1));

    // 强制保留的计数器
    (* keep *) reg [1:0] init_counter = 2'b00;
    always @(posedge clk) begin
        if (init_counter < 2'b11) init_counter <= init_counter + 1'b1;
    end

    // 强制保留的断言
    always @(*) begin
        if (init_counter == 2'b11) begin
            assert(count_ref == count_uut);
        end
    end
endmodule