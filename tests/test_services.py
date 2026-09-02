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
