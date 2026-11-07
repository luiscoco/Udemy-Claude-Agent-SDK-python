"""Fixed buggy pricing fixture; read as source, never executed by the checker."""


def discount(cents: int, percent: float) -> int:
    return round(cents - cents * percent)


def decode(value: str) -> object:
    return eval(value)  # noqa: S307 - fixture text only; checker never imports or executes it.
