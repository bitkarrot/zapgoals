import re
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, validator

MAX_SATS = 2_100_000_000
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
USERNAME_RE = re.compile(r"^[a-z0-9._-]+$")
PUBKEY_RE = re.compile(r"^[0-9a-f]{64}$")


class WalletMode(str, Enum):
    vanilla = "vanilla"
    all = "all"


class GoalData(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description_above: str = Field("", max_length=2000)
    description_below: str = Field("", max_length=2000)
    goal_amount: int = Field(
        ..., gt=0, le=MAX_SATS, description="Funding target in satoshis."
    )
    target_date: datetime = Field(
        ..., description="Timezone-aware target timestamp, normalized to UTC."
    )
    suggested_amounts: list[int] = Field(
        default_factory=lambda: [21, 100, 500, 1000],
        description="One to four unique suggested contribution amounts in satoshis.",
    )
    wallet_mode: WalletMode = Field(
        WalletMode.vanilla,
        description="Payment UI: vanilla BOLT11 invoice or Bitcoin Connect.",
    )
    background_color: str = "#FFFFFF"
    text_color: str = "#111111"
    progress_color: str = "#2E7D32"
    remainder_color: str = "#E0E0E0"
    font_family: str = "sans-serif"
    nostr_pubkey: str | None = Field(
        None, description="Recipient Nostr public key as 64 lowercase hex characters."
    )
    lightning_address_username: str | None = Field(
        None,
        max_length=64,
        description="Optional unique Lightning Address username.",
    )

    @validator("title", "description_above", "description_below")
    def plain_text(cls, value):
        if "\x00" in value:
            raise ValueError("NUL characters are not allowed")
        return value.strip() if value else ""

    @validator("background_color", "text_color", "progress_color", "remainder_color")
    def valid_color(cls, value):
        if not COLOR_RE.fullmatch(value):
            raise ValueError("color must be in #RRGGBB format")
        return value.upper()

    @validator("font_family")
    def safe_font(cls, value):
        if value not in {"sans-serif", "serif", "monospace"}:
            raise ValueError("unsupported font family")
        return value

    @validator("suggested_amounts", pre=True)
    def valid_suggested_amounts(cls, value):
        if not isinstance(value, list) or not 1 <= len(value) <= 4:
            raise ValueError("provide between one and four suggested amounts")
        if any(
            not isinstance(amount, int) or isinstance(amount, bool) for amount in value
        ):
            raise ValueError("suggested amounts must be whole sat amounts")
        if len(set(value)) != len(value):
            raise ValueError("suggested amounts must be unique")
        if any(amount < 1 or amount > MAX_SATS for amount in value):
            raise ValueError("suggested amounts must be valid whole sat amounts")
        return value

    @validator("nostr_pubkey")
    def valid_nostr_pubkey(cls, value):
        if value is not None and not PUBKEY_RE.fullmatch(value):
            raise ValueError("nostr_pubkey must be 64 lowercase hex characters")
        return value

    @validator("lightning_address_username")
    def normalize_username(cls, value):
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if not USERNAME_RE.fullmatch(value):
            raise ValueError("invalid lightning address username")
        return value

    @validator("target_date")
    def aware_target_date(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("target_date must include a timezone")
        return value.astimezone(timezone.utc)


class Goal(GoalData):
    id: str
    wallet: str
    current_amount: int = 0
    created_at: datetime
    updated_at: datetime


class PublicGoal(BaseModel):
    id: str
    title: str
    text: dict
    description_above: str
    description_below: str
    goal_amount: int = Field(..., description="Funding target in satoshis.")
    current_amount: int = Field(
        ..., description="Total settled contributions in satoshis."
    )
    target_date: datetime = Field(..., description="Goal target timestamp in UTC.")
    suggested_amounts: list[int] = Field(
        ..., description="Suggested contribution amounts in satoshis."
    )
    colors: dict
    background_color: str
    text_color: str
    progress_color: str
    remainder_color: str
    font: str
    font_family: str
    wallet_mode: WalletMode
    status: str
    percent: float
    lnurl: str
    lnurl_url: str
    lightning_address: str | None = None
    nostr_pubkey: str | None = None


class Contribution(BaseModel):
    payment_hash: str
    goal_id: str
    amount: int = Field(..., ge=1, le=MAX_SATS)
    paid: bool = False
    source: str
    created_at: datetime
    paid_at: datetime | None = None

    @validator("source")
    def valid_source(cls, value):
        if value not in {"invoice", "lnurl", "nostr"}:
            raise ValueError("invalid contribution source")
        return value


class InvoiceRequest(BaseModel):
    amount: int = Field(
        ..., ge=1, le=MAX_SATS, description="Contribution amount in satoshis."
    )
    comment: str | None = Field(
        None, max_length=280, description="Optional contribution comment."
    )

    @validator("comment")
    def plain_comment(cls, value):
        if value is None or not value.strip():
            return None
        if "\x00" in value:
            raise ValueError("NUL characters are not allowed")
        return value.strip()


class InvoiceResponse(BaseModel):
    payment_hash: str = Field(..., description="Hex-encoded Lightning payment hash.")
    payment_request: str = Field(..., description="BOLT11 Lightning invoice.")
    amount: int = Field(..., description="Invoice amount in satoshis.")


class ExtensionSetting(BaseModel):
    id: str = "singleton"
    nostr_private_key: str
