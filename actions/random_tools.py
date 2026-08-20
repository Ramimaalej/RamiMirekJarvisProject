"""Random fun tools — dice roll, coin flip and random pick.

Intents: dice_roll ("roll a d20", "roll 2 dice"), coin_flip ("flip a coin",
         "heads or tails"), random_pick ("pick between pizza and burger",
         "choose one of A, B, C")
"""
import logging
import random
import re

logger = logging.getLogger("random_tools")


def dice_roll(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    expr = parameters.get("dice") or parameters.get("text") or ""
    m = re.match(r"(\d+)?\s*[dD]\s*(\d+)", expr)
    if not m:
        n, sides = 1, 6
    else:
        n = min(int(m.group(1) or 1), 20)
        sides = min(int(m.group(2) or 6), 100)
    rolls = [random.randint(1, sides) for _ in range(n)]
    total = sum(rolls)
    if n == 1:
        return f"Rolled a d{sides}: {total}"
    return f"Rolled {n}d{sides}: {rolls} = {total}"


def coin_flip(parameters: dict | None = None, player=None) -> str:
    result = random.choice(["HEADS", "TAILS"])
    emoji = "🪙"
    return f"{emoji} Coin flip: {result}"


def random_pick(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    text = (parameters.get("options") or parameters.get("text") or "").strip()
    if not text:
        return "Give me the options, for example: 'pick between pizza, burger or sushi'."
    parts = [p.strip() for p in re.split(r",| or | / ", text) if p.strip()]
    if not parts:
        parts = [text]
    pick = random.choice(parts)
    return f"I pick: {pick} (from: {', '.join(parts)})"
