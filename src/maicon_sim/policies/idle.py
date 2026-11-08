"""Idle policy deliberately reports only ready, never guesses mission answers."""
from .baseline import ParticipantPolicy


class IdlePolicy(ParticipantPolicy):
    def __init__(self, public_map, calibration, slot):
        super().__init__(public_map, calibration, slot, policy="idle")
