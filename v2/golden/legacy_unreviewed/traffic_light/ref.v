// STATUS: UNREVIEWED - Awaiting user review and test before running experiments.
// Module: traffic_light_controller (TopModule)
// Specification: Intersection Traffic Light FSM with pedestrian servicing and emergency preemption.

`timescale 1ns/1ps

module TopModule #(
    parameter MAIN_GREEN_CYCLES = 10,
    parameter SIDE_GREEN_CYCLES = 6,
    parameter YELLOW_CYCLES     = 3,
    parameter ALL_RED_CYCLES    = 2
)(
    input  wire       clk,
    input  wire       rst_n,
    input  wire       car_present_side,
    input  wire       pedestrian_req,
    input  wire       emergency_override,
    output reg  [2:0] main_light, // [Red, Yellow, Green]: 3'b100=Red, 3'b010=Yellow, 3'b001=Green
    output reg  [2:0] side_light, // [Red, Yellow, Green]
    output reg        ped_walk,
    output reg  [2:0] state_out
);

    localparam S_MAIN_GREEN  = 3'd0;
    localparam S_MAIN_YELLOW = 3'd1;
    localparam S_ALL_RED1    = 3'd2;
    localparam S_SIDE_GREEN  = 3'd3;
    localparam S_SIDE_YELLOW = 3'd4;
    localparam S_ALL_RED2    = 3'd5;

    localparam LIGHT_RED    = 3'b100;
    localparam LIGHT_YELLOW = 3'b010;
    localparam LIGHT_GREEN  = 3'b001;

    reg [2:0] state;
    reg [4:0] timer;
    reg       ped_req_latched;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= S_MAIN_GREEN;
            timer           <= 5'd0;
            ped_req_latched <= 1'b0;
            main_light      <= LIGHT_GREEN;
            side_light      <= LIGHT_RED;
            ped_walk        <= 1'b0;
            state_out       <= S_MAIN_GREEN;
        end else if (emergency_override) begin
            state           <= S_MAIN_GREEN;
            timer           <= 5'd0;
            main_light      <= LIGHT_GREEN;
            side_light      <= LIGHT_RED;
            ped_walk        <= 1'b0;
            state_out       <= S_MAIN_GREEN;
        end else begin
            // Latch pedestrian request until serviced in side green
            if (pedestrian_req) begin
                ped_req_latched <= 1'b1;
            end

            state_out <= state;

            case (state)
                S_MAIN_GREEN: begin
                    main_light <= LIGHT_GREEN;
                    side_light <= LIGHT_RED;
                    ped_walk   <= 1'b0;
                    if ((car_present_side || ped_req_latched || pedestrian_req) && (timer >= MAIN_GREEN_CYCLES - 1)) begin
                        state <= S_MAIN_YELLOW;
                        timer <= 5'd0;
                    end else if (car_present_side || ped_req_latched || pedestrian_req) begin
                        timer <= timer + 1'b1;
                    end else begin
                        timer <= 5'd0; // idle in main green
                    end
                end

                S_MAIN_YELLOW: begin
                    main_light <= LIGHT_YELLOW;
                    side_light <= LIGHT_RED;
                    ped_walk   <= 1'b0;
                    if (timer >= YELLOW_CYCLES - 1) begin
                        state <= S_ALL_RED1;
                        timer <= 5'd0;
                    end else begin
                        timer <= timer + 1'b1;
                    end
                end

                S_ALL_RED1: begin
                    main_light <= LIGHT_RED;
                    side_light <= LIGHT_RED;
                    ped_walk   <= 1'b0;
                    if (timer >= ALL_RED_CYCLES - 1) begin
                        state <= S_SIDE_GREEN;
                        timer <= 5'd0;
                    end else begin
                        timer <= timer + 1'b1;
                    end
                end

                S_SIDE_GREEN: begin
                    main_light <= LIGHT_RED;
                    side_light <= LIGHT_GREEN;
                    ped_walk   <= ped_req_latched;
                    if (timer >= SIDE_GREEN_CYCLES - 1) begin
                        state           <= S_SIDE_YELLOW;
                        timer           <= 5'd0;
                        ped_req_latched <= 1'b0; // serviced
                    end else begin
                        timer <= timer + 1'b1;
                    end
                end

                S_SIDE_YELLOW: begin
                    main_light <= LIGHT_RED;
                    side_light <= LIGHT_YELLOW;
                    ped_walk   <= 1'b0;
                    if (timer >= YELLOW_CYCLES - 1) begin
                        state <= S_ALL_RED2;
                        timer <= 5'd0;
                    end else begin
                        timer <= timer + 1'b1;
                    end
                end

                S_ALL_RED2: begin
                    main_light <= LIGHT_RED;
                    side_light <= LIGHT_RED;
                    ped_walk   <= 1'b0;
                    if (timer >= ALL_RED_CYCLES - 1) begin
                        state <= S_MAIN_GREEN;
                        timer <= 5'd0;
                    end else begin
                        timer <= timer + 1'b1;
                    end
                end

                default: begin
                    state <= S_MAIN_GREEN;
                    timer <= 5'd0;
                end
            endcase
        end
    end

endmodule
