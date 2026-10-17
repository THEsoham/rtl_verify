# UNREVIEWED Golden Reference Designs and Testbenches

> **STATUS:** UNREVIEWED — Awaiting user review and manual testing before any experimental execution.
> Per Rule 3 of the approved plan, **no experiments are to be run on these modules** until explicitly confirmed by the user.

## Modules Included

1. **`alu_8bit/`**
   - File: `ref.v` — Synthesizable 8-bit registered ALU with 8 opcodes, flags (`zero`, `carry_out`, `overflow`), and 1-cycle latency pipeline.
   - File: `tb.v` — Self-checking testbench adhering to the fixed testbench contract (`*** TEST RESULT: PASS ***`, `$finish`).

2. **`fifo_sync/`**
   - File: `ref.v` — Parameterized synchronous FIFO buffer (depth 16, width 8) with cycle-accurate flags (`full`, `empty`, `almost_full`, `almost_empty`, `count`) and pointer protections on overflow/underflow.
   - File: `tb.v` — Self-checking testbench verifying FIFO ordering, threshold transitions, full/empty limits, and simultaneous read/write.

3. **`traffic_light/`**
   - File: `ref.v` — Intersection traffic light controller FSM with programmable timing, pedestrian servicing, emergency vehicle override preemption, and mutual exclusion safety guarantees.
   - File: `tb.v` — Self-checking testbench asserting safety invariants, sequence timing, pedestrian walk cycle latching, and immediate emergency preemption.
