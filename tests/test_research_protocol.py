import importlib.util
from pathlib import Path

import pytest

from biosbom_agentkg.multiagent.evaluation import FaultProvider


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "benchmarks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_source_fixture_contracts(tmp_path):
    result = load_script("run_public_corpus").run(tmp_path / "public", repeats=1)
    assert result["cases"] == 72
    assert result["passed"] == 72
    assert result["observed"]["no_candidate"] == 24
    assert result["observed"]["range_version"] == 8
    assert result["observed"]["ambiguous"] == 24
    assert result["latency_all_passed"]


def test_live_budget_guard_does_not_dispatch(tmp_path, case):
    class NeverCall(FaultProvider):
        def complete(self, *args, **kwargs):
            pytest.fail("provider must not be called")

    with pytest.raises(ValueError, match="authorization"):
        load_script("run_live_models").evaluate_live(
            [case], tmp_path / "live", NeverCall(), max_total_calls=11
        )
    assert not (tmp_path / "live").exists()


def test_live_protocol_using_mock_transport(tmp_path, case):
    rows = load_script("run_live_models").evaluate_live(
        [case], tmp_path / "mock", FaultProvider(), max_total_calls=12
    )
    assert len(rows) == 2
    assert all(r["verified"] for r in rows)
    assert {r["architecture"] for r in rows} == {"single_agent", "multi_agent"}
    assert sorted(r["calls"] for r in rows) == [1, 2]


def test_live_protocol_refuses_unpaired_role_models(tmp_path, case):
    provider = FaultProvider()
    provider.models = {"context": "one-model", "single": "other-model", "triage": "one-model"}
    with pytest.raises(ValueError, match="same model"):
        load_script("run_live_models").evaluate_live([case], tmp_path / "bad", provider)
