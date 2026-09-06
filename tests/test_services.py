import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from lnbits.core.models import Payment
from pynostr.event import Event
from pynostr.key import PrivateKey

from .. import services
from ..models import Goal, GoalData, WalletMode


def make_goal(**overrides):
    values = {
        "id": "goal123",
        "wallet": "wallet123",
        "title": "June Zap Goal",
        "description_above": "Help us reach the target.",
        "description_below": "Thank you.",
        "goal_amount": 100_000,
        "target_date": datetime.now(timezone.utc) + timedelta(days=30),
        "current_amount": 85_127,
        "wallet_mode": WalletMode.all,
        "background_color": "#202B3B",
        "text_color": "#FFFFFF",
        "progress_color": "#FF7900",
        "remainder_color": "#20D4D8",
        "font_family": "sans-serif",
        "font_name": "Arial, sans-serif",
        "font_weight": 700,
        "nostr_pubkey": None,
        "lightning_address_username": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return Goal(**values)


def test_public_goal_contains_required_fields_without_wallet_secrets(monkeypatch):
    goal = make_goal(lightning_address_username="june")
    request = SimpleNamespace(
        url=SimpleNamespace(netloc="example.com"),
        url_for=lambda _name, **_kwargs: "https://example.com/zapgoals/api/v1/lnurl/goal123",
    )

    payload = services.public_goal(goal, cast(Request, request))
    data = payload.dict()

    assert data["goal_amount"] == 100_000
    assert data["current_amount"] == 85_127
    assert data["target_date"] == goal.target_date
    assert data["lnurl_url"].endswith("/goal123")
    assert data["font_name"] == "Arial, sans-serif"
    assert data["font_weight"] == 700
    assert data["lightning_address"] is None
    assert "wallet" not in data
    assert "key" not in data

    monkeypatch.setattr(services, "lightning_address_enabled", True)
    enabled = services.public_goal(goal, cast(Request, request))
    assert enabled.lightning_address == "june@example.com"


def test_create_goal_invoice_tags_and_records_contribution(monkeypatch):
    payment = SimpleNamespace(
        payment_hash="ab" * 32,
        payment_request="lnbc1invoice",
        bolt11="lnbc1invoice",
    )
    create_payment = AsyncMock(return_value=payment)
    create_contribution = AsyncMock()
    purge_contributions = AsyncMock()
    monkeypatch.setattr(services, "create_payment_request", create_payment)
    monkeypatch.setattr(services, "create_contribution", create_contribution)
    monkeypatch.setattr(
        services, "purge_expired_unpaid_contributions", purge_contributions
    )

    result = asyncio.run(
        services.create_goal_invoice(
            make_goal(), 21, "invoice", extra={"comment": "great goal"}
        )
    )

    payment_call = create_payment.await_args
    assert payment_call is not None
    invoice_data = payment_call.args[1]
    assert invoice_data.amount == 21
    assert invoice_data.expiry == services.INVOICE_EXPIRY_SECONDS
    purge_contributions.assert_awaited_once_with(
        "goal123", services.INVOICE_EXPIRY_SECONDS
    )
    assert invoice_data.extra == {
        "tag": "zapgoals",
        "goal_id": "goal123",
        "source": "invoice",
        "comment": "great goal",
    }
    create_contribution.assert_awaited_once_with("ab" * 32, "goal123", 21, "invoice")
    assert result.payment_request == "lnbc1invoice"


def signed_zap_request(recipient_pubkey: str, amount_msat: int) -> str:
    sender = PrivateKey()
    event = Event(
        kind=9734,
        content="Zap!",
        tags=[
            ["relays", "wss://relay.example.com"],
            ["amount", str(amount_msat)],
            ["p", recipient_pubkey],
        ],
    )
    event.sign(sender.hex())
    return json.dumps(event.to_dict())


def test_validate_zap_request_signature_recipient_and_amount():
    recipient = PrivateKey().public_key.hex()
    goal = make_goal(nostr_pubkey=recipient)
    raw = signed_zap_request(recipient, 21_000)

    event, relays = services.validate_zap_request(raw, goal, 21_000)

    assert event.kind == 9734
    assert relays == ["wss://relay.example.com"]

    with pytest.raises(ValueError, match="amount"):
        services.validate_zap_request(raw, goal, 22_000)

    other_goal = make_goal(nostr_pubkey=PrivateKey().public_key.hex())
    with pytest.raises(ValueError, match="recipient"):
        services.validate_zap_request(raw, other_goal, 21_000)


def test_settled_payment_broadcasts_goal_invalidation(monkeypatch):
    goal = make_goal(current_amount=85_148)
    settle = AsyncMock(return_value=goal)
    send = AsyncMock()
    monkeypatch.setattr(services, "settle_contribution", settle)
    monkeypatch.setattr(services.websocket_manager, "send", send)
    payment = SimpleNamespace(payment_hash="cd" * 32, extra={"source": "invoice"})

    result = asyncio.run(services.process_settled_payment(cast(Payment, payment)))

    assert result == goal
    send.assert_awaited_once()
    send_call = send.await_args
    assert send_call is not None
    item_id, raw = send_call.args
    assert item_id == goal.id
    assert json.loads(raw)["current_amount"] == 85_148


def test_goal_data_accepts_long_time_periods():
    goal = GoalData(
        title="Long-term goal",
        description_above="",
        description_below="",
        goal_amount=100,
        target_date=datetime.now(timezone.utc) + timedelta(days=3650),
        wallet_mode=WalletMode.vanilla,
        font_name="sans-serif",
        font_weight=400,
        nostr_pubkey=None,
        lightning_address_username=None,
    )
    assert goal.target_date.tzinfo is not None


def test_next_period_end_advances_by_days():
    end = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
    assert services.next_period_end(end, "day", 7) == datetime(
        2026, 1, 22, 0, 0, tzinfo=timezone.utc
    )


def test_next_period_end_advances_by_weeks():
    end = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert services.next_period_end(end, "week", 2) == datetime(
        2026, 1, 15, 0, 0, tzinfo=timezone.utc
    )


def test_next_period_end_advances_by_months():
    end = datetime(2026, 1, 31, 0, 0, tzinfo=timezone.utc)
    assert services.next_period_end(end, "month", 1) == datetime(
        2026, 2, 28, 0, 0, tzinfo=timezone.utc
    )


def test_next_period_end_clamps_day_of_month():
    end = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
    assert services.next_period_end(end, "month", 1, day_of_month=31) == datetime(
        2026, 2, 28, 0, 0, tzinfo=timezone.utc
    )


def test_next_period_end_uses_day_of_month_when_provided():
    end = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
    assert services.next_period_end(end, "month", 1, day_of_month=1) == datetime(
        2026, 2, 1, 0, 0, tzinfo=timezone.utc
    )


def test_next_period_end_wraps_year():
    end = datetime(2026, 11, 30, 0, 0, tzinfo=timezone.utc)
    assert services.next_period_end(end, "month", 3) == datetime(
        2027, 2, 28, 0, 0, tzinfo=timezone.utc
    )


def test_next_period_end_unknown_unit_raises():
    with pytest.raises(ValueError, match="unknown recurrence unit"):
        services.next_period_end(datetime(2026, 1, 1, tzinfo=timezone.utc), "hour", 1)


def test_compute_sweep_over_target_counts_rollover():
    move, rollover, new_current = services.compute_sweep(
        zapped=10200,
        target=10000,
        sweep_mode="target_amount",
        rollover_mode="counts_as_progress",
    )
    assert move == 10000
    assert rollover == 200
    assert new_current == 200


def test_compute_sweep_over_target_resets_to_zero():
    move, rollover, new_current = services.compute_sweep(
        zapped=10200,
        target=10000,
        sweep_mode="target_amount",
        rollover_mode="reset_to_zero",
    )
    assert move == 10000
    assert rollover == 200
    assert new_current == 0


def test_compute_sweep_under_target_moves_all():
    move, rollover, new_current = services.compute_sweep(
        zapped=7000,
        target=10000,
        sweep_mode="target_amount",
        rollover_mode="counts_as_progress",
    )
    assert move == 7000
    assert rollover == 0
    assert new_current == 0


def test_compute_sweep_entire_amount_mode():
    move, rollover, new_current = services.compute_sweep(
        zapped=10200,
        target=10000,
        sweep_mode="entire_amount",
        rollover_mode="counts_as_progress",
    )
    assert move == 10200
    assert rollover == 0
    assert new_current == 0


def test_compute_sweep_zero_zapped():
    move, rollover, new_current = services.compute_sweep(
        zapped=0,
        target=10000,
        sweep_mode="target_amount",
        rollover_mode="counts_as_progress",
    )
    assert move == 0
    assert rollover == 0
    assert new_current == 0


def test_compute_sweep_exact_target():
    move, rollover, new_current = services.compute_sweep(
        zapped=10000,
        target=10000,
        sweep_mode="target_amount",
        rollover_mode="counts_as_progress",
    )
    assert move == 10000
    assert rollover == 0
    assert new_current == 0


def test_compute_sweep_unknown_sweep_mode_raises():
    with pytest.raises(ValueError, match="unknown sweep_mode"):
        services.compute_sweep(100, 100, "bogus", "counts_as_progress")


def test_compute_sweep_unknown_rollover_mode_raises():
    with pytest.raises(ValueError, match="unknown rollover_mode"):
        services.compute_sweep(100, 100, "target_amount", "bogus")


def make_recurring_goal(**overrides):
    values = {
        "id": "recur123",
        "wallet": "wallet123",
        "title": "Monthly Goal",
        "description_above": "",
        "description_below": "",
        "goal_amount": 10000,
        "target_date": datetime.now(timezone.utc) - timedelta(days=1),
        "current_amount": 10200,
        "wallet_mode": WalletMode.vanilla,
        "font_name": "sans-serif",
        "font_weight": 400,
        "nostr_pubkey": None,
        "lightning_address_username": None,
        "created_at": datetime.now(timezone.utc) - timedelta(days=31),
        "updated_at": datetime.now(timezone.utc) - timedelta(days=31),
        "recurring": True,
        "recurrence_unit": "month",
        "recurrence_interval": 1,
        "recurrence_day_of_month": None,
        "target_wallet_id": "target-wallet-456",
        "rollover_mode": "counts_as_progress",
        "sweep_mode": "target_amount",
        "period_index": 0,
        "period_start": datetime.now(timezone.utc) - timedelta(days=31),
        "last_swept_at": None,
        "sweeping": False,
    }
    values.update(overrides)
    return Goal(**values)


def test_sweep_recurring_goal_over_target_with_rollover(monkeypatch):
    goal = make_recurring_goal()
    updated_goal = make_recurring_goal(
        current_amount=200,
        period_index=1,
        period_start=goal.target_date,
        target_date=services.next_period_end(goal.target_date, "month", 1),
        last_swept_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(services, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(services, "acquire_sweep_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(services, "release_sweep_lock", AsyncMock())
    monkeypatch.setattr(
        services, "complete_sweep", AsyncMock(return_value=updated_goal)
    )
    send = AsyncMock()
    monkeypatch.setattr(services.websocket_manager, "send", send)

    target_wallet = SimpleNamespace(balance_msat=10200 * 1000)
    get_wallet = AsyncMock(return_value=target_wallet)
    monkeypatch.setattr("lnbits.core.crud.get_wallet", get_wallet)

    payment = SimpleNamespace(
        payment_hash="ab" * 32,
        payment_request="lnbc1sweep",
        bolt11="lnbc1sweep",
    )
    monkeypatch.setattr(
        services, "create_payment_request", AsyncMock(return_value=payment)
    )
    monkeypatch.setattr(services, "pay_invoice", AsyncMock())

    period = asyncio.run(services.sweep_recurring_goal("recur123"))

    assert period.zapped_total == 10200
    assert period.moved_to_target == 10000
    assert period.rollover == 200
    assert period.period_index == 0
    assert period.sweep_mode == "target_amount"

    pay_call = services.pay_invoice.await_args
    assert pay_call.kwargs["wallet_id"] == "wallet123"
    assert "lnbc1sweep" in pay_call.kwargs["payment_request"]

    send.assert_awaited_once()
    assert send.await_args.args[0] == "recur123"
    services.release_sweep_lock.assert_not_awaited()


def test_sweep_recurring_goal_insufficient_balance_releases_lock(monkeypatch):
    goal = make_recurring_goal()
    monkeypatch.setattr(services, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(services, "acquire_sweep_lock", AsyncMock(return_value=True))
    release = AsyncMock()
    monkeypatch.setattr(services, "release_sweep_lock", release)
    monkeypatch.setattr(services, "complete_sweep", AsyncMock())
    monkeypatch.setattr(services.websocket_manager, "send", AsyncMock())

    target_wallet = SimpleNamespace(balance_msat=5000 * 1000)
    get_wallet = AsyncMock(return_value=target_wallet)
    monkeypatch.setattr("lnbits.core.crud.get_wallet", get_wallet)
    monkeypatch.setattr(services, "create_payment_request", AsyncMock())
    monkeypatch.setattr(services, "pay_invoice", AsyncMock())

    with pytest.raises(services.SweepError, match="Insufficient balance"):
        asyncio.run(services.sweep_recurring_goal("recur123"))

    release.assert_awaited_once_with("recur123")
    services.complete_sweep.assert_not_awaited()


def test_sweep_recurring_goal_not_recurring_raises(monkeypatch):
    goal = make_recurring_goal(recurring=False)
    monkeypatch.setattr(services, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(services, "acquire_sweep_lock", AsyncMock())
    monkeypatch.setattr(services, "release_sweep_lock", AsyncMock())

    with pytest.raises(services.SweepError, match="not recurring"):
        asyncio.run(services.sweep_recurring_goal("recur123"))

    services.acquire_sweep_lock.assert_not_awaited()


def test_sweep_recurring_goal_not_due_raises(monkeypatch):
    goal = make_recurring_goal(
        target_date=datetime.now(timezone.utc) + timedelta(days=30)
    )
    monkeypatch.setattr(services, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(services, "acquire_sweep_lock", AsyncMock())
    monkeypatch.setattr(services, "release_sweep_lock", AsyncMock())

    with pytest.raises(services.SweepError, match="not ended yet"):
        asyncio.run(services.sweep_recurring_goal("recur123"))

    services.acquire_sweep_lock.assert_not_awaited()


def test_sweep_recurring_goal_lock_not_acquired_raises(monkeypatch):
    goal = make_recurring_goal()
    monkeypatch.setattr(services, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(services, "acquire_sweep_lock", AsyncMock(return_value=False))
    monkeypatch.setattr(services, "release_sweep_lock", AsyncMock())

    with pytest.raises(services.SweepError, match="already being swept"):
        asyncio.run(services.sweep_recurring_goal("recur123"))


def test_sweep_recurring_goal_zero_zapped_skips_transfer(monkeypatch):
    goal = make_recurring_goal(current_amount=0)
    updated_goal = make_recurring_goal(
        current_amount=0,
        period_index=1,
        period_start=goal.target_date,
        target_date=services.next_period_end(goal.target_date, "month", 1),
    )
    monkeypatch.setattr(services, "get_goal", AsyncMock(return_value=goal))
    monkeypatch.setattr(services, "acquire_sweep_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(services, "release_sweep_lock", AsyncMock())
    monkeypatch.setattr(
        services, "complete_sweep", AsyncMock(return_value=updated_goal)
    )
    monkeypatch.setattr(services.websocket_manager, "send", AsyncMock())

    create_pr = AsyncMock()
    pay_inv = AsyncMock()
    monkeypatch.setattr(services, "create_payment_request", create_pr)
    monkeypatch.setattr(services, "pay_invoice", pay_inv)

    period = asyncio.run(services.sweep_recurring_goal("recur123"))

    assert period.moved_to_target == 0
    assert period.rollover == 0
    create_pr.assert_not_awaited()
    pay_inv.assert_not_awaited()
    services.release_sweep_lock.assert_not_awaited()


def test_sweep_due_loop_sweeps_due_goals_then_sleeps(monkeypatch):
    import asyncio as _asyncio

    from .. import tasks

    goal = make_recurring_goal()
    call_count = {"sweep": 0, "clear": 0, "sleep": 0}

    async def fake_clear(timeout):
        call_count["clear"] += 1

    async def fake_get_due():
        if call_count["sweep"] == 0:
            return [goal]
        return []

    async def fake_sweep(goal_id):
        call_count["sweep"] += 1

    async def fake_sleep(seconds):
        call_count["sleep"] += 1
        if call_count["sleep"] >= 2:
            raise _asyncio.CancelledError()

    monkeypatch.setattr(tasks, "clear_stale_sweeping_flags", fake_clear)
    monkeypatch.setattr(tasks, "get_due_recurring_goals_all_wallets", fake_get_due)
    monkeypatch.setattr(tasks, "sweep_recurring_goal", fake_sweep)
    monkeypatch.setattr(tasks, "builtin_scheduler_interval_seconds", 3600)
    monkeypatch.setattr(_asyncio, "sleep", fake_sleep)

    settings_ns = SimpleNamespace(lnbits_running=True)
    monkeypatch.setattr("lnbits.settings.settings", settings_ns)

    with pytest.raises(_asyncio.CancelledError):
        _asyncio.run(tasks.sweep_due_loop())

    assert call_count["clear"] >= 1
    assert call_count["sweep"] == 1


def test_sweep_due_loop_continues_on_sweep_error(monkeypatch):
    import asyncio as _asyncio

    from .. import tasks

    goal = make_recurring_goal()
    call_count = {"sleep": 0}

    async def fake_clear(timeout):
        pass

    async def fake_get_due():
        return [goal]

    async def fake_sweep(goal_id):
        raise services.SweepError("insufficient balance")

    async def fake_sleep(seconds):
        call_count["sleep"] += 1
        if call_count["sleep"] >= 2:
            raise _asyncio.CancelledError()

    monkeypatch.setattr(tasks, "clear_stale_sweeping_flags", fake_clear)
    monkeypatch.setattr(tasks, "get_due_recurring_goals_all_wallets", fake_get_due)
    monkeypatch.setattr(tasks, "sweep_recurring_goal", fake_sweep)
    monkeypatch.setattr(tasks, "builtin_scheduler_interval_seconds", 3600)
    monkeypatch.setattr(_asyncio, "sleep", fake_sleep)

    settings_ns = SimpleNamespace(lnbits_running=True)
    monkeypatch.setattr("lnbits.settings.settings", settings_ns)

    with pytest.raises(_asyncio.CancelledError):
        _asyncio.run(tasks.sweep_due_loop())
