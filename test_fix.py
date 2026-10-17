import re
import sys
sys.path.insert(0, 'd:/rtl-verification')
import core

sim = core.HDLSimulator()
code = '''
module traffic_light_controller (
    input clk, rst_n,
    output reg [2:0] state_out
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) state_out <= 3'b006;
        else state_out <= 3'b002;
    end
endmodule
'''
valid_before, err_before = sim.validate_verilog(code, 'traffic_light_controller')
print('Before fix:', valid_before, err_before)

fixed_code = re.sub(r"(\b\d+)'b([0-9_]*[2-9][0-9_]*)", r"\1'd\2", code)
valid_after, err_after = sim.validate_verilog(fixed_code, 'traffic_light_controller')
print('After fix:', valid_after, err_after)
