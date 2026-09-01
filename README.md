# ZapGoals

ZapGoals is a standalone extension for LNbits 1.5 or newer. It creates public Lightning funding goals with customizable presentation, LNURL-pay support, optional Lightning Addresses, Nostr zap handling, and realtime progress updates.

## Install

In LNbits server settings, add `https://raw.githubusercontent.com/bitkarrot/zapgoals/main/extensions.json` to **Extension Manifests**. Restart LNbits, open **Manage Extensions**, install ZapGoals, and enable it for your user. A source installation may instead place this repository in the LNbits extensions directory and restart LNbits.

ZapGoals requires Python 3.10–3.12 and LNbits 1.5.0 or newer. LNURL-pay works without additional configuration. To let ZapGoals own `/.well-known/lnurlp` and issue Lightning Addresses, set `ZAPGOALS_ENABLE_LIGHTNING_ADDRESS=true`; leave it disabled when another extension such as LNURLp already owns that route.

## Use

1. Open ZapGoals and create a goal.
2. Select its receiving wallet, set the target amount and target date, then choose a payment mode.
3. Customize the goal colors and, if wanted, configure a Nostr public key and a unique username for a Lightning Address.
4. Publish or copy the public goal URL. The page updates when tagged contribution invoices settle.

The `vanilla` payment mode presents standard Lightning invoices, `nwc` enables the browser-based Nostr Wallet Connect flow, and `all` offers both. Contributors choose their amount when requesting an invoice or using LNURL-pay. Regardless of mode, only payments created for that goal count toward its progress.

Bitcoin Connect is loaded in the browser through a dynamically pinned import. It is intentionally not an npm build dependency.

## Public API

Routes are mounted below the extension's `/zapgoals` prefix:

- `GET /zapgoals/api/v1/goals/{goal_id}/public` returns public presentation settings, `goal_amount`, `current_amount`, `target_date`, status, percentage, and payment identifiers.
- `POST /zapgoals/api/v1/goals/{goal_id}/invoice` with `{"amount": 21}` creates a goal-tagged BOLT11 invoice.
- `GET /zapgoals/api/v1/lnurl/{goal_id}` and `GET /zapgoals/api/v1/lnurl/cb/{goal_id}` implement LNURL-pay and NIP-57 callbacks.
- `GET /.well-known/lnurlp/{username}` resolves an optional Lightning Address when the instance routes Lightning Addresses to this extension.
- `/api/v1/ws/{goal_id}` is the LNbits core WebSocket used as a realtime invalidation signal; clients should re-fetch the public endpoint after a message.

Authenticated goal management routes are listed in the running instance's OpenAPI schema.

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

## License

ZapGoals is original software licensed under the [MIT License](LICENSE).
