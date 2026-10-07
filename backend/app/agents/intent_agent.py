"""Explicit bounded grammar first; ambiguous mandates abstain rather than infer finance."""

import re
from decimal import Decimal

from app.agents.schemas import IntentOutput, Mandate
from app.services.intent import parse_intent

OPPORTUNITY = re.compile(
    r"i have \$(?P<budget>[0-9]{1,7}(?:\.[0-9]{1,2})?)"
    r"(?:[.;]?\s*(?:and )?(?:i )?(?:can lose up to|have a risk budget of|risk budget) "
    r"\$(?P<risk>[0-9]{1,7}(?:\.[0-9]{1,2})?))?[.;]?\s*"
    r"(?:find (?:me )?(?:an|the best) opportunity|no stock preference[.;]?\s*find "
    r"(?:me )?(?:an|the best) opportunity)\s+"
    r"(?P<window>before monday(?: open)?|before (?:the )?us market opens)\.?",
    re.I,
)
ALLOCATION = re.compile(
    r"keep (?:me at )?(?P<stocks>[0-9]{1,3})% (?:tokenized )?ai stocks "
    r"and (?P<cash>[0-9]{1,3})% cash\.?",
    re.I,
)
RISK_SUFFIX = re.compile(
    r"[;,.]?\s*(?:risk budget|i can lose up to) \$([0-9]{1,7}(?:\.[0-9]{1,2})?)\.?$", re.I
)


class IntentAgent:
    name = "INTENT"

    async def run(self, context, tools, previous):
        assets = tools.read("stock_resolver")
        tools.read("mandate_validator")
        text = context.text.strip()
        if len(text) > 1000 or re.search(
            r"\b(ignore|execute|broadcast|transfer|autonomous|automatically|sell)\b", text, re.I
        ):
            return (
                "ABSTAIN",
                IntentOutput(needs_clarification=True),
                (),
                ("UNSUPPORTED_OR_AMBIGUOUS_MANDATE",),
            )
        opportunity_text = re.sub(
            r"\bi have a \$([0-9]{1,7}(?:\.[0-9]{1,2})?) risk budget\b",
            r"I can lose up to $\1",
            text,
            flags=re.I,
        )
        opportunity_text = re.sub(
            r"(?:i have )?no stock preference[.;]?\s*",
            "",
            opportunity_text,
            flags=re.I,
        )
        match = OPPORTUNITY.fullmatch(opportunity_text)
        if match:
            try:
                mandate = Mandate(
                    mode="OPPORTUNITY",
                    budget_usd=match["budget"],
                    risk_budget_usd=match["risk"],
                    time_window="BEFORE_MONDAY"
                    if "monday" in match["window"].lower()
                    else "PRE_OPEN",
                )
            except ValueError:
                return (
                    "ABSTAIN",
                    IntentOutput(needs_clarification=True),
                    (),
                    ("EXPLICIT_BUDGET_RISK_AND_WINDOW_REQUIRED",),
                )
            return "OK", IntentOutput(mandate=mandate), (), ()
        match = ALLOCATION.fullmatch(text)
        if match:
            try:
                mandate = Mandate(
                    mode="AUTOPILOT",
                    strategy="TOKENIZED_AI_AND_CASH",
                    allocation_stock_percent=match["stocks"],
                    allocation_cash_percent=match["cash"],
                )
            except ValueError:
                return (
                    "ABSTAIN",
                    IntentOutput(needs_clarification=True),
                    (),
                    ("INVALID_ALLOCATION",),
                )
            return "OK", IntentOutput(mandate=mandate), (), ("AUTOPILOT_ENGINE_NOT_IMPLEMENTED",)
        risk_match = RISK_SUFFIX.search(text)
        risk = Decimal(risk_match[1]) if risk_match else None
        direct = text[: risk_match.start()].strip() if risk_match else text
        # Extend wording only. Existing stock/budget grammar and backend resolution are reused.
        direct = re.sub(r"^put\s+", "buy ", direct, flags=re.I)
        direct = re.sub(r"\binto\b", "of", direct, flags=re.I)
        parsed = parse_intent(direct)
        if parsed.status != "VALID":
            return (
                "ABSTAIN",
                IntentOutput(needs_clarification=True),
                (),
                ("EXPLICIT_STOCK_AND_BUDGET_REQUIRED",),
            )
        query = parsed.stock_query.casefold()

        def company_name(asset):
            name = asset.company_name
            if asset.data_mode == "DEMO":
                name = re.sub(r"\s+\(DEMO\)$", "", name)
            return re.sub(
                r"\s+(corporation|inc\.?|incorporated|corp\.?)$", "", name, flags=re.I
            ).casefold()

        exact = [
            a
            for a in assets
            if a.supported
            and (
                a.ticker.casefold() == query
                or a.company_name.casefold() == query
                or company_name(a) == query
            )
        ]
        if len(exact) != 1:
            return (
                "ABSTAIN",
                IntentOutput(needs_clarification=True),
                (),
                ("NO_UNAMBIGUOUS_VERIFIED_STOCK",),
            )
        try:
            mandate = Mandate(
                mode="DIRECT_EXPOSURE",
                ticker=exact[0].ticker,
                budget_usd=parsed.budget_usd,
                risk_budget_usd=risk,
            )
        except ValueError:
            return "ABSTAIN", IntentOutput(needs_clarification=True), (), ("INVALID_MANDATE",)
        return (
            "OK",
            IntentOutput(mandate=mandate),
            (),
            (() if risk is not None else ("USER_RISK_BUDGET_NOT_PROVIDED",)),
        )
