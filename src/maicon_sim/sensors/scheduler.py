"""Integer-boundary sensor cadence, including the initial tick."""
def due(tick,hz):
    if type(hz) is not int or hz<=0 or 100%hz:raise ValueError('Hz must divide 100')
    return tick%(100//hz)==0
