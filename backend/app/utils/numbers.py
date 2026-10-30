import math


# JSON allows integers of any size (jsonb even rewrites 1e400 as a 401-digit integer), and one
# that does not fit in a float would fail every float field and arithmetic it reaches.
def is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
