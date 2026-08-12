import random
import re


def random_number(parameters: dict | None = None, player=None) -> str:
    params = parameters or {}
    mode = params.get("mode", "number")
    lo = int(params.get("min", 1))
    hi = int(params.get("max", 100))

    if lo > hi:
        lo, hi = hi, lo

    if mode == "dice":
        sides = max(2, hi - lo + 1)
        return f"🎲 You rolled a {random.randint(1, sides)} (d{sides})"

    if mode == "coin":
        return f"🪙 It's {'Heads' if random.randint(0, 1) == 0 else 'Tails'}"

    n = random.randint(lo, hi)
    return f"Random number ({lo}–{hi}): {n}"
