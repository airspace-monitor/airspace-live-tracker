import math


def next_slot(now: float, cadence: int) -> float:
    """First slot at or after `now` (unix s) on the shared grid, docs/04 P1 step 1."""
    return math.ceil(now / cadence) * cadence
