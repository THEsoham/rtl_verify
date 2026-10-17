"""Unit tests for ProblemLoader."""

import os
import tempfile
from v2.src.problems import Problem, classify_problem, ProblemLoader


def test_classify_problem():
    seq_code = "always @(posedge clk) q <= d;"
    comb_code = "assign y = a & b;"
    assert classify_problem(seq_code, "D-flipflop") == "sequential"
    assert classify_problem(comb_code, "AND gate") == "combinational"


def test_problem_loader_caching():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ProblemLoader(golden_dir=tmpdir)
        # Prepopulate cache file
        cache_file = os.path.join(tmpdir, "verilogeval_all.json")
        sample_probs = [
            {
                "problem_id": "test_comb",
                "category": "combinational",
                "prompt_spec": "Inverter",
                "golden_rtl": "module RefModule(input a, output y); assign y = ~a; endmodule",
                "golden_tb": "module tb; endmodule",
                "top_module": "TopModule",
                "ref_module": "RefModule",
            },
            {
                "problem_id": "test_seq",
                "category": "sequential",
                "prompt_spec": "Counter",
                "golden_rtl": "module RefModule(input clk, output reg [3:0] q); always @(posedge clk) q <= q + 1; endmodule",
                "golden_tb": "module tb; endmodule",
                "top_module": "TopModule",
                "ref_module": "RefModule",
            },
        ]
        import json
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(sample_probs, f)

        loaded = loader.load_all()
        assert len(loaded) == 2
        assert loaded[0].problem_id == "test_comb"
        assert loaded[1].category == "sequential"

        pilot = loader.select_pilot_set(count=2)
        assert len(pilot) == 2
        cats = {p.category for p in pilot}
        assert "combinational" in cats
        assert "sequential" in cats
