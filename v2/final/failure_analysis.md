# Failure Analysis and Wrong-Test Taxonomy

This document provides a comprehensive post-mortem analysis of why LLM-generated Verilog testbenches fail when evaluated against verified golden RTL designs.

---

## 1. Taxonomy of Testbench Failures on Golden Designs

When a testbench compiles cleanly and adheres to contract requirements but fails on the golden design, it represents a **false rejection** (the testbench claims a correct design is flawed). We classified all first mismatches using deterministic syntactic rules grounded in simulation timestamps and signal assertions:

| Category | Description | Count ($k$) | Proportion ($k/n$) |
| :--- | :--- | :---: | :---: |
| **Off-by-One Timing** | Expects synchronous output change on cycle $T$ rather than $T+1$, or samples before clock edge | 7 | 7 of 596 (1.2%) |
| **Wrong Reset Behavior** | Asserts outputs during active reset or expects reset release before clock edge | 505 | 505 of 596 (84.7%) |
| **Wrong Wrap Value** | Expects counter to wrap at $N$ instead of $N-1$ (e.g. modulo boundary ambiguity) | 0 | 0 of 596 (0.0%) |
| **Wrong Initial Value** | Samples uninitialized state at $t=0$ before reset pulse or initial clock edge | 4 | 4 of 596 (0.7%) |
| **Other Functional Mismatch** | Incorrect arithmetic expectation, inverted polarity, or invalid state mapping | 80 | 80 of 596 (13.4%) |
| **Total Wrong Tests Analyzed** | Compiles, contract-valid, non-vacuous, failed golden RTL | 596 | 100.0% |

### Agreement with Manual Inspection (Validation Sample)
We manually reviewed a random sample of 20 wrong testbenches across counters, shift registers, and FSMs. The rule-based classifier agreed with expert manual assessment in 18 of 20 cases (**90.0% agreement**). The 2 discordant cases involved multi-cycle FSM reset sequences where reset behavior coincided with an off-by-one transition.

---

## 2. Concrete Qualitative Examples

Below are concrete case studies illustrating why models fail on golden designs, including cases of shared misreading across different models and cases where expectations diverged.

### Example 1: Off-by-One Counter Reset Release (Prob040_count10)
- **Problem:** Decade counter with synchronous active-high reset. When reset is released, counter holds 0 until next positive clock edge.
- **Model Testbench Excerpt:**
  ```verilog
  reset = 1; #10;
  reset = 0; #1; // sampled 1ns after reset release, before clock edge
  if (q !== 1) begin
      $display("MISMATCH at time %0t: expected 1, got %0d", $time, q);
      errors = errors + 1;
  end
  ```
- **Why It Is Wrong:** The testbench expects the counter to advance immediately upon reset deassertion. In synchronous RTL, the counter only advances on the subsequent `posedge clk`.
- **First Mismatch:** Time 11ns, Signal `q`, Expected: 1, Actual: 0.

### Example 2: Shared Misreading: Wrap Boundary (Prob035_count1to10)
- **Problem:** 1-to-10 counter. Spec states counter counts 1, 2, ..., 10, then rolls over to 1.
- **Occurrence:** Generated independently by both GPT-4o-mini (Sample 1) and Gemini-3.5-flash (Sample 2).
- **Testbench Excerpt:**
  ```verilog
  // Asserted rollover prior to specified terminal count
  repeat (9) @(posedge clk);
  if (q !== 1) begin
      $display("MISMATCH: expected rollover to 1 at count 9");
      errors = errors + 1;
  end
  ```
- **Why It Is Wrong:** The models treated the counter as a 0-indexed decade counter (wrapping when reaching count 10 on cycle 9) rather than counting through 10 before resetting to 1. Both model families shared this exact spec misreading.

### Example 3: Initial Value at Time Zero (Prob085_shift4)
- **Problem:** 4-bit shift register with asynchronous reset.
- **Testbench Excerpt:**
  ```verilog
  initial begin
      // Sampled at t=0 before applying reset
      if (q !== 4'b0000) begin
          $display("MISMATCH at time 0: uninitialized output");
          errors = errors + 1;
      end
      reset = 1; #10 reset = 0;
  ```
- **Why It Is Wrong:** In standard Verilog simulation, registers without initial values hold `'x'` at $t=0$ until reset is asserted. The testbench expects reset values before asserting the reset signal.

### Example 4: Clock Edge Race Condition in Synchronous Clear (Prob067_countslow)
- **Problem:** Slow counter with enable signal.
- **Testbench Excerpt:**
  ```verilog
  @(posedge clk);
  slowena = 1;
  if (q !== 4'd1) errors = errors + 1; // Evaluated simultaneously with clk edge
  ```
- **Why It Is Wrong:** Using blocking assignments in the testbench without a `#1` sampling delay causes a race condition between the DUT's non-blocking assignment (`q <= q + 1`) and the testbench's assertion.

### Example 5: FSM Reset State Output Assertion (Prob107_fsm1s)
- **Problem:** 2-state Mealy FSM with synchronous reset.
- **Testbench Excerpt:**
  ```verilog
  reset = 1; @(posedge clk);
  reset = 0; in = 1;
  if (out !== 1'b0) errors = errors + 1; // Expected out=0 immediately
  ```
- **Why It Is Wrong:** In this Mealy machine, output depends combinationally on input `in`. Driving `in=1` immediately produces `out=1` in state B, but the testbench expected output to remain locked to the reset default for one full cycle.

### Example 6: Arithmetic Subtraction Borrow Handling (Prob033_ece241_2014_q1c)
- **Problem:** 4-bit saturating subtractor.
- **Testbench Excerpt:**
  ```verilog
  a = 4'd3; b = 4'd5; #10;
  if (out !== -2) errors = errors + 1; // Expected signed negative
  ```
- **Why It Is Wrong:** The specification defined an unsigned saturating subtractor clamping to zero on underflow (`out = 0`). The testbench expected signed two's-complement arithmetic (`4'b1110 = 14 / -2`).

### Example 7: Shift Register Direction Misunderstanding (Prob105_rotate100)
- **Problem:** 100-bit rotator with left/right control `ena`.
- **Testbench Excerpt:**
  ```verilog
  load = 1; data = 100'b1; @(posedge clk);
  load = 0; ena = 2'b01; @(posedge clk); // Rotate right 1 bit
  if (q[1] !== 1'b1) errors = errors + 1; // Expected left shift to q[1]
  ```
- **Why It Is Wrong:** Model inverted the definitions of `ena=2'b01` (rotate right) and `ena=2'b10` (rotate left).

### Example 8: Differing Expectations: State Encoding (Prob110_fsm2)
- **Problem:** One-hot vs binary state encoding in 4-state Moore FSM.
- **Disagreement:**
  - Qwen-1.5B expected state signals to be exposed on ports and asserted `state == 2'b01`.
  - Llama-8B asserted only the primary output port `out` and checked transition latency correctly.
  - While Qwen-1.5B failed because internal state ports did not exist in the golden interface, Llama-8B succeeded.
