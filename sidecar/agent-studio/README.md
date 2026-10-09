# Parity Pulse × BNB Agent Studio sidecar

This sidecar runs on localhost only and needs Node 22 or later. It does two things:

- Executes rebalance legs through an **Altana** session key with on-chain permissions, so the
  Python `ALTANA` signer never holds a key.
- **Sells** the Parity Pulse parity signal over x402 to other agents.

```
npm ci
# 1) one-time: create the Altana wallet and grant a scoped session (BSC mainnet)
ALTANA_OWNER_PRIVATE_KEY=0x... ALTANA_SESSION_FILE=./altana-session.json \
SESSION_DAILY_USDT=50 SESSION_DAYS=3 node grant-session.mjs --register-agent
# fund the printed Altana wallet with USDT and a little BNB (the relay recovers gas from it)

# 2) run
ALTANA_SESSION_FILE=./altana-session.json SIDECAR_TOKEN=<16+ random chars> \
X402_PAY_TO=0xYourPayout X402_FACILITATOR_KEY=0xFundedGasKey X402_PRICE=10000000000000000 \
PARITY_API=http://127.0.0.1:8000 node server.mjs
```

Backend: `LIVE_SIGNER=ALTANA SIDECAR_TOKEN=<same>`, plus the live flags in `docs/LIVE_REBALANCE.md`.

Session permissions:
- Calls are allowed only to the Binance LiquidMesh router and to `approve()` on USDT and the
  configured stock tokens.
- Spending is capped at `SESSION_DAILY_USDT` USDT and `SESSION_DAILY_BNB` BNB per day.
- The session expires after `SESSION_DAYS` days.

To revoke the session, call `client.revokeSession` with the owner key.

Check the paywall with `curl -i localhost:8787/x402/parity/NVDA`, which returns `402` with
`accepts` for U and USDT on chain `eip155:56`.

Never commit `altana-session.json`. It contains the session private key.
