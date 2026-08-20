"""Math solver — evaluate mathematical expressions safely.

Intents: solve_math ("what is sqrt(144) + 2^10", "calculate 3x = 15",
         "cos(pi/3)", "convert 5 km to miles")
"""
import logging
import math
import re

logger = logging.getLogger("math_solver")

_ALLOWED = re.compile(r"^[\d\w\s\+\-\*/\.\%\(\),=\<\>\|\&\^!~\?:]+$")


def _safe_eval(expr: str) -> str:
    """Evaluate expr with a math-only namespace."""
    expr = expr.replace("^", "**")
    if not _ALLOWED.match(expr):
        raise ValueError("forbidden characters")
    ns = {k: getattr(math, k) for k in (
        "sqrt", "cbrt" if hasattr(math, "cbrt") else "",
        "log", "log10", "log2", "exp", "ceil", "floor", "fabs", "fmod",
        "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
        "degrees", "radians", "factorial", "gcd", "pi", "e", "inf",
        "tau", "isclose", "trunc")}
    ns = {k: v for k, v in ns.items() if v}
    ns["__builtins__"] = {}
    result = eval(expr, ns)  # noqa: S307 — ns sandboxed, expr regex-validated
    if isinstance(result, complex):
        return f"{result.real:.6g} {'+' if result.imag >= 0 else '-'} {abs(result.imag):.6g}i"
    if isinstance(result, float) and result == int(result) and abs(result) < 10**15:
        return str(int(result))
    return f"{result:.6g}"


def solve_math(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    expr = (parameters.get("expression") or parameters.get("text") or
            parameters.get("query") or "").strip()
    if not expr:
        return "Tell me the math expression, for example: 'solve sqrt(144) + 2^10'."
    # Handle simple linear equations ax=b → solve for x
    eq = re.match(r"^([-\d\w\s\+\-\*/\.]+?)\s*=\s*([-\d\w\s\+\-\*/\.]+)$", expr)
    if eq and re.search(r"\bx\b", expr):
        try:
            left_a = re.sub(r"[^-\d\s\+\-\*/\.]", "", eq.group(1))
            num = _safe_eval(eq.group(2) or "0")
            x_part = eq.group(1)
            coef = re.sub(r"x", "", x_part)
            coef = _safe_eval(coef or "1")
            if float(coef) == 0:
                return "The coefficient of x is zero; the equation has no unique solution."
            return f"x = {_safe_eval(f'{num}/{coef}')}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("equation solve error: %s", exc)
    try:
        return f"{expr} = {_safe_eval(expr)}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("math eval error: %s", expr)
        return f"Could not evaluate '{expr}': {exc}"
