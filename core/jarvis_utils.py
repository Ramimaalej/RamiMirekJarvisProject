"""Small utilities."""
from __future__ import annotations
from typing import Any
import logging

def _is_greeting(text: str) -> bool:
    """Return True only if the user's message is purely a greeting with no query."""
    t = text.lower().strip().rstrip("!?.,").strip()
    if t in _GREETINGS:
        return True
    first_word = t.split()[0] if t.split() else ""
    if first_word in _GREETINGS:
        remaining = t[len(first_word):].strip().rstrip("!?.,").strip()
        if not remaining or remaining in _GREETINGS:
            return True
    return False


def calculate(parameters: dict = None) -> str:
    import math as _math
    import re as _re
    expr = (parameters or {}).get("expression", "").strip()
    if not expr:
        return "No expression provided."
    s = expr
    # Roman numeral conversion
    roman_match = _re.match(r'^[IVXLCDM]+$', s.strip(), _re.IGNORECASE)
    if roman_match:
        roman = s.strip().upper()
        roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
        total = 0
        prev = 0
        for ch in reversed(roman):
            val = roman_map.get(ch, 0)
            if val < prev:
                total -= val
            else:
                total += val
            prev = val
        return f"{roman} = {total}"
    # Temperature conversion: "50 Celsius to Fahrenheit"
    m = _re.match(r'([\d.]+)\s*°?\s*(Celsius|C|Fahrenheit|F)\s*(?:to|in|→)\s*(Celsius|C|Fahrenheit|F)', s, _re.IGNORECASE)
    if m:
        val = float(m.group(1))
        from_unit = m.group(2).upper()
        to_unit = m.group(3).upper()
        if from_unit in ("C", "CELSIUS") and to_unit in ("F", "FAHRENHEIT"):
            return f"{s} = {val * 9/5 + 32}°F"
        elif from_unit in ("F", "FAHRENHEIT") and to_unit in ("C", "CELSIUS"):
            return f"{s} = {(val - 32) * 5/9}°C"
    # Percentage: "20% of 10000", "15 percent of 200"
    m = _re.match(r'([\d.]+)\s*%?\s*(?:percent\s+of|percent|of|out\s+of)\s+([\d.]+)', s, _re.IGNORECASE)
    if m:
        pct = float(m.group(1)); val = float(m.group(2))
        return f"{pct}% of {val} = {val * pct / 100}"
    # Hex color to RGB: "#FF5733 to RGB" or "hex #FF5733"
    hex_m = _re.match(r'(?:convert\s+)?(?:the\s+)?(?:hex\s+(?:color\s+)?)?#?([0-9a-fA-F]{6})\s*(?:to\s+)?(?:rgb|RGB)', s, _re.IGNORECASE)
    if hex_m:
        h = hex_m.group(1)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{h} = RGB({r}, {g}, {b})"
    # Unit conversion patterns
    _unit_re = r'(gallons?|liters?|litres?|pounds?|kg|kilograms?|miles?|kilometers?|km|bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|KB|MB|GB|TB)'
    # Normalize unit: strip trailing 's', handle abbreviations
    def _norm_u(u):
        u = u.lower().rstrip("s")
        if u == "kilogram": return "kg"
        if u == "kilometer": return "km"
        return u
    # Pattern 1: "convert 5 miles to km", "3.5 gallons to liters", "75 kg in pounds"
    m = _re.match(r'(?:convert\s+)?([\d.]+)\s*' + _unit_re + r'\s*(?:to|in|→)\s*' + _unit_re, s, _re.IGNORECASE)
    # Pattern 2: "how many X is Y Z" e.g. "how many kilometers is 26.2 miles"
    if not m:
        m = _re.match(r'how\s+many\s+' + _unit_re + r'\s+(?:is|are)\s+([\d.]+)\s+' + _unit_re, s, _re.IGNORECASE)
        if m:
            src_u = _norm_u(m.group(3))
            tgt_u = _norm_u(m.group(1))
            val = float(m.group(2))
        else:
            src_u = tgt_u = None
    else:
        src_u = _norm_u(m.group(2))
        tgt_u = _norm_u(m.group(3))
        val = float(m.group(1))
    if src_u and tgt_u:
        data_units = {"byte": 1, "kilobyte": 1024, "megabyte": 1024**2, "gigabyte": 1024**3, "terabyte": 1024**4,
                      "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
        if src_u in data_units and tgt_u in data_units:
            bytes_val = val * data_units[src_u]
            result = bytes_val / data_units[tgt_u]
            return f"{s} = {result:,.4f}"
        conversions = {
            ("gallon", "liter"): val * 3.78541,
            ("liter", "gallon"): val / 3.78541,
            ("pound", "kg"): val * 0.453592,
            ("kg", "pound"): val / 0.453592,
            ("mile", "km"): val * 1.60934,
            ("km", "mile"): val / 1.60934,
        }
        result = conversions.get((src_u, tgt_u))
        if result:
            return f"{s} = {result:.4f}"
    # Compound interest: "compound interest on 10000 at 5% for 10 years"
    ci_match = _re.match(r'compound\s+interest\s+(?:on\s+)?(\d+[.,]?\d*)\s*(?:at|of)\s+(\d+[.,]?\d*)\s*%?\s*(?:for|over)\s+(\d+)\s*(?:years?|yrs?)', s, _re.IGNORECASE)
    if ci_match:
        principal = float(ci_match.group(1).replace(',', ''))
        rate = float(ci_match.group(2)) / 100
        years = int(ci_match.group(3))
        total = principal * (1 + rate) ** years
        return f"Compound interest: ${principal:,.2f} at {ci_match.group(2)}% for {years} years = ${total:,.2f}"
    # Strip common prefixes: "Solve for x:", "Solve:", "Calculate:", "What is", etc.
    s_clean = _re.sub(r'^(?:solve|calculate|find|compute|what\s+is)\s+(?:for\s+)?(?:\w+\s*[:.])?\s*', '', s, flags=_re.IGNORECASE).strip().rstrip('?.,;:!')
    # Equation solving: "3x + 7 = 22"
    eq_match = _re.match(r'^([\d\s+\-*/().xX^]+)\s*=\s*([\d\s+\-*/().^]+)$', s_clean)
    if eq_match:
        left_side = eq_match.group(1).strip()
        right_side = eq_match.group(2).strip()
        try:
            left_expr = left_side.replace(' ', '').replace('x', '*x').replace('X', '*x')
            if left_expr.startswith('*x'):
                left_expr = 'x' + left_expr[2:]
            right_val = safe_math(right_side)
            coef_match = _re.match(r'^([\d.]+)\s*(?:\*\s*)?[xX]\s*([+\-])\s*([\d.]+)$|^([\d.]+)\s*([+\-])\s*([\d.]+)\s*(?:\*\s*)?[xX]$', left_side.replace(' ', ''))
            if coef_match:
                groups = coef_match.groups()
                if groups[0] and groups[1] and groups[2]:
                    a, op, b = float(groups[0]), groups[1], float(groups[2])
                    b = -b if op == '-' else b
                    x_val = (right_val - b) / a
                elif groups[3] and groups[4] and groups[5]:
                    b, op, a = float(groups[3]), groups[4], float(groups[5])
                    b = -b if op == '-' else b
                    x_val = (right_val - b) / a
                else:
                    raise ValueError("Unparseable")
                return f"x = {x_val}"
        except Exception:
            pass
    # "how many bytes in 2.5 gigabytes" or "how many megabytes in 1024 kilobytes"
    howmany_match = _re.match(r'how\s+many\s+(bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|KB|MB|GB|TB)\s+(?:are\s+)?(?:in|is)\s+([\d.]+)\s+(bytes?|kilobytes?|megabytes?|gigabytes?|terabytes?|KB|MB|GB|TB)', s, _re.IGNORECASE)
    if howmany_match:
        target_unit = howmany_match.group(1).lower().rstrip("s")
        val = float(howmany_match.group(2))
        source_unit = howmany_match.group(3).lower().rstrip("s")
        data_units = {"byte": 1, "kilobyte": 1024, "megabyte": 1024**2, "gigabyte": 1024**3, "terabyte": 1024**4,
                      "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
        if source_unit in data_units and target_unit in data_units:
            bytes_val = val * data_units[source_unit]
            result = bytes_val / data_units[target_unit]
            return f"{val} {howmany_match.group(3)} = {result:,.4f} {howmany_match.group(1)}"
    try:
        result = safe_math(s_clean)
        if isinstance(result, float):
            result = round(result, 10)
            s_result = f"{result:g}"
            return f"{s_clean} = {s_result}"
        return f"{s_clean} = {result}"
    except Exception as e:
        return f"Could not calculate: {e}"
