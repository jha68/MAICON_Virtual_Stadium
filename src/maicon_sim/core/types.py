"""Shared values. Mutable robot truth is owned exclusively by MatchEngine."""
from dataclasses import dataclass, field
from typing import Optional

SLOTS = ('B-1', 'B-2', 'B-3', 'R-1', 'R-2', 'R-3')
CAMPS = ('BLUE', 'RED')
SECTORS = ('B-S1', 'B-S2', 'B-S3', 'CM', 'R-S1', 'R-S2', 'R-S3')
OBJECT_CLASSES = ('MILITARY_TRUCK', 'MORTAR', 'TANK', 'MISSILE', 'AMMO_BOX', 'DRUM')
FACILITY_KINDS = ('COMMS', 'OUTPOST', 'RADAR')
BASE_KINDS = ('COMMAND_POST', 'MAINTENANCE', 'SUPPLY_DEPOT')
FACILITIES = tuple(f'{c}_{f}' for c in CAMPS for f in FACILITY_KINDS)
BASES = tuple(f'{c}_{b}' for c in CAMPS for b in BASE_KINDS)


def camp_for_slot(slot):
    return 'BLUE' if slot.startswith('B-') else 'RED'


def opponent_camp(camp):
    return 'RED' if camp == 'BLUE' else 'BLUE'


@dataclass(frozen=True)
class Pose2:
    x_m: float
    y_m: float
    yaw_rad: float


@dataclass(frozen=True)
class SessionIdentity:
    match_id: str
    episode_index: int
    slot: str
    camp: str


@dataclass(frozen=True)
class TimedEnvelope:
    sequence: int
    captured_tick: int
    received_tick: int
    source_id: str


@dataclass
class RobotTruth:
    slot: str
    camp: str
    pose: Pose2
    initial_pose: Pose2
    hp: int = 4
    ammo: int = 8
    ready: bool = False
    admitted: bool = False
    started: bool = False
    v: float = 0.0
    omega: float = 0.0
    pan: float = 0.0
    tilt: float = 0.0
    target_pan: float = 0.0
    target_tilt: float = 0.0
    gimbal_speed: float = 90.0
    gimbal_acc: float = 20.0
    last_velocity_received_tick: int = -1000000
    laser_until: int = 0
    next_fire_tick: int = 0
    invulnerable_until: int = 0
    device_locked_until: int = 0
    drive_locked_until: int = 0
    battery_pct: float = 100.0
    oled: dict = field(default_factory=dict)

    @property
    def active_command(self):
        return (self.v, self.omega)
