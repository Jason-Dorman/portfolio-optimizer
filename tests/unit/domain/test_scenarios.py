"""Tests for src/domain/models/scenarios.py."""

import pytest
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.scenarios import ScenarioDefinition, ScenarioResult


# --- ScenarioDefinition ---

def test_scenario_definition_construction():
    s = ScenarioDefinition(name="Equity Crash -30%", shocks={"equity": -0.30})
    assert s.name == "Equity Crash -30%"


def test_scenario_definition_shocks_stored():
    s = ScenarioDefinition(name="Rate Spike", shocks={"duration": 2.0})
    assert s.shocks["duration"] == 2.0


def test_scenario_definition_multiple_shocks():
    s = ScenarioDefinition(
        name="Stagflation",
        shocks={"equity": -0.20, "duration": 1.5, "inflation": 0.05},
    )
    assert len(s.shocks) == 3


def test_scenario_definition_id_auto_generated():
    s = ScenarioDefinition(name="Test", shocks={"equity": -0.10})
    assert s.scenario_id is not None


def test_scenario_definition_equity_crash_factory_name():
    s = ScenarioDefinition.equity_crash(equity_shock=-0.30)
    assert "-30%" in s.name


def test_scenario_definition_equity_crash_factory_shock_value():
    s = ScenarioDefinition.equity_crash(equity_shock=-0.30)
    assert s.shocks["equity"] == -0.30


def test_scenario_definition_equity_crash_custom_shock():
    s = ScenarioDefinition.equity_crash(equity_shock=-0.50)
    assert s.shocks["equity"] == -0.50


def test_scenario_definition_rate_spike_factory_name():
    s = ScenarioDefinition.rate_spike(duration_shock=2.0)
    assert "2" in s.name


def test_scenario_definition_rate_spike_factory_shock_value():
    s = ScenarioDefinition.rate_spike(duration_shock=2.0)
    assert s.shocks["duration"] == 2.0


# --- ScenarioResult ---

def test_scenario_result_construction():
    r = ScenarioResult(
        run_id=uuid4(),
        scenario_id=uuid4(),
        shocked_return=-0.18,
    )
    assert r.shocked_return == -0.18


def test_scenario_result_id_auto_generated():
    r = ScenarioResult(run_id=uuid4(), scenario_id=uuid4(), shocked_return=-0.10)
    assert r.result_id is not None


def test_scenario_result_shocked_vol_defaults_none():
    r = ScenarioResult(run_id=uuid4(), scenario_id=uuid4(), shocked_return=-0.10)
    assert r.shocked_vol is None


def test_scenario_result_with_shocked_vol():
    r = ScenarioResult(
        run_id=uuid4(),
        scenario_id=uuid4(),
        shocked_return=-0.18,
        shocked_vol=0.35,
    )
    assert r.shocked_vol == 0.35


def test_scenario_result_shocked_vol_negative_raises():
    with pytest.raises(ValidationError):
        ScenarioResult(
            run_id=uuid4(),
            scenario_id=uuid4(),
            shocked_return=-0.18,
            shocked_vol=-0.10,
        )
