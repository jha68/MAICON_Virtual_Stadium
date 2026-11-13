"""Threat ranking consumes public visual cues and preserves missing knowledge."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from maicon_sim.policies.threat import ThreatEstimator


def frame(tick, *cues):
    return {'camera_id': 'B-1/front', 'captured_tick': tick, 'detections': [
        {'kind': 'ugv', 'marker_readout': {'camp': camp, 'band_count': band, 'confidence': confidence}, 'visual_state': state}
        for camp, band, confidence, state in cues]}


def cue(band, hp, ammo, confidence=.99):
    return 'RED', band, .99, {'hp': hp, 'ammo': ammo, 'confidence': confidence}


def test_unequal_visual_hp_ammo_change_ranking_without_hidden_m3():
    estimate = ThreatEstimator('BLUE')
    estimate.observe(frame(100, cue(1, 0, 0), cue(2, 2, 4), cue(3, 4, 8)))
    result = estimate.summary(100)
    assert result['estimated_ranking'] == ['R-3', 'R-2', 'R-1']
    assert result['ranking_kind'] == 'observed_estimate'
    assert result['opponents']['R-3']['hp_interval'] == [4., 4.]
    assert all(item['m3_interval'] == [0, 30] for item in result['opponents'].values())
    assert result['oracle'] is False
    json.dumps(result, allow_nan=False)


def test_absence_and_ties_remain_explicit_and_deterministic():
    estimate = ThreatEstimator()
    result = estimate.summary(0)
    assert result['ranking_kind'] == 'uninformed_fallback'
    assert len(result['possible_ties']) == 3
    assert result['estimated_ranking'] == ['R-1', 'R-2', 'R-3']
    estimate.observe(frame(0, cue(1, 4, 8), cue(2, 4, 8), cue(3, 4, 8)))
    assert len(estimate.summary(0)['possible_ties']) == 3


def test_unseen_state_intervals_widen_and_low_confidence_has_margin():
    estimate = ThreatEstimator()
    estimate.observe(frame(0, cue(1, 4, 8), cue(2, 2, 4, confidence=.6)))
    fresh = estimate.summary(0)['opponents']
    assert fresh['R-2']['hp_interval'] == [1., 3.]
    assert fresh['R-2']['ammo_interval'] == [3., 5.]
    stale = estimate.summary(2000)['opponents']
    assert stale['R-1']['hp_interval'] == [2., 4.]
    assert stale['R-1']['ammo_interval'] == [6., 8.]
    assert stale['R-1']['age_s'] == 20.


def test_duplicate_and_out_of_order_frames_do_not_add_observations():
    estimate = ThreatEstimator()
    estimate.observe(frame(100, cue(1, 4, 8)))
    estimate.observe(frame(100, cue(1, 0, 0)))
    estimate.observe(frame(99, cue(1, 0, 0)))
    result = estimate.summary(100)['opponents']['R-1']
    assert result['hp_interval'] == [4., 4.]
    assert result['cue_counts']['hp_led'] == 1


def test_interval_allows_a_hit_or_shot_immediately_after_last_capture():
    estimate = ThreatEstimator()
    estimate.observe(frame(100, cue(1, 4, 8)))
    result = estimate.summary(101)['opponents']['R-1']
    assert result['hp_interval'] == [3., 4.]
    assert result['ammo_interval'] == [7., 8.]


def test_identity_confidence_and_own_camp_filter_otherwise_valid_cues():
    estimate = ThreatEstimator()
    estimate.observe(frame(0, ('BLUE', 1, 1., {'hp': 0, 'ammo': 0, 'confidence': 1.}), ('RED', 2, .4, {'hp': 0, 'ammo': 0, 'confidence': 1.})))
    assert estimate.summary(0)['ranking_kind'] == 'uninformed_fallback'


def test_raw_hidden_state_fields_are_ignored():
    estimate = ThreatEstimator()
    value = frame(0, ('RED', 1, 1., {}))
    value['detections'][0].update(hp=4, ammo=8, m3=30)
    value['detections'][0]['visual_state']['m3'] = 30
    estimate.observe(value)
    result = estimate.summary(0)['opponents']['R-1']
    assert result['hp_interval'] == [0., 4.]
    assert result['ammo_interval'] == [0., 8.]
    assert result['m3_interval'] == [0, 30]


def test_visible_shot_is_one_event_across_repeated_illumination():
    estimate = ThreatEstimator()
    estimate.observe(frame(0, cue(1, 4, 8)))
    for tick in (1, 10, 100, 499):
        estimate.observe(frame(tick, ('RED', 1, 1., {'shot_visible': True})))
    first = estimate.summary(499)['opponents']['R-1']
    assert first['cue_counts']['shot_events'] == 1
    assert first['ammo_interval'][1] == 7.
    estimate.observe(frame(500, ('RED', 1, 1., {'shot_visible': False})))
    estimate.observe(frame(1001, ('RED', 1, 1., {'shot_visible': True})))
    second = estimate.summary(1001)['opponents']['R-1']
    assert second['cue_counts']['shot_events'] == 2
    assert second['ammo_interval'][1] == 6.


def test_explicit_intervals_and_unresolvable_leds_are_conservative():
    estimate = ThreatEstimator()
    estimate.observe(frame(0, ('RED', 1, 1., {'hp_interval': [1, 3], 'ammo_interval': [2, 6], 'confidence': .99}), cue(2, 4, 8, confidence=.2)))
    result = estimate.summary(0)
    assert result['opponents']['R-1']['hp_interval'] == [1., 3.]
    assert result['opponents']['R-2']['hp_interval'] == [0., 4.]


def test_summary_and_observe_are_thread_safe_and_json_finite():
    estimate = ThreatEstimator()
    def observe():
        for tick in range(200):
            estimate.observe(frame(tick, cue(1, 4, 8)))
    def summarize():
        for tick in range(200):
            json.dumps(estimate.summary(tick), allow_nan=False)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda fn: fn(), [observe, summarize]))
    assert estimate.summary(200)['opponents']['R-1']['last_seen_tick'] == 199
