# ZapGoals Security Review

- **Version reviewed:** 0.1.6
- **Date:** 2026-09-08
- **Scope:** all server code (`views.py`, `views_api.py`, `crud.py`, `models.py`, `services.py`, `tasks.py`, `migrations.py`, `settings.py`, `__init__.py`), the standalone embeds (`embed.py`), the SPA (`static/js/`), tests, configuration and packaging files.
- **Method:** manual code review with local reproductions in `tests/test_security_review.py`. No LNbits server, wallet, payment backend, or external relay was contacted.

## Finding summary

| ID    | Severity | Title                                                      | Status          |
| ----- | -------- | ---------------------------------------------------------- | --------------- |
| ZG-01 | Medium   | SSRF via relay validation bypass                           | Fixed           |
| ZG-02 | Low      | `escapeHtml` not attribute-safe; unescaped inline handlers | Fixed           |
| ZG-03 | Low      | Unauthenticated invoice creation without rate limiting     | Open (advisory) |
| ZG-04 | Low      | Invoice data sent to third-party QR service; CDN script    | Open (advisory) |
| ZG-05 | Info     | Scheduler proxy uses admin key for invoice-key callers     | Open (accepted) |
| ZG-06 | Info     | Plaintext extension Nostr key; sweep crash window          | Open (accepted) |

## Findings

### ZG-01 — SSRF via relay validation bypass (Medium, fixed)

`validate_zap_request` screened relay hostnames as strings and parsed them
with `ipaddress.ip_address`. Two classes of relay URL survived screening but
still reach private addresses:

1. **Alternate IP notations.** `127.1`, `2130706433`, `0177.0.0.1` and
   `0x7f.1` fail `ipaddress.ip_address`, were treated as ordinary hostnames,
   and passed every string check. The OS resolver (`inet_aton` semantics)
   maps all of them to `127.0.0.1`, so `websockets.connect` reached loopback.
2. **DNS names resolving to private space.** Only the hostname string was
   inspected; nothing resolved it, so a name pointing at `127.0.0.1`,
   RFC1918 space, or link-local addresses (including cloud metadata
   endpoints) passed validation.

Reachable by unauthenticated users: craft a kind 9734 zap request against
any nostr-enabled goal with a hostile `relays` tag, request the invoice via
the LNURL-pay callback, and pay it (1 sat). On settlement,
`publish_zap_receipt` opened a WebSocket from the LNbits server to the
attacker-chosen address, sent the zap receipt (including `bolt11` and the
payment `preimage`), and read one response — a send-capable blind SSRF
primitive against the host's internal network.

Fix applied:

- `_is_shorthand_ip` rejects anything `socket.inet_aton` parses but
  `ipaddress.ip_address` does not, so alternate IP notations can no longer
  pass as hostnames during validation.
- `_assert_public_relay` re-runs the URL checks and resolves the hostname
  immediately before connecting, requiring every resolved address to be
  globally routable. This also covers DNS changes between invoice creation
  (when validation ran) and payment settlement.

Pinned by `test_relay_validation_rejects_alternate_loopback`,
`test_publisher_never_contacts_private_addresses` and
`test_relay_validation_accepts_public_relays`.

### ZG-02 — `escapeHtml` not attribute-safe; unescaped inline handlers (Low, fixed)

Both embeds escaped text with `textContent` → `innerHTML`, which escapes
`&`, `<` and `>` but **not quotes**, while the widget used the result inside
`data-copy="..."` attribute context. The iframe page interpolated
`goal.lightning_address` and `invoice.payment_request` directly into inline
`onclick="window.__zgCopy('...')"` handlers with no escaping at all. Both
were safe only because the values happen to be server-validated (username
regex, BOLT11 alphabet) — one field change away from XSS executing on the
LNbits origin, where it could reach same-origin session resources.

Fix applied: `escapeHtml` in both `EMBED_HTML` and `WIDGET_JS` now escapes
`"` and `'` as well, and the iframe copy buttons use `data-copy` attributes
wired with `addEventListener`, matching the widget pattern. No user data
flows into inline event handlers anymore.

Pinned by `test_embed_escapehtml_escapes_quotes` and
`test_embed_copy_buttons_avoid_inline_handlers`.

### ZG-03 — Unauthenticated invoice creation without rate limiting (Low, open)

`POST /api/v1/goals/{goal_id}/invoice` and `GET /api/v1/lnurl/cb/{goal_id}`
intentionally allow anonymous use (LNURL protocol requirement) and have no
per-IP or per-goal cap, so they can be spammed to load the Lightning backend
and grow database rows. Unpaid contribution rows older than the 10-minute
invoice expiry are purged before each issuance, which bounds that table.
Recommend a per-goal/per-IP limit at this extension or a gateway-level
limiter in front of LNbits.

### ZG-04 — Invoice data sent to third-party QR service; CDN script (Low, open)

The QR code is fetched from `https://api.qrserver.com` with the full BOLT11
invoice as a query parameter — disclosing the memo (goal title) and amount to
a third party. `bitcoin-connect` is imported live from `https://esm.sh`
(version-pinned, which is good), but a CDN or package compromise would
execute on the LNbits origin in the iframe page. Self-hosting QR generation
and vendoring the dependency would remove both external dependencies.

### ZG-05 — Scheduler proxy uses admin key for invoice-key callers (Info, accepted)

`api_scheduler_status` requires only an invoice key but forwards the
wallet's admin key to the local scheduler API; only zapgoals job metadata is
surfaced, so exposure is minimal. `api_setup_scheduler` persists the admin
key in a scheduler job header, which is same-privilege storage (scheduler
job listings require an admin key). Both assume the scheduler shares the
LNbits host (`http://localhost:5000`); document this deployment assumption.

### ZG-06 — Plaintext extension Nostr key; sweep crash window (Info, accepted)

The extension-wide Nostr key is stored unencrypted in
`zapgoals.settings`; it only signs zap receipts and holds no funds. In
`sweep_recurring_goal`, a crash between `pay_invoice` and `complete_sweep`
leaves the period unrecorded, and the retry after the stale-lock timeout
would move the sats again — an owner-to-owner double transfer within the
same user's wallets, not attacker-exploitable, but worth noting for
accounting reconciliation.

## Verified as solid

- **Authorization:** admin key for writes, invoice key for reads,
  ownership checks on every wallet-scoped route; public endpoints are
  limited to goal presentation, invoice creation, and LNURL flows.
- **SQL:** all queries are parameterized; the only f-string fragments are
  server-side placeholder names (`db.timestamp_placeholder`).
- **Input validation:** colors are `#RRGGBB`-regex checked (CSS injection
  blocked), fonts and font names are whitelisted, Lightning Address
  usernames and nostr pubkeys are regex-validated, NUL bytes are rejected,
  amounts are bounded (1–2_100_000_000 sats), comments capped at 280 chars.
- **Settlement integrity:** `settle_contribution` uses a conditional
  `UPDATE ... WHERE paid = false` with a rowcount check, making concurrent
  settlement of the same payment hash idempotent and preventing double
  counting.
- **Sweep safety:** atomic lock acquisition via conditional update, stale
  lock clearing, balance checks before payment, per-goal failure isolation,
  and a `UNIQUE (goal_id, period_index)` ledger constraint.
- **XSS in the SPA:** `public.vue` renders with `v-text`; no `v-html`
  anywhere; contribution comments are never rendered back.
- **Mass assignment:** `update_goal` preserves `id`, `wallet`,
  `current_amount`, `created_at` and period bookkeeping fields.
- **Secrets:** none in the repository, configuration, or git history;
  `data/` is gitignored.

## Residual risks

- A DNS rebinding window of a few milliseconds remains between the
  resolution check in `_assert_public_relay` and `websockets.connect`
  resolving again internally. Fully closing it would require connecting by
  the verified IP with SNI/Host overrides, which the `websockets` API does
  not support cleanly; the layered checks make this impractical to exploit.
- Relay validation is string-level at invoice time by design; the
  enforcement point for resolved addresses is publish time.
- ZG-03 and ZG-04 remain open advisories; both are deployment-context
  decisions rather than code defects.
