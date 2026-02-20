"""Tests for src/domain/models/market_data.py."""

import pytest
from datetime import date
from pydantic import ValidationError
from uuid import uuid4

from src.domain.models.market_data import PriceBar, ReturnPoint
from src.domain.models.enums import Frequency, ReturnType


# --- PriceBar ---

def test_price_bar_construction():
    bar = PriceBar(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.DAILY,
        adj_close=150.25,
    )
    assert bar.adj_close == 150.25


def test_price_bar_adj_close_zero_raises():
    with pytest.raises(ValidationError):
        PriceBar(
            asset_id=uuid4(),
            bar_date=date(2024, 1, 15),
            frequency=Frequency.DAILY,
            adj_close=0.0,
        )


def test_price_bar_adj_close_negative_raises():
    with pytest.raises(ValidationError):
        PriceBar(
            asset_id=uuid4(),
            bar_date=date(2024, 1, 15),
            frequency=Frequency.DAILY,
            adj_close=-5.0,
        )


def test_price_bar_close_defaults_to_none():
    bar = PriceBar(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.DAILY,
        adj_close=150.25,
    )
    assert bar.close is None


def test_price_bar_volume_defaults_to_none():
    bar = PriceBar(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.DAILY,
        adj_close=150.25,
    )
    assert bar.volume is None


def test_price_bar_close_set_when_provided():
    bar = PriceBar(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.DAILY,
        adj_close=150.25,
        close=151.00,
    )
    assert bar.close == 151.00


def test_price_bar_volume_set_when_provided():
    bar = PriceBar(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.DAILY,
        adj_close=150.25,
        volume=1_000_000,
    )
    assert bar.volume == 1_000_000


def test_price_bar_volume_negative_raises():
    with pytest.raises(ValidationError):
        PriceBar(
            asset_id=uuid4(),
            bar_date=date(2024, 1, 15),
            frequency=Frequency.DAILY,
            adj_close=150.25,
            volume=-1,
        )


def test_price_bar_is_frozen():
    bar = PriceBar(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.DAILY,
        adj_close=150.25,
    )
    with pytest.raises(ValidationError):
        bar.adj_close = 999.0  # type: ignore[misc]


# --- ReturnPoint ---

def test_return_point_construction():
    pt = ReturnPoint(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.MONTHLY,
        return_type=ReturnType.SIMPLE,
        ret=0.0312,
    )
    assert pt.ret == 0.0312


def test_return_point_negative_return_allowed():
    pt = ReturnPoint(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.MONTHLY,
        return_type=ReturnType.LOG,
        ret=-0.05,
    )
    assert pt.ret == -0.05


def test_return_point_is_frozen():
    pt = ReturnPoint(
        asset_id=uuid4(),
        bar_date=date(2024, 1, 15),
        frequency=Frequency.DAILY,
        return_type=ReturnType.SIMPLE,
        ret=0.01,
    )
    with pytest.raises(ValidationError):
        pt.ret = 0.99  # type: ignore[misc]
