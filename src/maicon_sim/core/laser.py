"""Backend-independent pairwise uninterrupted contact accumulation.

Geometry chooses emitter/receiver pairs; this module never reads render pixels.
Expiration and invulnerability are applied by MatchEngine before accumulation.
"""


def accumulate_contacts(previous, valid_pairs, threshold_ticks):
    """Return this interval's dwell and all newly ready pairs, without mutation."""
    if threshold_ticks < 1:
        raise ValueError('positive contact threshold required')
    dwell = {pair: previous.get(pair, 0) + 1 for pair in valid_pairs}
    return dwell, sorted(pair for pair, count in dwell.items() if count >= threshold_ticks)
