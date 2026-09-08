"""Regression tests for the findings in SECURITY_REVIEW.md.

ZG-01 and ZG-02 are fixed; these tests pin the fixes. No LNbits server,
wallet, payment backend, or external relay is contacted.
"""

import asyncio
import json
import socket

import pytest
from pynostr.event import Event
from pynostr.key import PrivateKey

from .. import embed, services
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
