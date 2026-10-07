"""Bounded deterministic budget grammar, without an LLM or implicit ticker mapping."""

import re
from decimal import Decimal

from app.models.exposure import ParsedIntent

# A budget is mandatory. Unsupported/ambiguous sentences cannot silently become an order.
REQUEST = re.compile(
    r"(?:buy\s+|i\s+have\s+)?\$([0-9]{1,7}(?:\.[0-9]{1,2})?)"
    r"\s+(?:(?:of|in|worth\s+of)\s+)?([A-Za-z][A-Za-z0-9 .&'\-]{0,99})",
    re.IGNORECASE,
)


def parse_intent(text: str) -> ParsedIntent:
    match = REQUEST.fullmatch(text.strip())
    if match:
        budget, query = Decimal(match[1]), match[2].strip().rstrip(".").strip()
        if (
            0 < budget <= Decimal("1000000")
            and query
            and not re.search(
                r"\b(and|or|then|sell|transfer|execute|broadcast|ignore)\b", query, re.I
            )
        ):
            return ParsedIntent(
                status="VALID", stock_query=query, budget_usd=budget, reason="EXPLICIT_USD_BUDGET"
            )
    return ParsedIntent(status="NEEDS_CLARIFICATION", reason="USE_EXPLICIT_STOCK_AND_USD_BUDGET")
