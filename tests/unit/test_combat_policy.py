import math

from maicon_sim.policies.combat import CombatPolicy


CALIBRATION = {"front_camera": {"fx_px": 320., "fy_px": 320., "cx_px": 319.5, "cy_px": 239.5}, "laser_offset_camera_m": [0, 0, .02]}


def facility():
    return {"kind": "facility", "confidence": .95, "class_probs": {"RADAR": .99},
            "aim_point_px": [319.5, 233.1], "range_m": 1.,
            "bbox_xyxy_px": [270, 210, 370, 310],
            "camp_readout": {"camp": "RED", "confidence": .95}}


def observations(tick, detections=None, ammo=8):
    return {"combat": {"captured_tick": tick, "received_tick": tick, "sequence": tick, "detections": detections or [facility()]},
            "state": {"hp": 4, "ammo": ammo, "captured_tick": tick}}


def test_stable_aim_fires_once_and_does_not_repeat_while_ack_pending():
    policy = CombatPolicy("B-1")
    assert policy.update(observations(0), CALIBRATION, target="RED_RADAR").state == "settle"
    assert policy.update(observations(20), CALIBRATION, target="RED_RADAR").fire
    assert not policy.update(observations(21), CALIBRATION, target="RED_RADAR").fire
    policy.acknowledge_fire({"message": "fired", "left_ms": 10000}, 21)
    for tick in range(30, 520, 10):
        result = policy.update(observations(tick), CALIBRATION, target="RED_RADAR")
        assert result.state == "cooldown" and not result.fire
    assert policy.update(observations(520), CALIBRATION, target="RED_RADAR").state == "facility_attempt_complete"
    assert "RED_RADAR" in policy.serviced_facilities


def test_fire_timeout_is_not_retried_and_can_only_resolve_from_new_own_state():
    policy = CombatPolicy("B-1")
    policy.update(observations(0), CALIBRATION, target="RED_RADAR")
    assert policy.update(observations(20), CALIBRATION, target="RED_RADAR").fire
    policy.acknowledge_fire(None, 21)
    result = policy.update(observations(2000), CALIBRATION, target="RED_RADAR")
    assert result.state == "unknown" and not result.fire
    policy.cancel(2001)
    assert policy.unknown_outcome
    result = policy.update(observations(2010, ammo=7), CALIBRATION, target="RED_RADAR")
    assert not policy.unknown_outcome
    assert not result.fire


def test_discarded_unsent_intent_can_recover_but_dispatched_unknown_stays_latched():
    policy = CombatPolicy("B-1")
    policy.update(observations(0), CALIBRATION, target="RED_RADAR")
    assert policy.update(observations(20), CALIBRATION, target="RED_RADAR").fire
    policy.discard_unsent_fire(20)
    assert not policy.pending_fire
    assert not policy.update(observations(21), CALIBRATION, target="RED_RADAR").fire
    assert policy.update(observations(41), CALIBRATION, target="RED_RADAR").fire
    policy.acknowledge_fire(None, 42)
    policy.discard_unsent_fire(42)
    assert policy.unknown_outcome
    assert not policy.update(observations(2000), CALIBRATION, target="RED_RADAR").fire


def test_gimbal_commands_respect_wire_direction_and_cannot_be_replayed_from_same_frame():
    policy = CombatPolicy("B-1")
    detection = facility()
    detection["aim_point_px"] = [350., 210.]
    value = observations(0, [detection])
    result = policy.update(value, CALIBRATION, target="RED_RADAR")
    assert result.gimbal[0] > 0 and result.gimbal[1] > 0
    assert result.hold and not result.fire
    assert policy.update(value, CALIBRATION, target="RED_RADAR").gimbal is None


def test_delayed_camera_correction_uses_capture_time_gimbal_not_latest_pose():
    policy = CombatPolicy("B-1")
    detection = facility()
    detection["aim_point_px"] = [383.5, 233.1]
    value = observations(0, [detection])
    value["state"]["received_tick"] = 10
    result = policy.update(value, CALIBRATION, target="RED_RADAR", gimbal={"pan": 20., "tilt": 0.}, capture_gimbal=(0., 0.))
    expected = math.degrees(math.atan(.2))/.5
    assert abs(result.gimbal[0]-expected) < 1e-9
    assert not result.fire
    assert policy.update(value, CALIBRATION, target="RED_RADAR", capture_gimbal=None).state == "uncertain_gimbal"


def test_m4_requires_enemy_identification_and_visible_receiver_and_avoids_crossing_ugv():
    policy = CombatPolicy("B-1")
    enemy = {"kind": "ugv", "confidence": .95, "aim_point_px": [319.5, 233.1], "range_m": 1.,
             "marker_readout": {"camp": "RED", "band_count": 2, "confidence": .95}, "bbox_xyxy_px": [290, 220, 350, 300]}
    assert policy.update(observations(0, [enemy]), CALIBRATION).state == "settle"
    assert policy.update(observations(20, [enemy]), CALIBRATION).fire
    policy = CombatPolicy("B-1")
    friendly = {**enemy, "marker_readout": {"camp": "BLUE", "band_count": 1, "confidence": .95}}
    assert policy.update(observations(0, [friendly]), CALIBRATION).state == "search"
    assert policy.update(observations(0, [{**enemy, "aim_point_px": None}]), CALIBRATION).state == "search"
    assert policy.update(observations(0, [{**enemy, "aim_confidence": .4}]), CALIBRATION).state == "search"
    assert policy.update(observations(0, [enemy, friendly]), CALIBRATION).state == "occluded"


def test_facility_camp_is_disambiguated_from_public_map_and_estimated_pose():
    sectors = {"sectors": [{"sector_id": "R-S1", "polygon_xy_m": [[3, 0], [6, 0], [6, 5], [3, 5]]},
                            {"sector_id": "B-S1", "polygon_xy_m": [[0, 0], [3, 0], [3, 5], [0, 5]]}]}
    policy = CombatPolicy("B-1", sectors)
    detection = facility()
    detection.pop("camp_readout")
    assert policy.update(observations(0, [detection]), CALIBRATION, target="RED_RADAR", pose=(4.8, 2., math.pi)).state == "settle"
    assert policy.update(observations(20, [detection]), CALIBRATION, target="RED_RADAR", pose=(1.8, 2., math.pi)).state == "search"


def test_phase_pause_objective_stale_empty_and_device_lock_do_not_fire():
    for kwargs in ({"phase": "reporting"}, {"cmd": "pause"}, {"objective": "RED_MAINTENANCE"}):
        policy = CombatPolicy("B-1")
        assert not policy.update(observations(100), CALIBRATION, target="RED_RADAR", **kwargs).fire
    policy = CombatPolicy("B-1")
    frame = observations(0)
    frame["state"]["received_tick"] = 100
    assert policy.update(frame, CALIBRATION, target="RED_RADAR").state == "stale"
    policy.update(observations(0), CALIBRATION, target="RED_RADAR")
    assert policy.update(observations(20, ammo=0), CALIBRATION, target="RED_RADAR").state == "empty"
    policy.update(observations(20), CALIBRATION, target="RED_RADAR")
    policy.acknowledge_fire({"message": "locked", "left_ms": 10000}, 20)
    assert not policy.update(observations(100), CALIBRATION, target="RED_RADAR").fire
    policy.acknowledge_fire({"message": "empty"}, 100)
    assert policy.update(observations(1100), CALIBRATION, target="RED_RADAR").state == "empty"


def test_lost_alignment_after_fire_does_not_claim_completed_dwell():
    policy = CombatPolicy("B-1")
    policy.update(observations(0), CALIBRATION, target="RED_RADAR")
    assert policy.update(observations(20), CALIBRATION, target="RED_RADAR").fire
    policy.acknowledge_fire({"message": "fired"}, 20)
    moved = facility()
    moved["aim_point_px"] = [350., 230.]
    policy.update(observations(100, [moved]), CALIBRATION, target="RED_RADAR")
    policy.update(observations(520), CALIBRATION, target="RED_RADAR")
    assert "RED_RADAR" not in policy.serviced_facilities


def test_missing_frames_and_alignment_after_emission_do_not_count_as_dwell():
    policy = CombatPolicy("B-1")
    policy.update(observations(0), CALIBRATION, target="RED_RADAR")
    assert policy.update(observations(20), CALIBRATION, target="RED_RADAR").fire
    policy.acknowledge_fire({"message": "fired"}, 20)
    # A fresh frame after a long gap cannot prove continuous aim in between.
    policy.update(observations(520), CALIBRATION, target="RED_RADAR")
    for tick in range(530, 800, 10):
        assert not policy.update(observations(tick), CALIBRATION, target="RED_RADAR").fire
    assert "RED_RADAR" not in policy.serviced_facilities
