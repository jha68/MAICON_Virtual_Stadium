"""Pure scoring shared by both render backends. SIM assumptions are explicit."""
from itertools import permutations
from .types import OBJECT_CLASSES, SECTORS, SLOTS, camp_for_slot


def score_m1(report, expected):
    if not report:
        return 0
    return (3 * (report.get('target') is not None and report['target'].upper() == expected['target'].upper())
            + 3 * (report.get('search_sectors') is not None and set(report['search_sectors']) == set(expected['search_sectors']))
            + 4 * (report.get('base') is not None and report['base'].upper() == expected['base'].upper()))


def inventory_from_boxes(boxes):
    inventory = {s: {c: 0 for c in OBJECT_CLASSES} for s in SECTORS}
    for box in boxes:
        for face in box['faces']:
            if face['kind'] == 'object':
                inventory[box['sector_id']][face['object_class'].upper()] += 1
    return inventory


def report_inventory(report):
    if not report:
        return {}
    return {item['sector']: {c: next((o['count'] for o in item['objects'] if o['type'].upper() == c), 0)
                            for c in OBJECT_CLASSES} for item in report['sectors']}


def scored_sectors(camp):
    prefix = 'R' if camp == 'BLUE' else 'B'
    return (f'{prefix}-S1', f'{prefix}-S2', f'{prefix}-S3', 'CM')


def score_m3(report, inventory, camp):
    value = report_inventory(report)
    return sum((9 if sector == 'CM' else 7) for sector in scored_sectors(camp)
               if sector in value and value[sector] == inventory[sector])


def risk_numerator(hp, ammo, m3):
    return 30 * hp + 15 * ammo + 4 * m3


def accepted_rankings(risks):
    return [p for p in permutations(sorted(risks)) if all(risks[p[i]] >= risks[p[i + 1]] for i in range(len(p) - 1))]


def score_m6(ranking, risks):
    if not ranking:
        return 0
    if isinstance(ranking, dict):
        ranking = ranking['ranking']
    best = 0
    for expected in accepted_rankings(risks):
        matches = [i < len(ranking) and ranking[i] == expected[i] for i in range(3)]
        points = 15 if len(ranking) == 3 and all(matches) else 10 if matches[0] else 5 if any(matches[1:]) else 0
        best = max(best, points)
    return best


def finalize_scores(base_scores, eligible):
    """Compare M1..M6 once, then add nonrecursive SIM-ALLIANCE bonus."""
    scores = {}
    for slot in SLOTS:
        row = {f'm{i}': int(base_scores[slot].get(f'm{i}', 0)) if slot in eligible else 0 for i in range(1, 7)}
        scores[slot] = row
    totals = {camp: sum(sum(v.values()) for slot, v in scores.items() if camp_for_slot(slot) == camp) for camp in ('BLUE', 'RED')}
    for slot, row in scores.items():
        camp = camp_for_slot(slot)
        row['alliance_bonus'] = 5 if slot in eligible and totals[camp] == max(totals.values()) else 0
        row['total'] = sum(row.values())
    return scores
