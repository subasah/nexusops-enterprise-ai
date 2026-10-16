"""
Unit Tests for Evaluation Harness and Flywheel Exporters.
"""

import pytest
from nexusops.evals.flywheel import PostTrainingFlywheel
from nexusops.evals.harness import EvaluationHarness


@pytest.mark.asyncio
async def test_evaluation_harness_single_scenario():
    harness = EvaluationHarness()
    summary = await harness.run_benchmark(scenario_id="BENCH-01")

    assert summary["total_scenarios"] == 1
    assert summary["passed_scenarios"] == 1
    assert summary["pass_rate_pct"] == 100.0
    assert summary["avg_grounding_score"] == 1.0


@pytest.mark.asyncio
async def test_flywheel_sft_and_dpo():
    flywheel = PostTrainingFlywheel()
    harness = EvaluationHarness(flywheel=flywheel)
    await harness.run_benchmark(scenario_id="BENCH-01")

    sft_data = flywheel.export_sft_dataset()
    assert len(sft_data) > 0
    assert "messages" in sft_data[0]

    dpo_pairs = flywheel.generate_dpo_pairs()
    assert len(dpo_pairs) >= 2
    assert "chosen" in dpo_pairs[0]
    assert "rejected" in dpo_pairs[0]
    assert "critique" in dpo_pairs[0]
