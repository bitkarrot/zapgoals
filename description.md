# ZapGoals

ZapGoals lets LNbits users create branded public fundraising pages with a satoshi target, deadline, live progress bar, descriptive text, configurable colors and fonts, and suggested contribution amounts.

Supporters can contribute through Bitcoin Connect or standard BOLT11 invoices and QR codes. Each settled contribution updates every open goal page in realtime. Goal totals include only invoices issued for that goal, not unrelated activity in the receiving wallet.

## Features

- Public goal pages with targets, deadlines, countdowns, and realtime updates
- One to four configurable suggested zap amounts plus custom amounts and comments
- Bitcoin Connect wallet connections and standard Lightning invoice payments
- Custom colors, typography, titles, and text above or below the progress bar
- Public goal and invoice APIs for alternate frontends
- LNURL-pay endpoints and optional per-goal Lightning Addresses
- NIP-57 zap request validation and signed zap receipt publication
- Safe cancellation of partially funded goals without deleting LNbits payment history

Lightning Addresses require the ZapGoals well-known redirect to be enabled at the server and cannot share that route with another Lightning Address extension. Nostr zaps require the recipient's 64-character hexadecimal public key. See the [setup guide](https://github.com/bitkarrot/zapgoals#lightning-address-and-nostr-setup) for details.

Created by [bitkarrot](https://github.com/bitkarrot). Source code and releases are available at [github.com/bitkarrot/zapgoals](https://github.com/bitkarrot/zapgoals).
