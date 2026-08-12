import re


_CONVERSIONS = {
    # Length
    ("km", "mi"): 0.621371,
    ("mi", "km"): 1.60934,
    ("km", "m"): 1000,
    ("m", "km"): 0.001,
    ("mi", "ft"): 5280,
    ("ft", "mi"): 0.000189394,
    ("m", "ft"): 3.28084,
    ("ft", "m"): 0.3048,
    ("cm", "in"): 0.393701,
    ("in", "cm"): 2.54,
    ("cm", "m"): 0.01,
    ("m", "cm"): 100,
    ("mm", "cm"): 0.1,
    ("cm", "mm"): 10,
    ("km", "cm"): 100000,
    ("cm", "km"): 0.00001,
    ("mi", "yd"): 1760,
    ("yd", "mi"): 0.000568182,
    ("yd", "m"): 0.9144,
    ("m", "yd"): 1.09361,
    ("in", "mm"): 25.4,
    ("mm", "in"): 0.0393701,
    ("km", "ft"): 3280.84,
    ("ft", "km"): 0.0003048,
    # Mass / Weight
    ("kg", "lb"): 2.20462,
    ("lb", "kg"): 0.453592,
    ("kg", "g"): 1000,
    ("g", "kg"): 0.001,
    ("g", "oz"): 0.035274,
    ("oz", "g"): 28.3495,
    ("lb", "oz"): 16,
    ("oz", "lb"): 0.0625,
    ("ton", "kg"): 1000,
    ("ton", "lb"): 2204.62,
    ("lb", "ton"): 0.000453592,
    # Volume
    ("l", "gal"): 0.264172,
    ("gal", "l"): 3.78541,
    ("l", "ml"): 1000,
    ("ml", "l"): 0.001,
    ("l", "qt"): 1.05669,
    ("qt", "l"): 0.946353,
    ("gal", "qt"): 4,
    ("qt", "gal"): 0.25,
    ("cup", "ml"): 240,
    ("ml", "cup"): 0.00416667,
    ("fl_oz", "ml"): 29.5735,
    ("ml", "fl_oz"): 0.033814,
    ("cup", "l"): 0.24,
    ("l", "cup"): 4.16667,
    # Temperature
    ("c", "f"): "c2f",
    ("f", "c"): "f2c",
    ("c", "k"): "c2k",
    ("k", "c"): "k2c",
    ("f", "k"): "f2k",
    ("k", "f"): "k2f",
    # Speed
    ("kmh", "mph"): 0.621371,
    ("mph", "kmh"): 1.60934,
    ("mps", "kmh"): 3.6,
    ("kmh", "mps"): 0.277778,
    ("mph", "mps"): 0.44704,
    ("mps", "mph"): 2.23694,
    ("knot", "kmh"): 1.852,
    ("kmh", "knot"): 0.539957,
    # Time
    ("min", "sec"): 60,
    ("sec", "min"): 0.0166667,
    ("hour", "min"): 60,
    ("min", "hour"): 0.0166667,
    ("day", "hour"): 24,
    ("hour", "day"): 0.0416667,
    ("week", "day"): 7,
    ("day", "week"): 0.142857,
    ("year", "day"): 365.25,
    ("day", "year"): 0.00273791,
    # Data
    ("gb", "mb"): 1024,
    ("mb", "gb"): 0.000976563,
    ("tb", "gb"): 1024,
    ("gb", "tb"): 0.000976563,
    ("mb", "kb"): 1024,
    ("kb", "mb"): 0.000976563,
    # Area
    ("sqm", "sqft"): 10.7639,
    ("sqft", "sqm"): 0.092903,
    ("sqkm", "sqmi"): 0.386102,
    ("sqmi", "sqkm"): 2.58999,
    ("hectare", "acre"): 2.47105,
    ("acre", "hectare"): 0.404686,
}

_UNIT_ALIASES = {
    "kilometers": "km", "kilometre": "km", "kilometres": "km", "kms": "km", "km": "km",
    "miles": "mi", "mile": "mi", "mi": "mi",
    "meters": "m", "metre": "m", "metres": "m", "m": "m",
    "centimeters": "cm", "centimetre": "cm", "cms": "cm", "cm": "cm",
    "millimeters": "mm", "millimetre": "mm", "mms": "mm", "mm": "mm",
    "feet": "ft", "foot": "ft", "ft": "ft",
    "inches": "in", "inch": "in", "in": "in",
    "yards": "yd", "yard": "yd", "yd": "yd",
    "kilograms": "kg", "kilogram": "kg", "kgs": "kg", "kg": "kg",
    "pounds": "lb", "pound": "lb", "lbs": "lb", "lb": "lb",
    "grams": "g", "gram": "g", "g": "g",
    "ounces": "oz", "ounce": "oz", "oz": "oz",
    "tons": "ton", "tonne": "ton", "tonnes": "ton", "t": "ton",
    "liters": "l", "litre": "l", "litres": "l", "l": "l",
    "gallons": "gal", "gallon": "gal", "gal": "gal",
    "milliliters": "ml", "millilitre": "ml", "mls": "ml", "ml": "ml",
    "quarts": "qt", "quart": "qt", "qt": "qt",
    "cups": "cup", "cup": "cup",
    "fluid_ounces": "fl_oz", "fluid_ounce": "fl_oz", "fl oz": "fl_oz",
    "celsius": "c", "centigrade": "c", "c": "c",
    "fahrenheit": "f", "f": "f",
    "kelvin": "k", "k": "k",
    "kmh": "kmh", "km/h": "kmh", "kph": "kmh",
    "mph": "mph", "m/h": "mph",
    "mps": "mps", "m/s": "mps",
    "knots": "knot", "knot": "knot", "kn": "knot",
    "seconds": "sec", "second": "sec", "secs": "sec", "sec": "sec",
    "minutes": "min", "minute": "min", "mins": "min", "min": "min",
    "hours": "hour", "hrs": "hour", "hr": "hour", "hour": "hour",
    "days": "day", "day": "day",
    "weeks": "week", "week": "week",
    "years": "year", "yr": "year", "year": "year",
    "gb": "gb", "gigabytes": "gb", "gigabyte": "gb",
    "mb": "mb", "megabytes": "mb", "megabyte": "mb",
    "tb": "tb", "terabytes": "tb", "terabyte": "tb",
    "kb": "kb", "kilobytes": "kb", "kilobyte": "kb",
    "sqm": "sqm", "square_meters": "sqm", "square meters": "sqm", "m2": "sqm",
    "sqft": "sqft", "square_feet": "sqft", "square feet": "sqft", "ft2": "sqft",
    "sqkm": "sqkm", "square_kilometers": "sqkm", "square kilometers": "sqkm", "km2": "sqkm",
    "sqmi": "sqmi", "square_miles": "sqmi", "square miles": "sqmi", "mi2": "sqmi",
    "hectares": "hectare", "hectare": "hectare",
    "acres": "acre", "acre": "acre",
}


def _normalize_unit(u: str) -> str:
    u = u.lower().strip().rstrip("s")
    return _UNIT_ALIASES.get(u, u)


def convert_units(parameters: dict | None = None, player=None) -> str:
    params = parameters or {}
    value = params.get("value")
    from_u = params.get("from", "")
    to_u = params.get("to", "")

    if value is None or not from_u or not to_u:
        return "Please specify a value, source unit, and target unit."

    try:
        val = float(value)
    except (ValueError, TypeError):
        return f"Invalid number: {value}"

    from_n = _normalize_unit(from_u)
    to_n = _normalize_unit(to_u)

    if from_n == to_n:
        return f"{val} {from_u} = {val} {to_u}"

    key = (from_n, to_n)
    factor = _CONVERSIONS.get(key)

    if factor is None:
        reverse_key = (to_n, from_n)
        rev_factor = _CONVERSIONS.get(reverse_key)
        if rev_factor is not None:
            result = val / rev_factor
        else:
            return f"Unsupported conversion: {from_u} → {to_u}"
    elif isinstance(factor, str):
        if factor == "c2f":
            result = val * 9 / 5 + 32
        elif factor == "f2c":
            result = (val - 32) * 5 / 9
        elif factor == "c2k":
            result = val + 273.15
        elif factor == "k2c":
            result = val - 273.15
        elif factor == "f2k":
            result = (val - 32) * 5 / 9 + 273.15
        elif factor == "k2f":
            result = (val - 273.15) * 9 / 5 + 32
        else:
            return f"Unsupported conversion: {from_u} → {to_u}"
    else:
        result = val * factor

    result = round(result, 4)
    return f"{val} {from_u} = {result} {to_u}"
