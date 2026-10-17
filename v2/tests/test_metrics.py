"""Unit tests for metrics and bootstrap statistics."""

from v2.src.metrics import compute_condition_metrics, bootstrap_ci


def test_bootstrap_ci():
    data = [0.2, 0.3, 0.25, 0.28, 0.22]
    low, high = bootstrap_ci(data, n_bootstraps=500, ci=0.95)
    assert 0.15 <= low <= 0.30
    assert 0.20 <= high <= 0.35
    assert low <= high


def test_condition_metrics_computation():
    records = [
        {
            "condition": "A_self_test",
            "design_compiled": True,
            "design_passed_golden_tb": True,
            "test_compiled": True,
            "test_passed_golden_rtl": True,
            "mutants_killed": 8,
            "mutants_total": 10,
            "natural_bug_tested": False,
            "natural_bug_escaped": False,
        },
        {
            "condition": "A_self_test",
            "design_compiled": True,
            "design_passed_golden_tb": False,  # naturally buggy design
            "test_compiled": True,
            "test_passed_golden_rtl": True,  # valid test
            "mutants_killed": 5,
            "mutants_total": 10,
            "natural_bug_tested": True,
            "natural_bug_escaped": True,  # bug escaped!
        },
    ]

    summary = compute_condition_metrics(records)
    assert summary.total_designs == 2
    assert summary.compiled_designs == 2
    assert summary.correct_designs == 1
    assert summary.design_pass_rate == 0.5
    assert summary.false_rejection_rate == 0.0  # both tests passed golden RTL
    assert summary.mutants_killed == 13
    assert summary.mutants_tested == 20
    assert summary.mutation_score == 0.65
    assert summary.escape_rate == 1.0  # 1 bug tested, 1 escaped
