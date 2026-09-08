# ZapGoals

<img width="160" height="160" alt="ZapGoals" align="right" src="https://github.com/user-attachments/assets/e4202ca3-f777-4d89-9384-a9cdd9c1d3c5" /><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-labelledby="title desc">
<defs>
<linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#312e81"/>
<stop offset="1" stop-color="#7c3aed"/>
</linearGradient>
<linearGradient id="bolt" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#fde047"/>
<stop offset="1" stop-color="#f59e0b"/>
</linearGradient>
</defs>
<rect width="256" height="256" rx="48" fill="url(#background)"/>
<circle cx="128" cy="128" r="78" fill="none" stroke="#ffffff" stroke-opacity=".22" stroke-width="18"/>
<path d="M128 50a78 78 0 0 1 72.6 106.4" fill="none" stroke="#2dd4bf" stroke-width="18" stroke-linecap="round"/>
<circle cx="128" cy="128" r="50" fill="#201b57" fill-opacity=".88"/>
<path d="M142 62 89 139h35l-12 56 56-85h-36z" fill="url(#bolt)" stroke="#fff7c2" stroke-width="4" stroke-linejoin="round"/>
<circle cx="201" cy="157" r="9" fill="#2dd4bf" stroke="#d5fffa" stroke-width="4"/>
</svg>

ZapGoals is a standalone extension for LNbits 1.5 or newer. It creates public Lightning funding goals with customizable presentation, LNURL-pay support, optional Lightning Addresses, Nostr zap handling, and realtime progress updates.

## Install

In LNbits server settings, add `https://raw.githubusercontent.com/bitkarrot/zapgoals/main/extensions.json` to **Extension Manifests**. Restart LNbits, open **Manage Extensions**, install ZapGoals, and enable it for your user. A source installation may instead place this repository in the LNbits extensions directory and restart LNbits.

ZapGoals requires Python 3.10–3.12 and LNbits 1.5.0 or newer. LNURL-pay works without additional configuration. To let ZapGoals own `/.well-known/lnurlp` and issue Lightning Addresses, set `ZAPGOALS_ENABLE_LIGHTNING_ADDRESS=true`; leave it disabled when another extension such as LNURLp already owns that route.

## Use

1. Open ZapGoals and create a goal.
2. Select its receiving wallet, set the target amount and target date, then choose a payment mode.
3. Customize the goal colors and, if wanted, configure a Nostr public key and a unique username for a Lightning Address.
4. Publish or copy the public goal URL. The page updates when tagged contribution invoices settle.

The `vanilla` payment mode presents standard Lightning invoices, while `all` also enables Bitcoin Connect and its supported wallet connectors. Creators can configure one to four suggested zap amounts; contributors can select one or enter a custom amount and optional comment. Regardless of mode, only payments created for that goal count toward its progress.

Bitcoin Connect is loaded in the browser through a dynamically pinned import. It is intentionally not an npm build dependency.

## Lightning Address and Nostr setup

### Lightning Address

Every goal has a direct LNURL-pay endpoint at `/zapgoals/api/v1/lnurl/{goal_id}`. To additionally give a goal a human-readable Lightning Address such as `june@example.com`:

1. Set `ZAPGOALS_ENABLE_LIGHTNING_ADDRESS=true` in the LNbits server environment and restart LNbits.
2. Enter a unique lowercase **Lightning Address username** in the goal form.
3. Ensure no other extension owns `/.well-known/lnurlp`. LNbits permits only one extension to handle Lightning Addresses, so ZapGoals cannot enable this redirect alongside an active LNURLp extension.

When a wallet resolves the address, ZapGoals returns an LNURL-pay callback that creates an invoice tagged to that goal. A settled invoice increments the goal rather than using the receiving wallet's total balance.

### Nostr zaps

Enter the recipient's 64-character lowercase hexadecimal Nostr public key in the goal form. The field currently expects hex, not `npub`. ZapGoals then advertises `allowsNostr: true` from the goal's LNURL-pay endpoint.

A Nostr client sends a signed kind `9734` zap request to the callback. ZapGoals verifies its signature, recipient `p` tag, amount, and relay list before issuing a description-hash invoice. After settlement, ZapGoals increments the goal and publishes a signed kind `9735` receipt to the requested relays.

The recipient key entered on the goal and the ZapGoals receipt-signing key are different: the goal key identifies who is being zapped, while an extension-generated private key signs receipts. The signing private key stays in the extension database; only its public key is advertised.

Ordinary Bitcoin Connect, QR, and copied BOLT11 payments still increment the goal, but they produce NIP-57 receipts only when initiated through a valid Nostr zap request.

## Public API

Routes are mounted below the extension's `/zapgoals` prefix:

- `GET /zapgoals/api/v1/goals/{goal_id}/public` returns public presentation settings, `goal_amount`, `current_amount`, `target_date`, status, percentage, and payment identifiers.
- `POST /zapgoals/api/v1/goals/{goal_id}/invoice` with `{"amount": 21, "comment": "Great goal"}` creates a goal-tagged BOLT11 invoice.
- `GET /zapgoals/api/v1/lnurl/{goal_id}` and `GET /zapgoals/api/v1/lnurl/cb/{goal_id}` implement LNURL-pay and NIP-57 callbacks.
- `GET /.well-known/lnurlp/{username}` resolves an optional Lightning Address when the instance routes Lightning Addresses to this extension.
- `POST /zapgoals/api/v1/goals/{goal_id}/sweep` manually triggers a period-end sweep for a recurring goal (admin key).
- `POST /zapgoals/api/v1/recurring/sweep-due` sweeps all due recurring goals owned by the wallet (admin key). Intended as the scheduler target.
- `GET /zapgoals/api/v1/goals/{goal_id}/periods` returns the per-period ledger for a recurring goal (invoice key).
- `GET /zapgoals/api/v1/recurring/scheduler-status` reports which sweep trigger methods are active (admin key).
- `POST /zapgoals/api/v1/recurring/setup-scheduler` creates or updates a scheduler extension job for due-goal checks (admin key). The check frequency can be hourly, every six hours, daily, or weekly.
- `/api/v1/ws/{goal_id}` is the LNbits core WebSocket used as a realtime invalidation signal; clients should re-fetch the public endpoint after a message.

Authenticated goal management routes are listed in the running instance's OpenAPI schema. Goal and direct invoice amounts use satoshis; LNURL callback amounts use millisatoshis; target dates are normalized to UTC. Public invoices expire after 10 minutes, expired unpaid tracking rows are removed during subsequent invoice creation, and requests remain subject to the LNbits server-wide rate limit.

## Recurring goals

A recurring goal reuses the same goal ID, public URL, LNURL endpoint, and Lightning Address across multiple funding periods. At each period end, settled sats are swept to a target wallet and the progress counter resets for the next period.

### Setup

1. Create a goal and enable the **Recurring goal** toggle.
2. Choose a recurrence unit (daily, weekly, monthly, quarterly, semi-annual, or annual) and interval (e.g. every 1 month).
3. For monthly recurrence, optionally set a day of month (clamped to the last day of short months).
4. Select a **target wallet** — an internal LNbits wallet on the same instance that will receive swept sats via a feeless internal transfer.
5. Choose a **sweep mode**:
   - **Target amount** — moves `min(zapped, goal_amount)`. Excess sats roll over.
   - **Entire amount** — moves everything zapped this period. No rollover.
6. Choose a **rollover mode**:
   - **Count excess as progress** — the next period starts with the rollover as its initial `current_amount`.
   - **Reset to zero** — the counter drops to 0 each period (excess sats remain in the goal wallet).

The goal's receiving wallet should be **dedicated** to that recurring goal. The sweep moves sats from the goal wallet's actual balance, so if the wallet is shared or has manual withdrawals, the sweep will fail with an insufficient balance error rather than silently underpaying.

### Example

A monthly goal with a 10,000 sat target and `target_amount` sweep mode receives 10,200 sats in January. At period end:

- 10,000 sats are moved to the target wallet (feeless internal transfer).
- 200 sats roll over. With `counts_as_progress` mode, February starts at 200/10,000 (2%). With `reset_to_zero` mode, February starts at 0/10,000 and the 200 sats remain in the goal wallet.

If only 7,000 sats were zapped, `min(7000, 10000) = 7000` is moved and nothing rolls over.

### Scheduling sweeps

Sweeps are triggered automatically by sending an HTTP request to the `sweep-due` endpoint. Two options:

**Option A — LNbits scheduler extension (recommended):** Install the [scheduler](https://github.com/bitkarrot/scheduler) extension and create or update a cron job that sends `POST /zapgoals/api/v1/recurring/sweep-due` with an admin key header. ZapGoals decides which goals are due; the check can run hourly, daily, weekly, or monthly. The admin panel's scheduler setup control defaults to a daily check and updates the existing ZapGoals job instead of creating duplicates.

**Option B — Built-in fallback loop:** Set `ZAPGOALS_BUILTIN_SCHEDULER=true` in the LNbits server environment. ZapGoals runs an internal loop that checks for due goals every `ZAPGOALS_SCHEDULER_INTERVAL_SECONDS` seconds (default 3600). Set that variable to change the interval; no extra extension is needed.

Sweeps can also be triggered manually per goal from the ZapGoals admin panel (the sweep button) or via `POST /zapgoals/api/v1/goals/{goal_id}/sweep`.

### Period history

Each completed period is recorded in a ledger accessible via `GET /zapgoals/api/v1/goals/{goal_id}/periods` and in the admin panel (the history button). Each row records the period index, start/end dates, total zapped, amount moved to the target wallet, rollover, and sweep timestamp.

## Embedding a goal on an external website

Any ZapGoal can be embedded on an external website using one of two methods. The embed dialog (accessible via the **Embed** button in the admin panel) lets you choose between them and copy the snippet.

### JS widget (recommended)

A `<script>` tag that injects a Shadow DOM widget directly into your page. Bitcoin Connect works natively because the script runs in your page's first-party context — `localStorage` and popups are not restricted.

```html
<script
  src="https://your-lnbits.example.com/zapgoals/embed.js"
  data-goal="{goal_id}"
  async
></script>
```

The script auto-detects the LNbits server URL from its own `src` attribute. It creates a container element, attaches a Shadow DOM (for CSS isolation from your page), and renders the full goal card with all features: live progress, countdown, zap button, invoice QR, and Bitcoin Connect.

### Iframe (simple)

Renders the goal in an iframe. Simpler but Bitcoin Connect may not work due to browser security restrictions on `localStorage` in cross-origin iframes (Safari blocks this by default). Falls back to QR-only with an "Open full page" link when Bitcoin Connect fails.

```html
<iframe
  src="https://your-lnbits.example.com/zapgoals/{goal_id}/embed"
  style="width:100%;max-width:500px;height:600px;border:0;border-radius:1rem;"
  loading="lazy"
  title="ZapGoal"
></iframe>
```

### What the embed shows

Both methods display the same content as the public page: goal title, descriptions, progress bar with live updates, current/goal amounts, countdown timer, recurring period badge (if applicable), zap button with suggested amounts, custom amount input, BOLT11 invoice QR code, and Bitcoin Connect (if enabled on the goal). Lightning Address and Nostr badge are also shown when configured.

### Technical notes

- Both methods use the public API (`GET /goals/{id}/public`, `POST /goals/{id}/invoice`) and WebSockets (`/api/v1/ws/{goal_id}`) for live updates — no authentication required.
- CORS is permissive on LNbits by default, so cross-origin embedding works without additional configuration.
- The JS widget uses Shadow DOM for complete CSS isolation — your page's styles won't affect the widget and vice versa.
- The iframe auto-resizes to fit the card content via `postMessage`.
- The JS widget is served at `/zapgoals/embed.js` and the iframe page at `/zapgoals/{goal_id}/embed`.

## NIP-57

An LNURL callback may receive a NIP-57 `nostr` zap request. ZapGoals validates supported zap request data and binds it to the generated invoice. When the tagged invoice settles, the extension can process the contribution as a Nostr-aware zap. Ordinary LNURL-pay clients remain supported; configuring a Nostr public key does not turn unrelated wallet payments into zaps.

## Security and accounting

Goal progress is **not** the total balance of the receiving wallet. It is the sum of settled invoices created and tagged for that goal. Keep LNbits admin and wallet keys private, expose only public goal/LNURL endpoints, use HTTPS, and treat public goal and Lightning Address usernames as discoverable identifiers.

## Development

Install Python development tools with `uv sync --group dev` and the pinned formatting/type-checking tools with `npm install`. Then use:

```sh
make format
make check
make test
```

## Project

Created by [bitkarrot](https://github.com/bitkarrot). Source code and releases are available in the [ZapGoals GitHub repository](https://github.com/bitkarrot/zapgoals).

## License

ZapGoals is original software licensed under the [MIT License](LICENSE).
