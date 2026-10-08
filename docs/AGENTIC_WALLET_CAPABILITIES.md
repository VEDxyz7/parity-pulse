# Agentic Wallet capability matrix — Master Phase 9

Verified date: October 8, 2026 (Asia/Kolkata). Mechanism: official Binance Skills Hub
`binance-agentic-wallet` 1.12.0 / required `@binance/agentic-wallet` CLI 1.10.0.
[Official manifest](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/SKILL.md),
[preflight](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/preflight.md).

The local PATH lookup returned no `baw`. Global npm inventory returned no matching package.
Node v24.12.0 is present. Candidate configuration directories were absent; this is not an
exhaustive disk/session search. No installation, pairing, authentication or wallet mutation
was performed. The opt-in diagnostic returned `UNAVAILABLE / BAW_UNAVAILABLE`.
[Actual capability evidence](evidence/PHASE_9_CAPABILITIES.json).

Documentation verification, synthetic protocol verification and actual authenticated access
are separate evidence levels. **No real wallet capability is marked PASS.**

| Capability | Current actual status | Verified mechanism | Mode | Evidence | Limitation |
|---|---|---|---|---|---|
| Wallet status | UNAVAILABLE | `baw wallet status --json` | LIVE_READ_ONLY | DOC + fixture tests; actual runtime missing | CONNECTED must be observed; no auto-authentication |
| Address | UNAVAILABLE | `baw wallet address --json` | LIVE_READ_ONLY | DOC + fixture tests | Exact BSC address required; no invented address |
| Balances | UNAVAILABLE | `baw wallet balance --binanceChainId 56 --json` | LIVE_READ_ONLY | DOC + fixture tests | Human units; omitted small holdings and no provider observation time |
| Supported chains | NOT_VERIFIED locally | `baw wallet chains --json` | LIVE_READ_ONLY | DOC + fixtures include unsupported BSC | Runtime list governs BSC support |
| Security settings | UNAVAILABLE | `baw wallet settings --json` | LIVE_READ_ONLY | DOC + malformed/limit tests | Session, market quota and Developer Mode quota kept separate |
| Daily limits / quota | UNAVAILABLE | Same settings read | LIVE_READ_ONLY | DOC + independent-limit tests | Reset timezone not documented; no live quota certificate |
| Token scope | NOT_VERIFIED locally | Settings `tradeAllTokens` | LIVE_READ_ONLY | DOC + scope rejection tests | Restricted allowlist not exposed; false blocks preparation checks |
| Confirmation / pending lock | UNAVAILABLE | `baw wallet tx-lock --binanceChainId 56 --json` | LIVE_READ_ONLY | DOC + lock/pending tests | Does not establish transaction-specific App confirmation |
| Transaction history | UNAVAILABLE | `baw wallet tx-history ... --json` | LIVE_READ_ONLY | DOC + bounded-page/identity tests | Corroboration only; no exact settlement certificate |
| Market orders / status | UNAVAILABLE | `baw market-order list ... --json` | LIVE_READ_ONLY | DOC + pending/terminal/unknown tests | No orders placed; FINISHED alone cannot confirm Phase 8 settlement |
| Indicative quote | NOT_VERIFIED locally | `baw market-order quote ... --json` | LIVE_READ_ONLY | DOC + exact human-unit fixture tests | Lacks external quote ID/address binding; cannot replace Phase 8 build |
| Tokenized-stock skill | NOT_VERIFIED locally | Official tokenized-securities information skill | Read-only information | DOC review only | Provider-description discrepancy; no account/token execution support proved |
| DRY_RUN integration | FIXTURE_VERIFIED | AgenticWalletAdapter → AgenticWalletCliGateway → existing Phase 8 checks | DEMO / DRY_RUN | Automated tests + synthetic evidence | Always non-executable; real wallet read preflight unavailable |
| LIVE / signing / broadcast | BLOCKED | No executor or mutation transport implemented | Disabled | Gate/configuration/transport tests | All LIVE gates blocked; equivalence/runtime/confirmation unresolved |

The [wallet-view reference](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/wallet-view.md)
defines status, identity, chain, balance, history and lock reads.
[Settings](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/wallet-setting.md)
are read-only and changed in the Binance App. [Market-order reference](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/market-order.md)
separates quotes, submissions and status. The application implements only reviewed reads.

## Discrepancies and explicit limits

- The welcome page lists four networks; the wallet-view example includes additional chains.
  Neither list proves current authenticated support. Use the actual `wallet chains` result.
- The [tokenized-securities skill](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-tokenized-securities-info/SKILL.md)
  describes Ondo/type=1, while the wallet manifest also describes type=2/type=3 provider lookup.
  These public information interfaces are not Agentic Wallet execution endpoints. Existing
  verified RWA discovery stays unchanged; no xStocks support is inferred.
- CLI balances have human quantities and indicative USD marks, but no documented observation
  timestamps/decimals. Verified existing token metadata supplies decimals. CLI marks are not
  independent equity references and are not used to manufacture fresh FundingState prices.
- Wallet settings expose quota dates without a reset timezone. A date match is only a conservative
  DRY_RUN check; the gateway separately reports reset semantics unverified for future live use.
- Ordinary quota and Developer Mode external-sign quota are independent. Both remain visible
  and are conservatively checked; one cannot substitute for the other.
- `NeedConfirmation` does not prove App confirmation occurred. It blocks wallet preflight without
  verified transaction-specific evidence. Host confirmation cannot waive that restriction.
- Market-order list examples omit actual received quantity. Wallet FINISHED/history-confirmed
  do not prove exact simulated settlement. Only the existing Phase 8 tracker can confirm an
  independently identified execution after its full binding checks; conflicts remain UNKNOWN.
- [External-sign documentation](https://github.com/binance/binance-skills-hub/blob/main/skills/binance-web3/binance-agentic-wallet/references/external-sign.md)
  describes preview/request-ID flows and no gas-price options. These previews/signatures/executions
  are not invoked or enabled here. Exact gas/nonce/transaction and RFQ settlement equivalence
  remain unverified. No remote Agentic Wallet REST interface is invented.

## Local read diagnostic

From the repository root:

```sh
.venv/bin/python scripts/inspect-wallet.py
# Explicitly opt into only installed official CLI reads:
.venv/bin/python scripts/inspect-wallet.py --read-only
```

Without the opt-in, worker reads are disabled. With it, missing `baw` returns an explicit
unavailable state. If installed on a controlled worker, the client first requires the reviewed
exact CLI version, then reads status/settings/chains/address/balance/lock/pending records and
rechecks identity. No command signs, places an order, authenticates or changes settings.
Output contains capability metadata only: no addresses, balances, raw settings, raw errors or secrets.
The application itself does not start a CLI worker or expose public wallet endpoints.

Installation and user-controlled App pairing are external prerequisites, not performed by this
diagnostic. A compatible official installation and session need fresh real read verification;
passing synthetic tests cannot turn on any LIVE gate.
