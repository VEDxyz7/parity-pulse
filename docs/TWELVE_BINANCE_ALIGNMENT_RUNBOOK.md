# Manual Twelve Data / Binance alignment diagnostic

Run at approximately **19:02 IST on October 7, 2026**, equivalent to **13:32 UTC**. The US regular session opens at 19:00 IST that day. The automatic waiting job is being stopped; these instructions preserve the manual run. Do not run the diagnostic before the intended session.

## Exact manual command

Open a terminal at the intended time and run:

```sh
cd "/Users/vedparikh/Desktop/Parity Pulse"
.venv/bin/python scripts/diagnose-twelve-binance-alignment.py
```

Keep the Mac awake and online and leave the terminal running for approximately three minutes. The script checks the verified calendar and refuses provider calls outside the regular session. It also requires the equity provider to report an open market for eligible pairs.

The original waiting command is preserved below for reference. It waits until the specified time when started early; the manual command above should be used at 19:02 IST. Neither command was run as part of saving these instructions.

```sh
cd "/Users/vedparikh/Desktop/Parity Pulse"
.venv/bin/python scripts/diagnose-twelve-binance-alignment.py \
  --start-at "2026-10-07T13:32:00+00:00"
```

## Environment and configuration assumptions

- Use the existing project `.venv` with its installed dependencies and the existing supporting script `scripts/diagnose-free-providers.py`.
- Credentials must be available in the existing project-root `.env` or inherited shell environment: `TWELVE_DATA_API_KEY`, `BINANCE_WEB3_API_KEY`, and `BINANCE_WEB3_SECRET_KEY`. The runner reads them locally. Never put their values in commands, reports, logs, job definitions, screenshots or commits.
- Credentials need entitlement to the read-only endpoints below. Working Internet access and `data/calendar/nyse-2026-2028.json` are required.
- Preserve the project's non-live safety configuration: `DATA_MODE=LIVE_READ_ONLY`, `EXECUTION_MODE=DRY_RUN`, `APPROVAL_MODE=PROPOSE_ONLY`, `LIVE_TRADING_ENABLED=false`, `REQUIRE_SIMULATION=true`. This isolated runner uses credentials directly and fixed read-only endpoints; it does not enable production execution or require changing application configuration.
- Alignment remains **30 seconds** and freshness remains **120 seconds**. No threshold or gate is changed by this diagnostic.
- The two output paths below must not already exist. The script refuses to overwrite evidence. Preserve any previous capture rather than deleting it to rerun.

## Read-only scope and evidence

The existing [diagnostic script](../scripts/diagnose-twelve-binance-alignment.py) performs ten rounds spaced 17 seconds apart. Each round concurrently requests:

- Twelve Data `GET https://api.twelvedata.com/quote`, with `symbol=NVDA`, `interval=1min`, `timezone=UTC`, `prepost=false`, `dp=11`.
- Binance `POST https://web3.binance.com/build/api/v1/dex/market/price`, a read-only market-data batch for BSC chain `56`: BStock NVDAB `0x02fca66c1d1afb4e2a7884261eb00f63598a7436` and Ondo NVDAon `0xa9ee28c80f960b889dfbd1902055218cba016f75`.

This yields ten pairs per representation, twenty comparisons overall. Alignment uses Twelve Data `last_quote_at` and each Binance token row's actual `time` in milliseconds. Candle-start `timestamp`, envelope timestamps and receipt times are not substitutes. Receipt-time differences are reported separately.

The actual run writes only these diagnostic artifacts:

- `docs/evidence/TWELVE_BINANCE_NVDA_ALIGNMENT.json`
- `docs/TWELVE_BINANCE_ALIGNMENT.md`

Missing or invalid data cannot pass. No alignment result exists until real pairs are captured. No production observations are persisted, no execution/wallet/trading endpoint is called, and no Trust logic or gate is modified.

## Preserved scheduler setup

The stopped job's label is `com.paritypulse.diagnostic.alignment.20261007`. Its definition and logs are retained at:

- `/private/tmp/parity-alignment-20261007.plist`
- `/private/tmp/parity-alignment-20261007.log`
- `/private/tmp/parity-alignment-20261007-error.log`

These temporary files are retained for inspection, not automatically reloaded. Temporary storage may be cleaned by the operating system. The repository script and this runbook are the saved manual setup. See [the pending diagnostic record](TWELVE_BINANCE_ALIGNMENT_PENDING.md) for preparation evidence and verified stop status.
