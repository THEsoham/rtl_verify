"""Unit tests for ExperimentPipeline and contract enforcement."""

import pytest
from unittest.mock import MagicMock
from v2.src.pipeline import ExperimentPipeline, TrialResult
from v2.src.problems import Problem
from v2.src.verilog_sim import VerilogSimulator
from v2.src.mutator import VerilogMutator
from v2.src.llm_client import LLMResponse
from v2.src.metrics import compute_plumbing_metrics

SIM_PATH = r"d:\rtl-verification\tools\iverilog\app\bin\iverilog.exe"
VVP_PATH = r"d:\rtl-verification\tools\iverilog\app\bin\vvp.exe"


@pytest.fixture
def test_env():
    sim = VerilogSimulator(iverilog_path=SIM_PATH, vvp_path=VVP_PATH)
    mutator = VerilogMutator(sim)
    llm_client = MagicMock()
    pipeline = ExperimentPipeline(llm_client, sim, mutator)

    prob = Problem(
        problem_id="test_prob",
        category="combinational",
        prompt_spec="Implement an inverter module TopModule with input in, output out.",
        golden_rtl="module RefModule(input in, output out); assign out = ~in; endmodule",
        golden_tb="""`timescale 1ns/1ps
module tb;
    reg in; wire out;
    RefModule good1(.in(in), .out(out));
    TopModule top_module1(.in(in), .out(out));
    initial begin
        in = 0; #10;
        in = 1; #10;
        $display("Mismatches: 0 in 2 samples");
        $finish;
    end
endmodule""",
        top_module="TopModule",
        ref_module="RefModule",
    )
    return pipeline, llm_client, prob


def test_pipeline_valid_contract(test_env):
    pipeline, llm_client, prob = test_env

    # Mock RTL generation response
    rtl_resp = LLMResponse(
        call_id="call-1",
        model_id="gen-model",
        model_name="gen-model-name",
        provider="mock",
        prompt="prompt",
        raw_response="```verilog\nmodule TopModule(input in, output out); assign out = ~in; endmodule\n```",
        verilog_code="module TopModule(input in, output out); assign out = ~in; endmodule",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_sec=0.1,
    )

    tb_resp = LLMResponse(
        call_id="call-2",
        model_id="gen-model",
        model_name="gen-model-name",
        provider="mock",
        prompt="prompt",
        raw_response="""```verilog
`timescale 1ns/1ps
module tb;
    reg in; wire out;
    integer errors = 0;
    TopModule dut(.in(in), .out(out));
    initial begin
        in = 0; #10;
        if (out !== 1) errors = errors + 1;
        in = 1; #10;
        if (out !== 0) errors = errors + 1;
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end
endmodule
```""",
        verilog_code="""`timescale 1ns/1ps
module tb;
    reg in; wire out;
    integer errors = 0;
    TopModule dut(.in(in), .out(out));
    initial begin
        in = 0; #10;
        if (out !== 1) errors = errors + 1;
        in = 1; #10;
        if (out !== 0) errors = errors + 1;
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end
endmodule""",
        prompt_tokens=200,
        completion_tokens=80,
        total_tokens=280,
        latency_sec=0.1,
    )

    llm_client.generate.side_effect = [rtl_resp, tb_resp]

    res = pipeline.run_problem_condition(
        problem=prob,
        condition="A",
        gen_model_config={"id": "gen-model"},
        test_model_config={"id": "gen-model"},
    )

    assert res.design_compiled
    assert res.design_passed_golden_tb
    assert res.test_compiled
    assert res.test_contract_valid
    assert res.test_passed_golden_rtl
    assert not res.false_rejection
    assert res.generator_retries == 0
    assert res.tester_retries == 0


def test_pipeline_contract_violation_triggers_retry(test_env):
    pipeline, llm_client, prob = test_env

    rtl_resp = LLMResponse(
        call_id="call-1",
        model_id="gen-model",
        model_name="gen-model-name",
        provider="mock",
        prompt="prompt",
        raw_response="```verilog\nmodule TopModule(input in, output out); assign out = ~in; endmodule\n```",
        verilog_code="module TopModule(input in, output out); assign out = ~in; endmodule",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_sec=0.1,
    )

    # TB 1 violates contract (no *** TEST RESULT: PASS ***)
    tb_bad = LLMResponse(
        call_id="call-2",
        model_id="test-model",
        model_name="test-model-name",
        provider="mock",
        prompt="prompt",
        raw_response="""```verilog
`timescale 1ns/1ps
module tb;
    reg in; wire out;
    TopModule dut(.in(in), .out(out));
    initial begin
        in = 0; #10;
        $display("Passed without contract");
        $finish;
    end
endmodule
```""",
        verilog_code="""`timescale 1ns/1ps
module tb;
    reg in; wire out;
    TopModule dut(.in(in), .out(out));
    initial begin
        in = 0; #10;
        $display("Passed without contract");
        $finish;
    end
endmodule""",
        prompt_tokens=200,
        completion_tokens=80,
        total_tokens=280,
        latency_sec=0.1,
    )

    # TB 2 (on retry) complies with contract
    tb_good = LLMResponse(
        call_id="call-3",
        model_id="test-model",
        model_name="test-model-name",
        provider="mock",
        prompt="prompt",
        raw_response="""```verilog
`timescale 1ns/1ps
module tb;
    reg in; wire out;
    integer errors = 0;
    TopModule dut(.in(in), .out(out));
    initial begin
        in = 0; #10;
        if (out !== 1) errors = errors + 1;
        in = 1; #10;
        if (out !== 0) errors = errors + 1;
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end
endmodule
```""",
        verilog_code="""`timescale 1ns/1ps
module tb;
    reg in; wire out;
    integer errors = 0;
    TopModule dut(.in(in), .out(out));
    initial begin
        in = 0; #10;
        if (out !== 1) errors = errors + 1;
        in = 1; #10;
        if (out !== 0) errors = errors + 1;
        if (errors == 0) begin
            $display("*** TEST RESULT: PASS ***");
        end else begin
            $display("*** TEST RESULT: FAIL ***");
        end
        $finish;
    end
endmodule""",
        prompt_tokens=250,
        completion_tokens=90,
        total_tokens=340,
        latency_sec=0.1,
    )

    llm_client.generate.side_effect = [rtl_resp, tb_bad, tb_good]

    res = pipeline.run_problem_condition(
        problem=prob,
        condition="B",
        gen_model_config={"id": "gen-model"},
        test_model_config={"id": "test-model"},
    )

    # Succeeded on retry
    assert res.tester_retries == 1
    assert res.test_contract_valid
    assert res.test_passed_golden_rtl
    assert res.tester_retry_tokens == 340


def test_loud_failure_on_insufficient_mutants(test_env):
    pipeline, llm_client, prob = test_env

    # 3 mutants (< 8 required)
    from v2.src.mutator import Mutant
    few_mutants = [
        Mutant(mutant_id=f"M_{i}", operator="AOR", description="test", original_code="", mutated_code="", compiles=True, is_equivalent=False)
        for i in range(3)
    ]

    with pytest.raises(ValueError, match=r"\[HARD CHECK FAILED - A1\]"):
        pipeline.run_problem_condition(
            problem=prob,
            condition="A",
            gen_model_config={"id": "gen-model"},
            test_model_config={"id": "gen-model"},
            precomputed_mutants=few_mutants,
        )


def test_template_arm_execution(test_env):
    pipeline, llm_client, prob = test_env

    rtl_resp = LLMResponse(
        call_id="call-1",
        model_id="gen-model",
        model_name="gen-model-name",
        provider="mock",
        prompt="prompt",
        raw_response="```verilog\nmodule TopModule(input in, output out); assign out = ~in; endmodule\n```",
        verilog_code="module TopModule(input in, output out); assign out = ~in; endmodule",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_sec=0.1,
    )

    # In template arm, model writes ONLY stimulus
    stim_resp = LLMResponse(
        call_id="call-2",
        model_id="gen-model",
        model_name="gen-model-name",
        provider="mock",
        prompt="prompt",
        raw_response="""```verilog
in = 0; #10;
if (out !== 1) errors = errors + 1;
in = 1; #10;
if (out !== 0) errors = errors + 1;
```""",
        verilog_code="""in = 0; #10;
if (out !== 1) errors = errors + 1;
in = 1; #10;
if (out !== 0) errors = errors + 1;""",
        prompt_tokens=150,
        completion_tokens=60,
        total_tokens=210,
        latency_sec=0.1,
    )

    llm_client.generate.side_effect = [rtl_resp, stim_resp]

    res = pipeline.run_problem_condition(
        problem=prob,
        condition="A",
        gen_model_config={"id": "gen-model"},
        test_model_config={"id": "gen-model"},
        arm="template",
    )

    assert res.arm == "template"
    assert res.design_compiled
    assert res.test_compiled
    assert res.test_contract_valid
    assert res.test_passed_golden_rtl
    assert not res.test_vacuous

