from __future__ import annotations

from decimal import Decimal

RUPEE_SYMBOL = "\u20b9"


def format_inr(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    quantized = abs(value).quantize(Decimal("0.01"))
    digits = f"{quantized:f}"
    whole, _, fraction = digits.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.append(head[-2:])
            head = head[:-2]
        if head:
            groups.append(head)
        whole = ",".join(reversed(groups)) + "," + tail
    return f"{sign}{RUPEE_SYMBOL}{whole}.{fraction}"
