"""Session-only paper ledger; serialized snapshots, atomic fills and no external interfaces."""

from datetime import timedelta
from decimal import Decimal, localcontext
from threading import RLock

from app.config import ROOT_DIR
from app.models.demo_execution import artifact_id, digest
from app.models.demo_paper import (
    ExitFixture,
    PaperEvent,
    PaperExit,
    PaperFill,
    PaperLifecycle,
    PaperObservation,
    PaperOrder,
    PaperPnL,
    PaperPosition,
    PaperScorecard,
)
from app.models.risk import RiskInputs
from app.services.opportunity import rounded


def pnl(position, exit):
    with localcontext() as context:
        context.prec = 256
        gross = (exit.price_usd - position.entry_price_usd) * position.quantity
        costs = position.entry_costs_usd + exit.fees_usd + exit.gas_usd
        basis = position.entry_notional_usd + position.entry_costs_usd
        return PaperPnL(
            position_id=position.position_id,
            gross_pnl_usd=gross,
            costs_usd=costs,
            net_pnl_usd=gross - costs,
            return_pct=rounded((gross - costs) / basis * 100),
            entry_cost_basis_usd=basis,
        )


class DemoPaperLedger:
    """A DEMO app owns one ledger. Restart clears it; it never opens a database/file/socket.

    Records are canonical JSON snapshots so callers cannot mutate internal state. The
    lock spans risk checks and insertion: concurrent retries cannot create two fills.
    Refuse at capacity rather than evicting idempotency or financial history.
    """

    capacity = 64

    def __init__(self, preparation):
        self.preparation = preparation
        self.rows = {}
        self.transactions = {}
        self.lock = RLock()
        self.exit_fixture = ExitFixture.model_validate_json(
            (ROOT_DIR / "data/demo/paper/exit.json").read_bytes()
        )

    def _store(self, row):
        self.rows[row.position.position_id] = row.model_dump_json()
        self.transactions[row.order.transaction_id] = row.position.position_id
        return self.get(row.position.position_id)

    def get(self, position_id):
        with self.lock:
            if position_id not in self.rows:
                raise LookupError("Unknown paper position")
            return PaperLifecycle.model_validate_json(self.rows[position_id])

    def list(self):
        """Validated snapshots for the evaluator; no fill/exit or clock advance."""
        with self.lock:
            return tuple(self.get(key) for key in sorted(self.rows, key=str))

    def _mandate(self, now):
        core = self.preparation.flow
        base = core.fixture.risk_inputs
        cash = base.wallet_available_usd
        exposure, loss, trades, last = Decimal(0), Decimal(0), 0, base.last_trade_at
        with localcontext() as context:
            context.prec = 256
            for key in self.rows:
                row = self.get(key)
                p = row.position
                # The fixture is one fixed synthetic session, not a rolling live clock.
                cash -= p.entry_notional_usd + p.entry_costs_usd
                if p.state == "OPEN":
                    cash -= p.reserved_usd
                    exposure += row.quote.base_notional_usd
                else:
                    cash += row.exit.notional_usd - row.exit.fees_usd - row.exit.gas_usd
                    if row.exit.exited_at.date() == now.date():
                        loss += max(Decimal(0), -row.pnl.net_pnl_usd)
                if p.entered_at.date() == now.date():
                    trades += 1
                last = max(last, p.entered_at) if last is not None else p.entered_at
            return RiskInputs.model_validate(
                {
                    **base.model_dump(),
                    "wallet_available_usd": max(Decimal(0), cash),
                    "existing_exposure_usd": base.existing_exposure_usd + exposure,
                    "daily_loss_usd": base.daily_loss_usd + loss,
                    "trades_today": base.trades_today + trades,
                    "last_trade_at": last,
                }
            )

    def fill(self, transaction_id, simulation_id):
        with self.lock:
            if transaction_id in self.transactions:
                existing = self.get(self.transactions[transaction_id])
                if existing.order.simulation_id != simulation_id:
                    raise ValueError("Retry must identify the original simulation proof")
                return existing
            if len(self.rows) >= self.capacity:
                raise ValueError("Paper ledger capacity reached; history is not evicted")
            d = self.preparation
            proof, _ = d.flow._read(d.simulations, simulation_id)
            prepared, elapsed = d.flow._read(d.transactions, transaction_id)
            tx = prepared.transaction
            quoted, _ = d.flow._read(d.quotes, tx.quote_id)
            q = quoted.quote
            now = tx.prepared_at + elapsed
            if (
                proof.simulation.status != "SIMULATION_PASS"
                or proof.simulation.transaction_id != transaction_id
                or proof.simulation.transaction_fingerprint != tx.fingerprint
                or not proof.simulation.evaluated_at <= now < proof.simulation.valid_until
                or prepared.risk_revalidation.status != "PASS"
                or quoted.risk_revalidation.status != "PASS"
            ):
                raise ValueError("A matching current simulation and approved Risk are required")
            current = d.quote_service.quoted_opportunity(
                quoted.opportunity, q, current_inputs=d.flow.fixture.economics
            )
            risk = d.flow.risk_engine.evaluate(
                current, self._mandate(now), d.flow.fixture.risk_policy, now=now
            )
            simulation = d.simulation_service.simulate(
                tx,
                q,
                risk,
                d.flow.sandbox.datasets[quoted.scenario_id].token.record,
                context_sha256=d.context(quoted.scenario_id),
                now=now,
            )
            if simulation.status != "SIMULATION_PASS":
                raise ValueError("Current paper risk/local constraints failed; no fill created")
            if quoted.scenario_id != self.exit_fixture.scenario_id:
                raise ValueError("No explicit synthetic exit fixture for this scenario")
            trust, _ = d.flow._read(d.flow.trust_results, current.trust_assessment_id)
            order_id = artifact_id("paper-order", tx.fingerprint)
            fill_id = artifact_id("paper-fill", tx.fingerprint)
            position_id = artifact_id("paper-position", tx.fingerprint)
            fill = PaperFill(
                fill_id=fill_id,
                order_id=order_id,
                filled_at=now,
                quantity=q.output_token_quantity,
                price_usd=q.execution_price_usd,
                notional_usd=q.input_amount_usd,
                fees_usd=q.fees_usd,
                gas_usd=q.gas_usd,
                reserve_usd=q.execution_buffer_usd,
            )
            with localcontext() as context:
                context.prec = 256
                costs = q.fees_usd + q.gas_usd
            row = PaperLifecycle(
                scenario_id=quoted.scenario_id,
                order=PaperOrder(
                    order_id=order_id,
                    transaction_id=transaction_id,
                    quote_id=q.quote_id,
                    simulation_id=simulation_id,
                    opportunity_id=current.opportunity_id,
                    risk_id=risk.risk_id,
                    created_at=now,
                ),
                fill=fill,
                position=PaperPosition(
                    position_id=position_id,
                    fill_id=fill_id,
                    ticker=q.ticker,
                    issuer=q.issuer,
                    token=q.contract,
                    quantity=fill.quantity,
                    entry_price_usd=fill.price_usd,
                    entry_notional_usd=fill.notional_usd,
                    entry_costs_usd=costs,
                    reserved_usd=fill.reserve_usd,
                    entered_at=now,
                    state="OPEN",
                ),
                events=[
                    PaperEvent(
                        event_id=artifact_id("entry-event", tx.fingerprint),
                        position_id=position_id,
                        kind="ENTRY",
                        occurred_at=now,
                        reference_id=fill_id,
                    )
                ],
                opportunity=current,
                risk=risk,
                quote=q,
                preparation=tx,
                simulation=proof.simulation,
                fill_revalidation=simulation,
                trust_reason_codes=trust.assessment.representations[0].reason_codes,
                exit_fixture=self.exit_fixture,
            )
            return self._store(row)

    def monitor(self, position_id):
        with self.lock:
            row = self.get(position_id)
            if row.position.state != "OPEN":
                raise ValueError("Only OPEN positions may be monitored")
            if row.observation is not None:
                return row
            f = row.exit_fixture
            with localcontext() as context:
                context.prec = 256
                price = f.token_mark_price_usd * (1 - f.slippage_bps / Decimal(10000))
            observation_id = artifact_id("paper-observation", digest(f) + str(position_id))
            observation = PaperObservation(
                observation_id=observation_id,
                position_id=position_id,
                observed_at=row.position.entered_at + timedelta(seconds=f.seconds_after_entry),
                token_mark_price_usd=f.token_mark_price_usd,
                sell_price_usd=price,
                fees_usd=f.fees_usd,
                gas_usd=f.gas_usd,
                fixture_sha256=digest(f),
                description=f.description,
            )
            event = PaperEvent(
                event_id=artifact_id("monitor-event", str(observation_id)),
                position_id=position_id,
                kind="MONITOR",
                occurred_at=observation.observed_at,
                reference_id=observation_id,
            )
            return self._store(
                PaperLifecycle.model_validate(
                    {
                        **row.model_dump(),
                        "observation": observation,
                        "events": [*row.events, event],
                    }
                )
            )

    def exit(self, position_id, observation_id):
        with self.lock:
            row = self.get(position_id)
            p, o = row.position, row.observation
            if p.state != "OPEN" or o is None or o.observation_id != observation_id:
                raise ValueError("Exit requires an OPEN position and its monitored observation")
            if o.observed_at <= p.entered_at:
                raise ValueError("Synthetic exit must follow entry")
            with localcontext() as context:
                context.prec = 256
                notional = p.quantity * o.sell_price_usd
            exit = PaperExit(
                exit_id=artifact_id("paper-exit", str(observation_id)),
                position_id=position_id,
                observation_id=observation_id,
                exited_at=o.observed_at,
                quantity=p.quantity,
                price_usd=o.sell_price_usd,
                notional_usd=notional,
                fees_usd=o.fees_usd,
                gas_usd=o.gas_usd,
                released_reserve_usd=p.reserved_usd,
            )
            position = PaperPosition.model_validate(
                {
                    **p.model_dump(),
                    "state": "EXITED",
                    "exited_at": o.observed_at,
                }
            )
            event = PaperEvent(
                event_id=artifact_id("exit-event", str(exit.exit_id)),
                position_id=position_id,
                kind="EXIT",
                occurred_at=o.observed_at,
                reference_id=exit.exit_id,
            )
            return self._store(
                PaperLifecycle.model_validate(
                    {
                        **row.model_dump(),
                        "position": position,
                        "exit": exit,
                        "pnl": pnl(position, exit),
                        "events": [*row.events, event],
                    }
                )
            )

    def scorecard(self, position_id):
        row = self.get(position_id)
        if row.position.state != "EXITED":
            raise ValueError("A scorecard requires an exited paper position")
        return PaperScorecard(
            scenario_id=row.scenario_id,
            position_id=position_id,
            trust_assessment_id=row.opportunity.trust_assessment_id,
            trust_classification=row.opportunity.source_trust_classification,
            entry=row.fill,
            exit=row.exit,
            pnl=pnl(row.position, row.exit),
            event_ids=[e.event_id for e in row.events],
            reason_codes=[
                *row.trust_reason_codes,
                *row.opportunity.reason_codes,
                *row.risk.reason_codes,
                *row.simulation.reason_codes,
            ],
            confidence=row.opportunity.confidence,
            evidence_quality=row.opportunity.evidence_quality,
            quote_id=row.quote.quote_id,
            transaction_id=row.preparation.transaction_id,
            simulation_id=row.simulation.simulation_id,
            risk_id=row.risk.risk_id,
        )
