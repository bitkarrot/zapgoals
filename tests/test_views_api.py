import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from lnbits.core.models import WalletTypeInfo

from .. import views_api
from ..models import Goal, Period, SweepError, WalletMode


def partially_funded_goal() -> Goal:
    now = datetime.now(timezone.utc)
    return Goal(
        id="goal123",
        wallet="wallet123",
        title="Partially funded goal",
        description_above="",
        description_below="",
        goal_amount=1000,
        current_amount=250,
        target_date=now + timedelta(days=30),
        wallet_mode=WalletMode.vanilla,
        font_name="sans-serif",
        font_weight=400,
        nostr_pubkey=None,
        lightning_address_username=None,
        created_at=now,
        updated_at=now,
        recurring=False,
        show_period_badge=True,
        recurrence_unit=None,
        recurrence_interval=1,
        recurrence_day_of_month=None,
        target_wallet_id=None,
        rollover_mode="counts_as_progress",
        sweep_mode="target_amount",
    )


def recurring_goal() -> Goal:
    now = datetime.now(timezone.utc)
    return Goal(
        id="recur123",
        wallet="wallet123",
        title="Monthly Goal",
        description_above="",
        description_below="",
        goal_amount=10000,
        current_amount=10200,
        target_date=now - timedelta(days=1),
        wallet_mode=WalletMode.vanilla,
        font_name="sans-serif",
        font_weight=400,
        nostr_pubkey=None,
        lightning_address_username=None,
        created_at=now - timedelta(days=31),
        updated_at=now - timedelta(days=31),
        recurring=True,
        show_period_badge=True,
        recurrence_unit="month",
        recurrence_interval=1,
        recurrence_day_of_month=None,
        target_wallet_id="target-wallet-456",
        rollover_mode="counts_as_progress",
        sweep_mode="target_amount",
        period_index=0,
        period_start=now - timedelta(days=31),
        last_swept_at=None,
        sweeping=False,
    )


def make_period(**overrides) -> Period:
    now = datetime.now(timezone.utc)
    defaults: dict[str, object] = {
        "id": "period123",
        "goal_id": "recur123",
        "period_index": 0,
        "period_start": now - timedelta(days=31),
        "period_end": now - timedelta(days=1),
        "zapped_total": 10200,
        "moved_to_target": 10000,
        "rollover": 200,
        "sweep_mode": "target_amount",
        "swept_at": now,
    }
    defaults.update(overrides)
    return Period(**defaults)  # type: ignore[arg-type]


def wallet_info(wallet_id: str) -> WalletTypeInfo:
    return cast(WalletTypeInfo, SimpleNamespace(wallet=SimpleNamespace(id=wallet_id)))


def test_partially_funded_goal_can_be_deleted(monkeypatch):
    goal = partially_funded_goal()
    delete = AsyncMock()
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(views_api, "delete_goal_and_contributions", delete)

    asyncio.run(views_api.api_delete_goal(goal.id, wallet_info(goal.wallet)))

    delete.assert_awaited_once_with(goal.id)


def test_goal_delete_still_checks_wallet_ownership(monkeypatch):
    goal = partially_funded_goal()
    delete = AsyncMock()
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(views_api, "delete_goal_and_contributions", delete)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(views_api.api_delete_goal(goal.id, wallet_info("other-wallet")))

    assert exc.value.status_code == 403
    delete.assert_not_awaited()


def test_sweep_goal_returns_period(monkeypatch):
    goal = recurring_goal()
    period = make_period()
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    sweep = AsyncMock(return_value=period)
    monkeypatch.setattr(views_api, "sweep_recurring_goal", sweep)

    result = asyncio.run(views_api.api_sweep_goal(goal.id, wallet_info(goal.wallet)))

    assert result == period
    sweep.assert_awaited_once_with(goal.id)


def test_sweep_goal_checks_ownership(monkeypatch):
    goal = recurring_goal()
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    sweep = AsyncMock()
    monkeypatch.setattr(views_api, "sweep_recurring_goal", sweep)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(views_api.api_sweep_goal(goal.id, wallet_info("other-wallet")))

    assert exc.value.status_code == 403
    sweep.assert_not_awaited()


def test_sweep_goal_not_found(monkeypatch):
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=None))
    monkeypatch.setattr(views_api, "sweep_recurring_goal", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(views_api.api_sweep_goal("missing", wallet_info("wallet123")))

    assert exc.value.status_code == 404


def test_sweep_goal_sweep_error_returns_conflict(monkeypatch):
    goal = recurring_goal()
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(
        views_api,
        "sweep_recurring_goal",
        AsyncMock(side_effect=SweepError("not due")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(views_api.api_sweep_goal(goal.id, wallet_info(goal.wallet)))

    assert exc.value.status_code == 409
    assert "not due" in exc.value.detail


def test_sweep_due_sweeps_all_due_goals(monkeypatch):
    goal = recurring_goal()
    period = make_period()
    get_due = AsyncMock(return_value=[goal])
    monkeypatch.setattr(views_api, "get_due_recurring_goals", get_due)
    monkeypatch.setattr(
        views_api, "sweep_recurring_goal", AsyncMock(return_value=period)
    )

    results = asyncio.run(views_api.api_sweep_due(wallet_info(goal.wallet)))

    assert len(results) == 1
    assert results[0] == period
    get_due.assert_awaited_once_with(goal.wallet)


def test_sweep_due_continues_on_failure(monkeypatch):
    goal = recurring_goal()
    monkeypatch.setattr(
        views_api, "get_due_recurring_goals", AsyncMock(return_value=[goal])
    )
    sweep = AsyncMock(side_effect=SweepError("insufficient balance"))
    monkeypatch.setattr(views_api, "sweep_recurring_goal", sweep)

    results = asyncio.run(views_api.api_sweep_due(wallet_info(goal.wallet)))

    assert results == []
    sweep.assert_awaited_once_with(goal.id)


def test_goal_periods_returns_ledger(monkeypatch):
    goal = recurring_goal()
    periods = [make_period(period_index=0), make_period(id="p1", period_index=1)]
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    get_periods = AsyncMock(return_value=periods)
    monkeypatch.setattr(views_api, "get_periods", get_periods)

    result = asyncio.run(views_api.api_goal_periods(goal.id, wallet_info(goal.wallet)))

    assert result == periods
    get_periods.assert_awaited_once_with(goal.id)


def test_goal_periods_checks_ownership(monkeypatch):
    goal = recurring_goal()
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    get_periods = AsyncMock()
    monkeypatch.setattr(views_api, "get_periods", get_periods)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(views_api.api_goal_periods(goal.id, wallet_info("other-wallet")))

    assert exc.value.status_code == 403
    get_periods.assert_not_awaited()
