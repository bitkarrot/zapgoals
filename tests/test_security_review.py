"""Regression tests for the findings in SECURITY_REVIEW.md.

ZG-01 through ZG-04 are fixed; these tests pin the fixes. No LNbits server,
wallet, payment backend, or external relay is contacted.
"""

import asyncio
import json
import socket
from http import HTTPStatus
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from lnurl import LnurlErrorResponse
from pynostr.event import Event
from pynostr.key import PrivateKey

from .. import embed, services, views_api
from ..models import InvoiceRequest, InvoiceResponse
from ..ratelimit import WindowRateLimiter
from .test_services import make_goal


def relay_request(relay):
    recipient = PrivateKey().public_key.hex()
    sender = PrivateKey()
    event = Event(
        kind=9734,
        content="Local security regression test",
        tags=[["p", recipient], ["amount", "1000"], ["relays", relay]],
    )
    event.sign(sender.hex())
    return json.dumps(event.to_dict()), make_goal(nostr_pubkey=recipient)


@pytest.mark.parametrize("hostname", ["127.1", "2130706433", "0177.0.0.1", "0x7f.1"])
def test_relay_validation_rejects_alternate_loopback(hostname):
    raw, goal = relay_request(f"ws://{hostname}:12345/local-review")
    with pytest.raises(ValueError, match="relay"):
        services.validate_zap_request(raw, goal, 1000)


def test_relay_validation_accepts_public_relays():
    raw, goal = relay_request("wss://relay.example.com")
    _, relays = services.validate_zap_request(raw, goal, 1000)
    assert relays == ["wss://relay.example.com"]


@pytest.mark.parametrize("hostname", ["127.1", "relay.example.test"])
def test_publisher_never_contacts_private_addresses(monkeypatch, hostname):
    # Disable ambient HTTP/SOCKS proxies; all test traffic must remain local.
    for key in list(__import__("os").environ):
        if key.lower().endswith("_proxy"):
            monkeypatch.delenv(key)

    original_getaddrinfo = socket.getaddrinfo

    def local_dns(host, *args, **kwargs):
        if host == "relay.example.test":
            host = "127.0.0.1"
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_dns)

    async def reproduce():
        requests = []

        async def handle(reader, writer):
            requests.append(await reader.readuntil(b"\r\n\r\n"))
            writer.write(
                b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n"
                b"Connection: close\r\n\r\n"
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            relay = f"ws://{hostname}:{port}/local-review"
            raw, goal = relay_request(relay)
            try:
                _, relays = services.validate_zap_request(raw, goal, 1000)
            except ValueError:
                return
            await services._publish_to_relay(relays[0], "local review only")
        assert not requests, (
            "Untrusted relay caused a loopback HTTP request: "
            + requests[0].split(b"\r\n", 1)[0].decode()
        )

    asyncio.run(reproduce())


def test_embed_escapehtml_escapes_quotes():
    # ZG-02: escapeHtml is used in attribute contexts and must escape quotes.
    escaping = "replace(/\"/g,'&quot;')"
    assert escaping in embed.EMBED_HTML
    assert escaping in embed.WIDGET_JS


def test_embed_copy_buttons_avoid_inline_handlers():
    # ZG-02: no unescaped interpolation into inline event handlers.
    assert "window.__zgCopy(" not in embed.EMBED_HTML
    assert "data-copy=" in embed.EMBED_HTML
    assert "data-copy=" in embed.WIDGET_JS


def test_window_rate_limiter_blocks_and_resets():
    limiter = WindowRateLimiter(3, window_seconds=0.05)
    assert limiter.allow("key")
    assert limiter.allow("key")
    assert limiter.allow("key")
    assert not limiter.allow("key")
    assert limiter.allow("other-key")
    sleep(0.06)
    assert limiter.allow("key")

    unlimited = WindowRateLimiter(0)
    assert all(unlimited.allow("key") for _ in range(10))


def test_invoice_endpoints_share_rate_limit(monkeypatch):
    goal = make_goal()
    monkeypatch.setattr(views_api, "get_goal", AsyncMock(return_value=goal))
    invoice = InvoiceResponse(
        payment_hash="ab" * 32, payment_request="lnbc1test", amount=21
    )
    create_invoice = AsyncMock(return_value=invoice)
    monkeypatch.setattr(views_api, "create_goal_invoice", create_invoice)
    limiter = WindowRateLimiter(3, window_seconds=3600)
    monkeypatch.setattr(views_api, "_invoice_limiter", limiter)
    request = cast(
        Request,
        SimpleNamespace(
            client=SimpleNamespace(host="203.0.113.9"),
            url=SimpleNamespace(netloc="example.com"),
        ),
    )

    async def create():
        return await views_api.api_goal_invoice(
            "goal123", request, InvoiceRequest(amount=21, comment=None)
        )

    for _ in range(3):
        assert asyncio.run(create()) == invoice

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create())
    assert exc_info.value.status_code == HTTPStatus.TOO_MANY_REQUESTS

    response = asyncio.run(
        views_api.api_lnurl_callback("goal123", request, 21000, None, None, None)
    )
    assert isinstance(response, LnurlErrorResponse)
    assert "Rate limit" in response.reason
    assert create_invoice.await_count == 3


def test_qr_endpoint_only_renders_lightning_payloads():
    # ZG-04: QR codes are generated locally and only for Lightning data.
    response = views_api.api_qr(data="LIGHTNING:LNBC1TESTPAYLOAD")
    assert response.media_type == "image/svg+xml"
    assert b"<svg" in response.body
    assert response.headers["cache-control"] == "public, max-age=600"

    with pytest.raises(HTTPException) as exc_info:
        views_api.api_qr(data="https://phishing.example")
    assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST


def test_frontends_contain_no_third_party_hosts():
    # ZG-04: Bitcoin Connect is vendored and the QR service is self-hosted.
    static_js = Path(__file__).resolve().parent.parent / "static" / "js"
    public_js = (static_js / "public.js").read_text()
    vendor = static_js / "vendor" / "bitcoin-connect.bundle.mjs"
    assert vendor.exists()
    for source in (embed.EMBED_HTML, embed.WIDGET_JS, public_js):
        assert "esm.sh" not in source
        assert "qrserver.com" not in source
        assert "bitcoin-connect.bundle.mjs" in source
