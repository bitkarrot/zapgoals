import asyncio
import ipaddress
import json
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

import websockets
from fastapi import Request
from lnbits.core.models import Payment
from lnbits.core.models.payments import CreateInvoice
from lnbits.core.services import create_payment_request, websocket_manager
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
    create_contribution,
    create_extension_setting,
    get_extension_setting,
    settle_contribution,
)
from .models import MAX_SATS, PUBKEY_RE, Goal, InvoiceResponse, PublicGoal
from .settings import lightning_address_enabled

MIN_SENDABLE_MSAT = 1000
MAX_SENDABLE_MSAT = MAX_SATS * 1000
COMMENT_ALLOWED = 280


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
        font=goal.font_family,
        font_family=goal.font_family,
        wallet_mode=goal.wallet_mode,
        status=goal_status(goal),
        percent=percent,
        lnurl=endpoint,
        lnurl_url=endpoint,
        lightning_address=address,
        nostr_pubkey=goal.nostr_pubkey,
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
    invoice_data = CreateInvoice(
        out=False,
        amount=amount,
        unit="sat",
        memo=goal.title,
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
