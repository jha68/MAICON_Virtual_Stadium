"""Check the evidence inventory's integrity, without fabricating missing tests."""
import ast
import json
from pathlib import Path
import re


ROOT=Path(__file__).resolve().parents[1]


def test_acceptance_inventory_has_every_documented_identifier_once():
    manifest=json.loads((ROOT/"tests/acceptance_manifest.json").read_text())
    base=[case for case in manifest["cases"] if case["source"]=="base"]
    expected=set(re.findall(r"^\|\s*((?:RULE|TIME|API|ISO|GEO|RENDER|REPLAY|E2E|PERF|PACK)-\d{3})\s*\|",
        (ROOT/"docs/implementation_plan/docs/07_TESTS_AND_ACCEPTANCE.md").read_text(),re.M))
    assert len(base)==len(expected)==152
    assert len({case["id"] for case in manifest["cases"]})==len(manifest["cases"])
    assert {case["id"] for case in base}==expected
    assert all(case["coverage"] in ("mapped","partial","unmapped") for case in manifest["cases"])
    assert all(case["coverage"]!="unmapped" or not case["tests"] for case in manifest["cases"])


def test_acceptance_patterns_reference_real_test_functions():
    manifest=json.loads((ROOT/"tests/acceptance_manifest.json").read_text())
    for case in manifest["cases"]:
        for pattern in case["tests"]:
            path,name=pattern.split("::")
            tree=ast.parse((ROOT/path).read_text())
            names={node.name for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
            assert name.rstrip("*") in names,(case["id"],pattern)
