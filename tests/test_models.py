from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ..models import GoalData, InvoiceRequest, WalletMode


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


@pytest.mark.parametrize(
    "font_name",
    [
        "sans-serif",
        "system-ui, sans-serif",
        "Arial, sans-serif",
        '"Trebuchet MS", sans-serif',
        "Verdana, sans-serif",
        "Tahoma, sans-serif",
        "Georgia, serif",
        '"Times New Roman", serif',
        '"Courier New", monospace',
    ],
)
def test_supported_font_names_and_weights(font_name):
    for weight in (400, 600, 700, 800):
        goal = GoalData(**valid_goal_data(font_name=font_name, font_weight=weight))
        assert goal.font_name == font_name
        assert goal.font_weight == weight

    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(font_name="url(https://example.com/font.woff)"))
    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(font_weight=900))


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


@pytest.mark.parametrize("mode", ["vanilla", "all"])
def test_supported_wallet_modes(mode):
    goal = GoalData(**valid_goal_data(wallet_mode=mode))
    assert goal.wallet_mode is WalletMode(mode)


@pytest.mark.parametrize("mode", ["nwc", "unknown"])
def test_unknown_wallet_mode_is_rejected(mode):
    with pytest.raises(ValidationError):
        GoalData(**valid_goal_data(wallet_mode=mode))


def test_suggested_amounts_are_limited_and_unique():
    goal = GoalData(**valid_goal_data(suggested_amounts=[21, 100, 500, 1000]))
    assert goal.suggested_amounts == [21, 100, 500, 1000]

    for values in ([], [1, 2, 3, 4, 5], [21, 21], [0, 21]):
        with pytest.raises(ValidationError):
            GoalData(**valid_goal_data(suggested_amounts=values))


def test_invoice_comment_is_trimmed_and_limited():
    assert InvoiceRequest(amount=21, comment="  great goal  ").comment == "great goal"
    assert InvoiceRequest(amount=21, comment="   ").comment is None

    with pytest.raises(ValidationError):
        InvoiceRequest(amount=21, comment="x" * 281)


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
