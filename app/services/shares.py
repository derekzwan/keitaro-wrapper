"""Пересчёт долей офферов в потоке. Чистые функции, без БД."""

from dataclasses import dataclass

TOTAL = 100


class ShareError(ValueError):
    pass


@dataclass
class Slot:
    key: int
    share: int
    pinned: bool


def rebalance(slots: list[Slot]) -> dict[int, int]:
    """Закреплённые доли не трогаем, остаток 100 - sum(pinned) делим поровну между остальными.

    Остаток от деления раздаётся по +1 первым по порядку: 75 на двоих → 38, 37.
    """
    if not slots:
        return {}
    pinned = [s for s in slots if s.pinned]
    free = [s for s in slots if not s.pinned]
    pinned_sum = sum(s.share for s in pinned)
    if pinned_sum > TOTAL:
        raise ShareError(f"Закреплённые доли дают {pinned_sum}% — больше 100%")
    rest = TOTAL - pinned_sum
    if not free:
        if rest != 0:
            raise ShareError(
                f"Все доли закреплены и в сумме дают {pinned_sum}%, а нужно 100%. Открепи хотя бы один оффер."
            )
        return {s.key: s.share for s in slots}
    base, extra = divmod(rest, len(free))
    result = {s.key: s.share for s in pinned}
    for i, s in enumerate(free):
        result[s.key] = base + (1 if i < extra else 0)
    return result
