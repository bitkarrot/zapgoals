import asyncio
import ipaddress
import json
import secrets
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import websockets
from fastapi import Request
from lnbits.core.models import Payment
from lnbits.core.models.payments import CreateInvoice
from lnbits.core.services import create_payment_request, websocket_manager
from lnbits.core.services.payments import pay_invoice
from lnbits.helpers import urlsafe_short_hash
from lnurl import (
    CallbackUrl,
    LnurlPayMetadata,
    LnurlPayResponse,
    MilliSatoshi,
)
from loguru import logger
from pydantic import parse_obj_as
from pynostr.event import Event
from pynostr.key import PrivateKey

from .crud import (
    acquire_sweep_lock,
    complete_sweep,
    create_contribution,
    create_extension_setting,
    get_extension_setting,
    get_goal,
    purge_expired_unpaid_contributions,
    release_sweep_lock,
    settle_contribution,
)
from .models import (
    MAX_SATS,
    PUBKEY_RE,
    Goal,
    InvoiceResponse,
    Period,
    PublicGoal,
    SweepError,
)
from .settings import lightning_address_enabled

MIN_SENDABLE_MSAT = 1000
MAX_SENDABLE_MSAT = MAX_SATS * 1000
COMMENT_ALLOWED = 280
INVOICE_EXPIRY_SECONDS = 600


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def goal_status(goal: Goal) -> str:
    if goal.current_amount >= goal.goal_amount:
        return "completed"
    if datetime.now(timezone.utc) >= _as_utc(goal.target_date):
        return "expired"
    return "active"


def next_period_end(
    current_end: datetime,
    unit: str,
    interval: int,
    day_of_month: int | None = None,
) -> datetime:
    """Compute the next period boundary in UTC.

    For day/week units the boundary advances by interval days/weeks.
    For month, quarter, half_year and year units it advances by the
    equivalent number of months; when day_of_month is given (month only)
    the result is clamped to the last day of the target month.
    """
    end = _as_utc(current_end)
    if unit == "day":
        return end + timedelta(days=interval)
    if unit == "week":
        return end + timedelta(weeks=interval)
    months_per_unit = {
        "month": 1,
        "quarter": 3,
        "half_year": 6,
        "year": 12,
    }
    if unit in months_per_unit:
        total_months = months_per_unit[unit] * interval
        year = end.year
        month = end.month + total_months
        while month > 12:
            month -= 12
            year += 1
        if day_of_month is not None:
            last_day = monthrange(year, month)[1]
            day = min(day_of_month, last_day)
        else:
            day = min(end.day, monthrange(year, month)[1])
        return end.replace(year=year, month=month, day=day)
    raise ValueError(f"unknown recurrence unit: {unit}")


def compute_sweep(
    zapped: int,
    target: int,
    sweep_mode: str,
    rollover_mode: str,
) -> tuple[int, int, int]:
    """Compute the sweep outcome for one period.

    Returns (move_amount, rollover, new_current):
    - target_amount mode moves min(zapped, target); excess rolls over.
    - entire_amount mode moves everything zapped; rollover is always 0.
    - counts_as_progress seeds the next period with the rollover;
      reset_to_zero drops the counter to 0 (sats stay in the goal wallet).
    """
    if sweep_mode == "entire_amount":
        move_amount = zapped
    elif sweep_mode == "target_amount":
        move_amount = min(zapped, target)
    else:
        raise ValueError(f"unknown sweep_mode: {sweep_mode}")
    rollover = zapped - move_amount
    if rollover_mode == "counts_as_progress":
        new_current = rollover
    elif rollover_mode == "reset_to_zero":
        new_current = 0
    else:
        raise ValueError(f"unknown rollover_mode: {rollover_mode}")
    return move_amount, rollover, new_current


def public_goal(goal: Goal, request: Request) -> PublicGoal:
    endpoint = str(request.url_for("zapgoals_lnurl", goal_id=goal.id))
    address = None
    if lightning_address_enabled and goal.lightning_address_username:
        address = f"{goal.lightning_address_username}@{request.url.netloc}"
    percent = round((goal.current_amount * 100) / goal.goal_amount, 2)
    return PublicGoal(
        id=goal.id,
        title=goal.title,
        text={
            "above": goal.description_above,
            "below": goal.description_below,
        },
        description_above=goal.description_above,
        description_below=goal.description_below,
        goal_amount=goal.goal_amount,
        current_amount=goal.current_amount,
        target_date=goal.target_date,
        suggested_amounts=goal.suggested_amounts,
        colors={
            "background": goal.background_color,
            "text": goal.text_color,
            "progress": goal.progress_color,
            "remainder": goal.remainder_color,
        },
        background_color=goal.background_color,
        text_color=goal.text_color,
        progress_color=goal.progress_color,
        remainder_color=goal.remainder_color,
        font=goal.font_name,
        font_family=goal.font_family,
        font_name=goal.font_name,
        font_weight=goal.font_weight,
        wallet_mode=goal.wallet_mode,
        status=goal_status(goal),
        percent=percent,
        lnurl=endpoint,
        lnurl_url=endpoint,
        lightning_address=address,
        nostr_pubkey=goal.nostr_pubkey,
        recurring=goal.recurring,
        show_period_badge=goal.show_period_badge,
        period_index=goal.period_index,
        period_start=goal.period_start,
        last_swept_at=goal.last_swept_at,
    )


def lnurl_metadata(goal: Goal, identifier: str) -> str:
    return json.dumps(
        [["text/plain", goal.title], ["text/identifier", identifier]],
        separators=(",", ":"),
        ensure_ascii=False,
    )


async def get_nostr_keypair():
    setting = await get_extension_setting()
    if not setting:
        private_key = secrets.token_hex(32)
        try:
            setting = await create_extension_setting(private_key)
        except Exception:
            setting = await get_extension_setting()
            if not setting:
                raise
    key = PrivateKey(bytes.fromhex(setting.nostr_private_key))
    return setting.nostr_private_key, key.public_key.hex()


async def make_lnurl_response(
    goal: Goal, request: Request, identifier: str | None = None
) -> LnurlPayResponse:
    callback = str(request.url_for("zapgoals_lnurl_callback", goal_id=goal.id))
    if identifier is None:
        local_part = goal.lightning_address_username or goal.id
        identifier = f"{local_part}@{request.url.netloc}"
    signing_pubkey = None
    if goal.nostr_pubkey:
        _, signing_pubkey = await get_nostr_keypair()
    return LnurlPayResponse(
        callback=parse_obj_as(CallbackUrl, callback),
        minSendable=MilliSatoshi(MIN_SENDABLE_MSAT),
        maxSendable=MilliSatoshi(MAX_SENDABLE_MSAT),
        metadata=LnurlPayMetadata(lnurl_metadata(goal, identifier)),
        commentAllowed=COMMENT_ALLOWED,
        allowsNostr=bool(goal.nostr_pubkey),
        nostrPubkey=signing_pubkey,
    )


async def create_goal_invoice(
    goal: Goal,
    amount: int,
    source: str,
    unhashed_description: bytes | None = None,
    extra: dict | None = None,
) -> InvoiceResponse:
    payment_extra = {
        "tag": "zapgoals",
        "goal_id": goal.id,
        "source": source,
    }
    payment_extra.update(extra or {})
    await purge_expired_unpaid_contributions(goal.id, INVOICE_EXPIRY_SECONDS)
    invoice_data = CreateInvoice(
        out=False,
        amount=amount,
        unit="sat",
        memo=goal.title,
        expiry=INVOICE_EXPIRY_SECONDS,
        extra=payment_extra,
        unhashed_description=(
            unhashed_description.hex() if unhashed_description is not None else None
        ),
    )
    if "extension" in CreateInvoice.__fields__:
        invoice_data.extension = "zapgoals"
    payment = await create_payment_request(goal.wallet, invoice_data)
    await create_contribution(payment.payment_hash, goal.id, amount, source)
    return InvoiceResponse(
        payment_hash=payment.payment_hash,
        payment_request=payment.payment_request or payment.bolt11,
        amount=amount,
    )


def validate_zap_request(raw_nostr: str, goal: Goal, amount_msat: int):
    if not goal.nostr_pubkey:
        raise ValueError("This goal does not accept Nostr zaps")
    try:
        data = json.loads(raw_nostr)
        if not isinstance(data, dict):
            raise ValueError
        event = Event.from_dict(data)
    except Exception as exc:
        raise ValueError("Invalid Nostr zap request") from exc
    try:
        valid_event = event.kind == 9734 and event.verify()
    except Exception as exc:
        raise ValueError("Invalid Nostr zap request") from exc
    if not valid_event:
        raise ValueError("Invalid Nostr zap request")
    p_tags = [tag for tag in event.tags if tag and tag[0] == "p"]
    if len(p_tags) != 1 or len(p_tags[0]) != 2 or p_tags[0][1] != goal.nostr_pubkey:
        raise ValueError("Zap request recipient does not match this goal")
    amount_tags = [tag for tag in event.tags if tag and tag[0] == "amount"]
    if len(amount_tags) > 1:
        raise ValueError("Zap request must contain at most one amount tag")
    if amount_tags:
        try:
            if len(amount_tags[0]) != 2 or int(amount_tags[0][1]) != amount_msat:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("Zap request amount does not match") from exc
    event_tags = [tag for tag in event.tags if tag and tag[0] == "e"]
    if len(event_tags) > 1:
        raise ValueError("Zap request must contain at most one e tag")
    coordinate_tags = [tag for tag in event.tags if tag and tag[0] == "a"]
    if len(coordinate_tags) > 1:
        raise ValueError("Zap request must contain at most one a tag")
    if coordinate_tags:
        coordinate = coordinate_tags[0][1] if len(coordinate_tags[0]) == 2 else ""
        parts = coordinate.split(":", 2)
        if (
            len(parts) != 3
            or not parts[0].isdigit()
            or not PUBKEY_RE.fullmatch(parts[1])
        ):
            raise ValueError("Zap request contains an invalid a tag")
    relay_tags = [tag for tag in event.tags if tag and tag[0] == "relays"]
    if len(relay_tags) != 1:
        raise ValueError("Zap request must contain one relays tag")
    relays = relay_tags[0][1:]
    if not relays or len(relays) > 10:
        raise ValueError("Zap request must contain between 1 and 10 relays")
    validated = []
    for relay in relays:
        if not isinstance(relay, str):
            raise ValueError("Invalid Nostr relay URL")
        parsed = urlparse(relay)
        if (
            parsed.scheme not in {"ws", "wss"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError("Invalid Nostr relay URL")
        hostname = parsed.hostname.lower()
        if hostname == "localhost" or hostname.endswith((".local", ".internal")):
            raise ValueError("Invalid Nostr relay URL")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise ValueError("Invalid Nostr relay URL")
        validated.append(relay)
    return event, list(dict.fromkeys(validated))


async def process_settled_payment(payment: Payment) -> Goal | None:
    goal = await settle_contribution(payment.payment_hash)
    if not goal:
        return None
    payload = public_goal_dict(goal)
    await websocket_manager.send(goal.id, json.dumps(payload, default=str))
    if payment.extra and payment.extra.get("source") == "nostr":
        await publish_zap_receipt(payment)
    return goal


def public_goal_dict(goal: Goal) -> dict:
    percent = round((goal.current_amount * 100) / goal.goal_amount, 2)
    return {
        "id": goal.id,
        "title": goal.title,
        "current_amount": goal.current_amount,
        "goal_amount": goal.goal_amount,
        "target_date": _as_utc(goal.target_date).isoformat(),
        "status": goal_status(goal),
        "percent": percent,
    }


async def publish_zap_receipt(payment: Payment) -> None:
    extra = payment.extra or {}
    raw = extra.get("nostr")
    relays = extra.get("nostr_relays") or []
    if not isinstance(raw, str) or not isinstance(relays, list):
        return
    try:
        zap_request = Event.from_dict(json.loads(raw))
        private_key, _ = await get_nostr_keypair()
        copied_tags = [
            list(tag) for tag in zap_request.tags if tag and tag[0] in {"p", "e", "a"}
        ]
        tags = [
            *copied_tags,
            ["P", zap_request.pubkey],
            ["bolt11", payment.bolt11],
            ["description", raw],
        ]
        if payment.preimage:
            tags.append(["preimage", payment.preimage])
        receipt = Event(
            content="",
            created_at=int(_as_utc(payment.time).timestamp()),
            kind=9735,
            tags=tags,
        )
        receipt.sign(private_key)
        message = json.dumps(["EVENT", receipt.to_dict()], separators=(",", ":"))
        await asyncio.gather(
            *[_publish_to_relay(relay, message) for relay in relays[:10]],
            return_exceptions=True,
        )
    except Exception as exc:
        logger.warning("Could not create zap receipt: {}", str(exc))


async def _publish_to_relay(relay: str, message: str) -> None:
    async def publish() -> None:
        async with websockets.connect(
            relay, open_timeout=4, close_timeout=1, max_size=262144
        ) as socket:
            await socket.send(message)
            try:
                await asyncio.wait_for(socket.recv(), timeout=1)
            except asyncio.TimeoutError:
                pass

    try:
        await asyncio.wait_for(publish(), timeout=5)
    except Exception as exc:
        logger.warning("Could not publish zap receipt to relay {}: {}", relay, str(exc))


SWEEP_STALE_TIMEOUT_SECONDS = 300


async def sweep_recurring_goal(goal_id: str) -> Period:
    """Sweep one recurring goal whose period has ended.

    Moves settled sats to the target wallet, records a period ledger row,
    and advances the goal to the next period. Raises SweepError if the
    goal is not recurring, not due, already being swept, or the goal
    wallet balance is insufficient.
    """
    goal = await get_goal(goal_id)
    if not goal:
        raise SweepError("Goal not found")
    if not goal.recurring:
        raise SweepError("Goal is not recurring")
    if datetime.now(timezone.utc) < _as_utc(goal.target_date):
        raise SweepError("Goal period has not ended yet")

    acquired = await acquire_sweep_lock(goal_id)
    if not acquired:
        raise SweepError("Goal is already being swept")

    try:
        zapped = goal.current_amount
        move_amount, rollover, new_current = compute_sweep(
            zapped, goal.goal_amount, goal.sweep_mode, goal.rollover_mode
        )

        if move_amount > 0:
            from lnbits.core.crud import get_wallet

            goal_wallet = await get_wallet(goal.wallet)
            if not goal_wallet:
                raise SweepError("Goal wallet not found")
            balance_sat = goal_wallet.balance_msat // 1000
            if balance_sat < move_amount:
                raise SweepError(
                    f"Insufficient balance: wallet has {balance_sat} sats, "
                    f"sweep requires {move_amount} sats. The goal wallet must "
                    f"be dedicated to this recurring goal."
                )

            assert goal.target_wallet_id is not None
            sweep_extra = {
                "tag": "zapgoals_sweep",
                "goal_id": goal.id,
                "period_index": goal.period_index,
            }
            invoice_data = CreateInvoice(
                out=False,
                amount=move_amount,
                unit="sat",
                memo=f"{goal.title} period {goal.period_index + 1}",
                expiry=3600,
                extra=sweep_extra,
            )
            if "extension" in CreateInvoice.__fields__:
                invoice_data.extension = "zapgoals"
            payment = await create_payment_request(goal.target_wallet_id, invoice_data)
            await pay_invoice(
                wallet_id=goal.wallet,
                payment_request=payment.payment_request or payment.bolt11,
                extra=sweep_extra,
                description=f"ZapGoals sweep period {goal.period_index + 1}",
            )

        now = datetime.now(timezone.utc)
        period_start = (
            _as_utc(goal.period_start)
            if goal.period_start
            else _as_utc(goal.created_at)
        )
        period = Period(
            id=urlsafe_short_hash(),
            goal_id=goal.id,
            period_index=goal.period_index,
            period_start=period_start,
            period_end=_as_utc(goal.target_date),
            zapped_total=zapped,
            moved_to_target=move_amount,
            rollover=rollover,
            sweep_mode=goal.sweep_mode,
            swept_at=now,
        )

        assert goal.recurrence_unit is not None
        next_end = next_period_end(
            goal.target_date,
            goal.recurrence_unit,
            goal.recurrence_interval,
            goal.recurrence_day_of_month,
        )

        updated = await complete_sweep(
            goal_id,
            new_current,
            goal.period_index + 1,
            _as_utc(goal.target_date),
            next_end,
            period,
        )
        if not updated:
            raise SweepError("Goal vanished during sweep")

        payload = public_goal_dict(updated)
        await websocket_manager.send(goal.id, json.dumps(payload, default=str))
        return period
    except SweepError:
        await release_sweep_lock(goal_id)
        raise
    except Exception as exc:
        await release_sweep_lock(goal_id)
        raise SweepError(f"Sweep failed: {exc}") from exc
