# ZapGoals agent notes

## Critical constraint: no new Python dependencies

LNbits does **not** install Python dependencies for extensions at install
time. Anything in `pyproject.toml` `dependencies` beyond `lnbits` itself must
already exist in the LNbits environment, or the extension fails to import
(`ModuleNotFoundError`) on stock installs. This broke v0.1.7, which added
`qrcode`. Use packages LNbits already depends on (e.g. `pyqrcode` for QR,
`pynostr`, `websockets`, `httpx`) — see LNbits' own `pyproject.toml`.

## Checks

- `make check` must pass: ruff, black, mypy, pyright (needs `npm install`
  for prettier/pyright), prettier.
- `make test` runs pytest (95+ tests; `tests/test_security_review.py` pins
  the SECURITY_REVIEW.md findings and must stay passing).
- mypy/pyright need an override entry for any untyped import (see
  `[[tool.mypy.overrides]]` in `pyproject.toml`).
- The embedded JS lives inside Python strings in `embed.py` — E501/RUF001
  are ignored there on purpose. Syntax-check the served JS with
  `node --check` after editing it.

## Release process

1. Bump `version` in `config.json`, `package.json`, `pyproject.toml`;
   commit "Release ZapGoals vX.Y.Z".
2. Create annotated tag `vX.Y.Z` and push main + tag.
3. Download
   `https://github.com/bitkarrot/zapgoals/archive/refs/tags/vX.Y.Z.zip`
   and compute its sha256 — GitHub tag zips are what LNbits downloads.
4. Update `version`, `archive`, `hash` in `extensions.json`; commit
   "Publish ZapGoals vX.Y.Z in extension manifest"; push.
