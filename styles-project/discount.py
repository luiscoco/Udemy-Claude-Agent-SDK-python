"""Deliberately buggy percentage calculation for the output-style exercise."""


def apply_discount(price, percent):
    if not 0 <= percent <= 100:
        raise ValueError("percent must be 0–100")
    return price - price * percent
