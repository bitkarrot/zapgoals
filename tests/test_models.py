from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ..models import GoalData, WalletMode


def valid_goal_data(**overrides):
    data = {
        "title": "Open-source fundraiser",
        "goal_amount": 100_000,
        "target_date": datetime.now(timezone.utc) + timedelta(days=30),
    }
    data.update(overrides)
    return data


def test_goal_target_amount_and_date_are_validated():
    goal = GoalData(**valid_goal_data())

    assert goal.goal_amount == 100_000
    assert goal.target_date.tzinfo is not None
    assert goal.target_date.utcoffset() == timedelta(0)

    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(goal_amount=0))

    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(target_date=datetime.now()))


def test_goal_colors_are_normalized_and_validated():
    goal = GoalData(
        **valid_goal_data(
            background_color="#aabbcc",
            text_color="#010203",
            progress_color="#abcdef",
            remainder_color="#fedcba",
        )
    )

    assert goal.background_color == "#AABBCC"
    assert goal.text_color == "#010203"
    assert goal.progress_color == "#ABCDEF"
    assert goal.remainder_color == "#FEDCBA"

    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(background_color="aabbcc"))


@pytest.mark.parametrize("mode", ["vanilla", "nwc", "all"])
def test_supported_wallet_modes(mode):
    goal = GoalData(**valid_goal_data(wallet_mode=mode))
    assert goal.wallet_mode is WalletMode(mode)


def test_unknown_wallet_mode_is_rejected():
    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(wallet_mode="unknown"))


def test_nostr_pubkey_requires_lowercase_hex():
    pubkey = "ab" * 32
    goal = GoalData(**valid_goal_data(nostr_pubkey=pubkey))
    assert goal.nostr_pubkey == pubkey

    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(nostr_pubkey="AB" * 32))

    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(nostr_pubkey="ab" * 31))


def test_lightning_address_username_is_normalized_and_validated():
    goal = GoalData(**valid_goal_data(lightning_address_username="  Satoshi_21  "))
    assert goal.lightning_address_username == "satoshi_21"

    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(lightning_address_username="not an address"))
