"""Risk analytics ORM models: scenario_definitions, scenario_results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Double, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base


class ScenarioDefinition(Base):
    """Reusable stress scenario with factor shocks.

    shocks: e.g. {"equity": -0.30, "duration": 2.0, "inflation": 0.03}
    """

    __tablename__ = "scenario_definitions"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    shocks: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    results: Mapped[list["ScenarioResult"]] = relationship(back_populates="scenario")


class ScenarioResult(Base):
    """Outcome of applying a stress scenario to an optimization run's portfolio."""

    __tablename__ = "scenario_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("optimization_runs.run_id"), nullable=False
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenario_definitions.scenario_id"), nullable=False
    )
    shocked_return: Mapped[float] = mapped_column(Double, nullable=False)
    shocked_vol: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["OptimizationRun"] = relationship(back_populates="scenario_results")
    scenario: Mapped["ScenarioDefinition"] = relationship(back_populates="results")
