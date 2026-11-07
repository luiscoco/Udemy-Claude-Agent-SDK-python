"""Fixed clean pricing fixture; read as source, never executed by the checker."""


def discount(cents: int, percent: float) -> int:
    return round(cents * (1 - percent / 100))
