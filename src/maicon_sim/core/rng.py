"""Stable independent randomness; Python randomized hash() is never a seed."""
import hashlib
import numpy as np


def stream(seed, *namespace):
    digest = hashlib.sha256((str(seed) + ':' + ':'.join(map(str, namespace))).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:16], 'big'))
