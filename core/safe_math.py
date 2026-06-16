"""Safe math expression evaluator using AST — no eval()."""

import ast
import math as _math
from typing import Any

_ALLOWED_NAMES = {
    "sqrt": _math.sqrt, "sin": _math.sin, "cos": _math.cos,
    "tan": _math.tan, "log": _math.log, "log10": _math.log10,
    "pi": _math.pi, "e": _math.e,
}

_ALLOWED_NODE_TYPES = frozenset({
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.FloorDiv,
    ast.Mod, ast.USub, ast.UAdd,
})


def safe_math(expression: str, extra_names: dict[str, Any] | None = None) -> float:
    """Evaluate a math expression safely using AST parsing.

    Only numeric constants, basic operators (+, -, *, /, //, %, **),
    and allowed math functions are permitted.
    """
    cleaned = (
        expression.replace(" ", "")
        .replace("^", "**")
    )
    cleaned = __import__("re").sub(r"(\d)x", r"\1*x", cleaned)
    cleaned = __import__("re").sub(r"x(\d)", r"x*\1", cleaned)

    tree = ast.parse(cleaned, mode="eval")

    names = dict(_ALLOWED_NAMES)
    if extra_names:
        names.update(extra_names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise ValueError(f"Unsafe name '{node.id}' in expression")
            continue
        if type(node) not in _ALLOWED_NODE_TYPES:
            raise ValueError(
                f"Unsafe construct '{type(node).__name__}' in expression"
            )

    code = compile(tree, "<safe_math>", "eval")
    return eval(code, {"__builtins__": {}}, names)
