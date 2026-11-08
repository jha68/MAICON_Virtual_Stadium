#!/usr/bin/env python3
"""Map documented acceptance IDs to reviewed test entry points.

The manifest describes coverage, never execution success. Running pytest emits
separate actual outcomes, including unrun and skipped cases.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
BASE_GROUPS = ("RULE", "TIME", "API", "ISO", "GEO", "RENDER", "REPLAY", "E2E", "PERF", "PACK")

# These entries have intentionally narrower evidence than their specification.
# Remove a limitation only after adding and reviewing an appropriate test.
LIMITATIONS = {}

EXPLICIT = {
    "REPLAY-006": ["tests/integration/test_evaluation.py::test_D2_P01_viewer_does_not_change_fixed_trace*"],
    "API-011": ["tests/contracts/test_sdk_adapters.py::test_latest_report_replaces_pending_and_is_retransmitted*"],
    "GEO-010": ["tests/unit/test_config.py::test_invalid_configuration_is_actionable*"],
    "PACK-005": ["tests/unit/test_config.py::test_all_supplied_scenarios*"],
    "PACK-006": ["tests/unit/test_config.py::test_schema_definition*", "tests/unit/test_config.py::test_all_supplied_scenarios*"],
    "PACK-007": ["tests/unit/test_config.py::test_invalid_configuration_is_actionable*", "tests/render/test_assets.py::test_import_digest_failure_is_explicit*"],
    "RENDER-019": ["tests/render/test_assets.py::test_import_digest_failure_is_explicit*", "tests/render/test_assets.py::test_resolved_tamper_detected*"],
    "REPLAY-005": ["tests/unit/test_rules_time.py::test_CORE_checkpoint_preserves_effects*"],
    "T3D-01": ["tests/unit/test_geometry.py::test_optical_projection*"],
    "RENDER-001": ["tests/render/test_bullet_backend.py::test_direct_bgr_private_boundary*"],
    "ISO-002": ["tests/render/test_bullet_backend.py::test_direct_bgr_private_boundary*"],
    "T3D-12": ["tests/render/test_bullet_backend.py::test_direct_bgr_private_boundary*"],
    "RENDER-002": ["tests/render/test_bullet_backend.py::test_projection_pan_tilt*"],
    "RENDER-003": ["tests/render/test_bullet_backend.py::test_metric_depth_plane_and_landmark*"],
    "RENDER-004": ["tests/render/test_bullet_backend.py::test_metric_depth_plane_and_landmark*"],
    "T3D-05": ["tests/render/test_bullet_backend.py::test_metric_depth_plane_and_landmark*"],
    "RENDER-005": ["tests/render/test_bullet_backend.py::test_uv_and_color_quadrants*"],
    "RENDER-006": ["tests/render/test_bullet_backend.py::test_projection_pan_tilt*"],
    "RENDER-008": ["tests/render/test_bullet_backend.py::test_uv_and_color_quadrants*"],
    "T3D-06": ["tests/render/test_bullet_backend.py::test_uv_and_color_quadrants*"],
    "RENDER-007": ["tests/render/test_bullet_backend.py::test_full_partial_occlusion_keeps_private_inventory*"],
    "T3D-07": ["tests/render/test_bullet_backend.py::test_full_partial_occlusion_keeps_private_inventory*"],
    "T3D-08": ["tests/render/test_bullet_backend.py::test_full_partial_occlusion_keeps_private_inventory*"],
    "RENDER-020": ["tests/render/test_bullet_backend.py::test_scene_sync_no_dynamics_hash_and_close*"],
    "T3D-14": ["tests/render/test_bullet_backend.py::test_scene_sync_no_dynamics_hash_and_close*"],
    "T3D-18": ["tests/render/test_bullet_backend.py::test_scene_sync_no_dynamics_hash_and_close*", "tests/render/test_bullet_backend.py::test_bounded_async_worker_delay_and_generation_reset*"],
    "RENDER-018": ["tests/render/test_bullet_backend.py::test_fog_identity_volume_and_contrast*"],
    "T3D-16": ["tests/render/test_bullet_backend.py::test_fog_identity_volume_and_contrast*"],
    "T3D-15": ["tests/render/test_bullet_backend.py::test_bounded_async_worker_delay_and_generation_reset*"],
    "RENDER-011": ["tests/render/test_bullet_backend.py::test_bounded_async_worker_delay_and_generation_reset*"],
    "T3D-17": ["tests/unit/test_sensors.py::test_imu_actual_yaw_rate_radians*"],
}


def ids_in_name(name):
    result=[]
    for group in BASE_GROUPS:
        for match in re.finditer(rf"(?<![A-Za-z0-9]){group}_((?:\d{{3}}_)*\d{{3}})(?=_|\b)", name.replace("test_", "", 1)):
            result.extend(f"{group}-{v}" for v in match.group(1).split("_"))
    result.extend("D2-"+m.group(1) for m in re.finditer(r"D2_([KCS P]\d{2})".replace(" ",""), name))
    result.extend("T3D-"+m.group(1) for m in re.finditer(r"T3D_?(\d{2})",name))
    result.extend(m.group(0) for m in re.finditer(r"(?:RULE|TIME|API|ISO|GEO|RENDER|REPLAY|E2E|PERF|PACK)-\d{3}|D2-[KCSP]\d{2}|T3D-\d{2}",name))
    return result


def generate():
    plan=ROOT/"docs/implementation_plan/docs"
    definitions={}
    for filename,source in (("07_TESTS_AND_ACCEPTANCE.md","base"),("03_PLAN_2D.md","supplemental"),("04_PLAN_3D.md","supplemental")):
        for line in (plan/filename).read_text().splitlines():
            match=re.match(r"\|\s*((?:RULE|TIME|API|ISO|GEO|RENDER|REPLAY|E2E|PERF|PACK)-\d{3}|D2-[KCSP]\d{2}|T3D-\d{2})\s*\|",line)
            if match:
                identifier=match.group(1)
                definitions[identifier]={"id":identifier,"source":source,"document":"docs/implementation_plan/docs/"+filename,
                    "requirement":" | ".join(v.strip() for v in line.strip("|").split("|")[1:]),"tests":[],"coverage":"unmapped"}
    for path in sorted((ROOT/"tests").rglob("test_*.py")):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                identifiers=ids_in_name(node.name)
                for decorator in node.decorator_list:
                    if isinstance(decorator,ast.Call):
                        for keyword in decorator.keywords:
                            if keyword.arg=="ids":
                                for value in ast.walk(keyword.value):
                                    if isinstance(value,ast.Constant) and isinstance(value.value,str):
                                        identifiers.extend(ids_in_name(value.value))
                for identifier in identifiers:
                    if identifier in definitions:
                        definitions[identifier]["tests"].append(str(path.relative_to(ROOT))+"::"+node.name+"*")
    for identifier,patterns in EXPLICIT.items():
        if identifier in definitions:
            for pattern in patterns:
                file=ROOT/pattern.split("::")[0]
                name=pattern.split("::")[1].rstrip("*")
                if file.is_file() and re.search(r"\bdef "+re.escape(name)+r"\(",file.read_text()):
                    definitions[identifier]["tests"].append(pattern)
    for identifier,entry in definitions.items():
        entry["tests"]=sorted(set(entry["tests"]))
        if entry["tests"]:
            entry["coverage"]="partial" if identifier in LIMITATIONS else "mapped"
        if identifier in LIMITATIONS:
            entry["limitation"]=LIMITATIONS[identifier]
    base=[e for e in definitions.values() if e["source"]=="base"]
    assert len(base)==152, f"Expected 152 base IDs, found {len(base)}"
    result={"schema_version":"1.0","meaning":"Coverage map only; outcomes require actual pytest execution. Partial or unrun checks do not pass a gate.",
            "base_count":len(base),"supplemental_count":len(definitions)-len(base),
            "coverage_counts":dict(Counter(e["coverage"] for e in base)),"cases":list(definitions.values())}
    (ROOT/"tests/acceptance_manifest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    artifact=ROOT/"artifacts"; artifact.mkdir(exist_ok=True)
    (artifact/"acceptance-gaps.json").write_text(json.dumps({"schema_version":"1.0","base_count":152,
        "counts":result["coverage_counts"],"gaps":[e for e in result["cases"] if e["coverage"]!="mapped"]},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"base":152,"supplemental":result["supplemental_count"],"coverage":result["coverage_counts"]}))


if __name__=="__main__":
    generate()
