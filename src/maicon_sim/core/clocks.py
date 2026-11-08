"""Integer 10 ms clock conversions; wall time belongs to transport only."""
TICK_MS = 10


def ticks(milliseconds):
    if type(milliseconds) is not int or milliseconds < 0 or milliseconds % TICK_MS:
        raise ValueError('duration must be a nonnegative multiple of 10 ms')
    return milliseconds // TICK_MS
