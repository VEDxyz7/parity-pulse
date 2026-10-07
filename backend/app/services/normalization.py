"""Shared exact exposure economics; no reference-price fallback."""

from decimal import ROUND_CEILING, Decimal, localcontext

from app.models.data import financial


def bounded_decimal(value):
    if value is None:
        return
    value = financial(value)
    if len(value.as_tuple().digits) > 96 or abs(value.adjusted()) > 36:
        raise ValueError("Unsupported financial magnitude")


def positive(value):
    result = financial(value)
    bounded_decimal(result)
    if result <= 0:
        raise ValueError("Positive financial input required")
    return result


def effective_price_per_share(price, ratio, *, presentation=False):
    price, ratio = positive(price), positive(ratio)
    with localcontext() as context:
        context.prec = 256
        result = price / ratio
        return result.quantize(Decimal("1e-18"), rounding=ROUND_CEILING) if presentation else result


def comparable_economics(price, ratio, reference):
    price, ratio, reference = positive(price), positive(ratio), positive(reference)
    with localcontext() as context:
        context.prec = 256
        comparable = reference * ratio
        deviation = (price - comparable) / comparable
        return {
            "effective_price_per_share_usd": effective_price_per_share(price, ratio),
            "comparable_token_value_usd": comparable,
            "deviation": deviation,
            "absolute_deviation": abs(deviation),
        }
