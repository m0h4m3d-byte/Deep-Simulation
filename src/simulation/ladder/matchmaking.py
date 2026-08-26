"""ladder/matchmaking.py — picks an opponent near our current rating."""

import random


def pick_opponent(our_rating: float, pool, ratings, window: float = 120.0):
    """Sample an opponent whose rating is within `window` of ours.

    Falls back to uniform sampling when nobody is in range (early ladder).
    """
    candidates = [o for o in pool if abs(ratings.get(o.name) - our_rating) <= window]
    if not candidates:
        candidates = list(pool)
    return random.choice(candidates)
