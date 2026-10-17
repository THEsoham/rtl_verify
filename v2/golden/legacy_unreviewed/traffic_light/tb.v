// STATUS: UNREVIEWED - Awaiting user review and test before running experiments.
// Testbench: traffic_light_controller self-checking testbench adhering to fixed verification contract.

`timescale 1ns/1ps

module tb;
    reg       clk;
    reg       rst_n;
    reg       car_present_side;
    reg       pedestrian_req;
    reg       emergency_override;

    wire [2:0] main_light;
    wire [2:0] side_light;
    wire       ped_walk;
    wire [2:0] state_out;

    integer errors = 0;

    TopModule #(
        .MAIN_GREEN_CYCLES(10),
        .SIDE_GREEN_CYCLES(6),
        .YELLOW_CYCLES(3),
        .ALL_RED_CYCLES(2)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .car_present_side(car_present_side),
        .pedestrian_req(pedestrian_req),
        .emergency_override(emergency_override),
        .main_light(main_light),
        .side_light(side_light),
        .ped_walk(ped_walk),
        .state_out(state_out)
    );

    always #5 clk = ~clk;

    // Safety assertion monitor: Never both green or both yellow
    always @(posedge clk) begin
        if (rst_n) begin
            if (main_light[0] && side_light[0]) begin
                $display("CRITICAL SAFETY VIOLATION: Both Main and Side are GREEN at time %0t", $time);
                errors = errors + 1;
            end
            if (main_light[1] && side_light[1]) begin
                $display("CRITICAL SAFETY VIOLATION: Both Main and Side are YELLOW at time %0t", $time);
                errors = errors + 1;
            end
            if (main_light[0] && side_light[1]) begin
                $display("CRITICAL SAFETY VIOLATION: Main GREEN while Side YELLOW at time %0t", $time);
                errors = errors + 1;
            end
            if (main_light[1] && side_light[0]) begin
                $display("CRITICAL SAFETY VIOLATION: Main YELLOW while Side GREEN at time %0t", $time);
                errors = errors + 1;
            end
        end
    end

    initial begin
        clk = 0;
        rst_n = 0;
        car_present_side = 0;
        pedestrian_req = 0;
        emergency_override = 0;

        repeat (3) @(posedge clk);
        rst_n = 1;
        @(posedge clk); #1;

        // Reset check: Main should be Green (3'b001), Side should be Red (3'b100)
        if (main_light !== 3'b001 || side_light !== 3'b100 || ped_walk !== 1'b0) begin
            $display("ERROR: Reset lights invalid: main=%b side=%b", main_light, side_light);
            errors = errors + 1;
        end

        // 1. Remain in Main Green while no cars or pedestrians
        repeat (15) @(posedge clk);
        if (main_light !== 3'b001) begin
            $display("ERROR: Left Main Green without demand");
            errors = errors + 1;
        end

        // 2. Pulse pedestrian request & side car demand
        @(posedge clk);
        car_present_side <= 1'b1;
        pedestrian_req   <= 1'b1;
        @(posedge clk);
        pedestrian_req   <= 1'b0;

        // Wait through Main Green (remaining), Yellow (3), All Red 1 (2)
        repeat (15) @(posedge clk);

        // Should reach Side Green with ped_walk = 1
        @(posedge clk); #1;
        if (side_light !== 3'b001 || ped_walk !== 1'b1) begin
            $display("ERROR: Did not service Side Green / Pedestrian correctly: side=%b ped=%b", side_light, ped_walk);
            errors = errors + 1;
        end

        // 3. Emergency override test
        // While in side green, assert emergency vehicle override
        emergency_override <= 1'b1;
        @(posedge clk); #1;
        if (main_light !== 3'b001 || side_light !== 3'b100 || ped_walk !== 1'b0) begin
            $display("ERROR: Emergency preemption failed: main=%b side=%b ped=%b", main_light, side_light, ped_walk);
            errors = errors + 1;
        end

        @(posedge clk);
        emergency_override <= 1'b0;
        car_present_side   <= 1'b0;

        repeat (20) @(posedge clk);

        #20;
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end

endmodule
