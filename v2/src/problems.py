"""Problem set loader for RTL verification.

Loads and structures problems from VerilogEval v2 and legacy benchmarks.
Classifies problems (combinational vs. sequential), extracts golden reference RTL,
and golden self-checking testbenches.
"""

from dataclasses import dataclass
import json
import os
import re
from typing import Dict, List, Optional
import datasets


@dataclass
class Problem:
    """Represents a hardware verification benchmark task."""
    problem_id: str
    category: str  # "combinational" or "sequential"
    prompt_spec: str
    golden_rtl: str
    golden_tb: str
    top_module: str = "TopModule"
    ref_module: str = "RefModule"

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "category": self.category,
            "prompt_spec": self.prompt_spec,
            "golden_rtl": self.golden_rtl,
            "golden_tb": self.golden_tb,
            "top_module": self.top_module,
            "ref_module": self.ref_module,
        }


def classify_problem(ref_code: str, prompt_text: str) -> str:
    """Classify problem as sequential or combinational based on clocking and flip-flops."""
    text = (ref_code + " " + prompt_text).lower()
    if re.search(r"posedge\s+clk|negedge\s+clk|always\s*@\s*\(\s*posedge", text) or "clock" in prompt_text.lower():
        return "sequential"
    return "combinational"


class ProblemLoader:
    """Loads benchmark problems from VerilogEval or local cache."""

    def __init__(
        self,
        dataset_name: str = "dakies/nvlabs-verilogeval-v2-spec-to-rtl",
        golden_dir: str = "d:/rtl-verification/v2/golden",
    ):
        self.dataset_name = dataset_name
        self.golden_dir = os.path.normpath(golden_dir)
        os.makedirs(self.golden_dir, exist_ok=True)

    def load_all(self, split: str = "test") -> List[Problem]:
        """Fetch all problems from HuggingFace dataset or local cache."""
        cache_file = os.path.join(self.golden_dir, "verilogeval_all.json")
        if os.path.isfile(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Problem(**p) for p in data]

        ds = datasets.load_dataset(self.dataset_name, split=split)
        problems: List[Problem] = []

        for row in ds:
            prob_id = row["problem_id"]
            prompt = row["prompt"]
            ref = row["ref"]
            test = row["test"]

            cat = classify_problem(ref, prompt)

            prob = Problem(
                problem_id=prob_id,
                category=cat,
                prompt_spec=prompt,
                golden_rtl=ref,
                golden_tb=test,
                top_module="TopModule",
                ref_module="RefModule",
            )
            problems.append(prob)

            # Persist individual golden files for post-hoc analysis
            prob_dir = os.path.join(self.golden_dir, prob_id)
            os.makedirs(prob_dir, exist_ok=True)
            with open(os.path.join(prob_dir, "ref.v"), "w", encoding="utf-8") as f:
                f.write(ref)
            with open(os.path.join(prob_dir, "tb.v"), "w", encoding="utf-8") as f:
                f.write(test)
            with open(os.path.join(prob_dir, "spec.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

        # Cache combined list
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in problems], f, indent=2)

        return problems

    def select_pilot_set(self, count: int = 5) -> List[Problem]:
        """Select pilot benchmark problems with real internal logic and >= 8 non-equivalent mutants.
        
        Replaces trivial 1-line circuits (Prob001_zero, Prob002_m2014_q4i, Prob031_dff, Prob034_dff8)
        with sequential problems featuring state registers, counters, branching, and wrap conditions.
        """
        all_probs = {p.problem_id: p for p in self.load_all()}
        
        # Priority list of verified sequential problems with >= 8 non-equivalent mutants
        verified_seq_ids = [
            "Prob035_count1to10",
            "Prob040_count10",
            "Prob037_review2015_count1k",
            "Prob067_countslow",
            "Prob080_timer",
            "Prob068_countbcd",
            "Prob073_dff16e",
            "Prob038_count15",
        ]
        
        selected: List[Problem] = []
        for pid in verified_seq_ids:
            if pid in all_probs:
                selected.append(all_probs[pid])
                if len(selected) >= count:
                    break

        # If more problems requested, add other non-trivial problems
        if len(selected) < count:
            unusable = {"Prob001_zero", "Prob002_m2014_q4i", "Prob031_dff", "Prob034_dff8", "Prob046_dff8p"}
            for p in self.load_all():
                if p.problem_id not in unusable and p not in selected:
                    selected.append(p)
                    if len(selected) >= count:
                        break

        return selected
