"""Scenario analysis domain models.

ScenarioDefinition — a named set of factor shocks (equity %, rates bps, etc.)
ScenarioResult     — the portfolio impact of applying a scenario to an
                     optimization run
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ScenarioDefinition(BaseModel):
    """A named stress scenario expressed as factor shocks.

    shocks maps factor names to shock magnitudes:
      equity     — proportional return shock  (e.g. -0.30 = −30 %)
      duration   — parallel rate shift in years (e.g. 2.0 = +200 bps × 1-yr duration)
      inflation  — additional inflation rate   (e.g. 0.03 = +3 %)

    Factor names and shock magnitudes are open-ended; the Risk Analytics
    module maps them to per-asset return impacts using the asset's factor
    sensitivities.

    Example:
        ScenarioDefinition(
            name="Equity Crash -30%",
            shocks={"equity": -0.30},
        )
    """

    model_config = ConfigDict(frozen=True)

    scenario_id: UUID = Field(default_factory=uuid4)
    name: str
    shocks: dict[str, float]  # factor → shock magnitude
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def equity_crash(cls, equity_shock: float = -0.30) -> ScenarioDefinition:
        return cls(
            name=f"Equity Crash {equity_shock:.0%}",
            shocks={"equity": equity_shock},
        )

    @classmethod
    def rate_spike(cls, duration_shock: float = 2.0) -> ScenarioDefinition:
        """duration_shock in years; e.g. 2.0 ≈ +200 bps × 1-yr duration."""
        return cls(
            name=f"Rate Spike +{duration_shock:.0f}yr duration",
            shocks={"duration": duration_shock},
        )


class ScenarioResult(BaseModel):
    """Portfolio impact of a scenario applied to a specific optimization run.

    shocked_return  — estimated portfolio return under the scenario shocks
    shocked_vol     — re-estimated portfolio volatility under shocked covariance;
                      None when the covariance was not re-estimated (simple shock model)
    """

    model_config = ConfigDict(frozen=True)

    result_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    scenario_id: UUID
    shocked_return: float
    shocked_vol: float | None = Field(default=None, ge=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
