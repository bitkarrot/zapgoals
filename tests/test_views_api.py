import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from lnbits.core.models import WalletTypeInfo

from .. import views_api
from ..models import Goal, WalletMode


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
        nostr_pubkey=None,
        lightning_address_username=None,
        created_at=now,
        updated_at=now,
    )


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
