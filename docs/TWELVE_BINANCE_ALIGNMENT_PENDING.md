# Twelve Data / Binance alignment — manual diagnostic pending

**Status: MANUAL_RUN_PENDING; automatic waiting job STOPPED. No measured alignment result yet.** Preparation and scheduling occurred on October 7, 2026, around 03:00 IST. The US regular session was closed. The verified calendar's next open is October 7, 19:00 IST (13:30 UTC).

The intended manual run is **October 7, 19:02 IST (13:32 UTC)**. Its normal ten-round run takes about three minutes. Before cancellation, the job was running and waiting, with zero provider calls, zero real pairs and an empty error log. At the user's request, the exact command and configuration assumptions were saved in the [manual runbook](TWELVE_BINANCE_ALIGNMENT_RUNBOOK.md) before stopping the job. Stop verification at **October 7, 03:10:04 IST (October 6, 21:40:04 UTC)** confirmed the job was unregistered and its previous PID had exited. The script, job definition and logs remain intact. No automatic run remains scheduled by this job, and the diagnostic was not run during cancellation.

## Fixed read-only scope

- Twelve Data: `GET https://api.twelvedata.com/quote`, `symbol=NVDA`, `interval=1min`, `timezone=UTC`, `prepost=false`, `dp=11`.
- Binance: `POST https://web3.binance.com/build/api/v1/dex/market/price`, a **read-only market-data operation**, batch body containing the two already verified BSC chain56 contracts.
- BStock NVDAB: `0x02fca66c1d1afb4e2a7884261eb00f63598a7436`.
- Ondo NVDAon: `0xa9ee28c80f960b889dfbd1902055218cba016f75`.

The [official Binance contract](https://web3.binance.com/en/dev-docs/catalog/web3-wallet/api/rest-api/general-data) defines each row's `time` as the token-price observation time in Unix milliseconds. The response-envelope timestamp and local receipt time are not substitutes. Twelve Data's `last_quote_at` is used directly; its candle-start `timestamp` is excluded from alignment calculations. The previous [timestamp-semantics diagnostic](TWELVE_DATA_TIMESTAMP_SEMANTICS.md) and all accepted evidence are preserved.

## Sampling and reporting

Ten rounds start 17 seconds apart. Each round concurrently fetches one equity quote and one Binance batch covering both representations, yielding **ten pairs per representation and twenty comparisons overall**. No local cache replay, historical pairing or retry-until-aligned selection is allowed. The timing covers multiple minute updates without intentionally targeting only favorable alignments; it remains below the advertised Twelve Data minute quota.

Each round records the equity price, `last_quote_at`, `is_market_open`, receipt UTC and HTTP/business status. Each token records its actual `time`, USD/token price, receipt UTC and HTTP/business status. The script separately calculates absolute source-timestamp skew and receipt-time skew, retaining the exact Decimal seconds.

The diagnostic's PASS requires all ten rounds, both representations, real valid identities/prices/timestamps, active regular-session evidence, nonfuture source ages no greater than **120s**, and every pair's source skew no greater than **30s**. These are existing limits, unchanged. Missing data is unscorable and cannot pass; missing timestamps are never inferred. Within/outside counts, maximum and median are reported per representation and overall. A short sample cannot establish sustained reliability or pass the full Trust gate.

After the actual run, the script writes:

- `docs/evidence/TWELVE_BINANCE_NVDA_ALIGNMENT.json`: complete raw paired fields, receipt times, separate differences, status ledgers and statistics.
- `docs/TWELVE_BINANCE_ALIGNMENT.md`: all ten timestamp pairs per representation, summaries, `TWELVE_BINANCE_30S_ALIGNMENT=PASS/FAIL` and the bounded integration recommendation.

Neither output exists yet. **No max/median/count-of-aligned result is invented from zero measurements.** If the machine misses the regular-session window, the script refuses provider calls and reports `NOT_TESTED_MARKET_CLOSED` in its local log. Provider failures fail closed and are retained as unavailable/unscorable evidence.

## Scheduler and validation

The preserved historical job label is `com.paritypulse.diagnostic.alignment.20261007`; its previous PID was97606. The definition remains at `/private/tmp/parity-alignment-20261007.plist`, with `RunAtLoad=true` and **`KeepAlive=false`**, and explicit start time. It made no API calls during its wait. Logs remain at `/private/tmp/parity-alignment-20261007.log` and `/private/tmp/parity-alignment-20261007-error.log`; neither receives credentials or signatures. The job was stopped using `launchctl bootout gui/501/com.paritypulse.diagnostic.alignment.20261007`, without deleting these files. Both scheduler preflight jobs had already been removed. The retained definition is not registered or automatically reloaded.

Credentials are loaded from the existing protected project environment at observation time. No key/secret appears in program arguments, job definition, report or evidence. The existing Binance signer and protected read transport are reused; no production integration is created. [Isolated diagnostic script](../scripts/diagnose-twelve-binance-alignment.py).

Local 29.999/30/30.001-second boundary controls, missing-data, closed-session, stale/future-age rejection controls PASS. These are explicitly synthetic arithmetic controls, not real observations or Trust history. Actual closed-session invocation refused all network calls. Ruff lint/format PASS for72 Python files; existing security audit PASS for209 artifacts including this pending report. No production implementation or test behavior was changed; the application test suite was not rerun for this isolated preparation.

The pre-task manifest confirms **192 of193 pre-existing files unchanged**, including every production source and formal gate artifact. The sole changed path is `data/parity-pulse.db`: its modification time and latest Trust-assessment ingestion time are October6 21:26:19 UTC (October7 02:56:19 IST). The already running backend PID94450 holds this database open. The diagnostic runner never connects to a production database and has zero production writes; the existing database change was preserved, not reverted. A subsequent inspection used SQLite read-only mode. This is not counted as paired diagnostic evidence. The unchanged formal Trust gate SHA256 is `f84e8489a756df2924b9a21f5486d84d563c9270362f076e0463f6c79c8aabdd`.

**Production Trust logic, TRUST_GATE and every threshold remain unchanged.** Opportunity and all LIVE gates remain blocked. The isolated diagnostic now awaits manual execution using the saved runbook; no diagnostic provider request was made during this cancellation task. No execution, wallet or trading endpoint is permitted. No PASS/FAIL alignment claim is available until real regular-session pairs exist.
