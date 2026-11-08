"""Record actual acceptance evidence without turning missing tests green."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
_reports={}
_collected=[]


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(session,config,items):
    _collected.extend(item.nodeid for item in items)


def pytest_runtest_logreport(report):
    item=_reports.setdefault(report.nodeid,{"nodeid":report.nodeid,"outcome":"not_run","duration_s":0.0,"phases":{}})
    item["duration_s"]+=report.duration
    item["phases"][report.when]=report.outcome
    for name,value in report.user_properties:
        if name=="acceptance_context":
            item["context"]=value
    if report.failed:
        item["outcome"]="failed"
        item["failure"]=str(report.longrepr)[:2000]
    elif report.skipped and item["outcome"]!="failed":
        item["outcome"]="skipped"
        item["skip_reason"]=str(report.longrepr)[:500]
    elif report.when=="call" and report.passed and item["outcome"] not in ("failed","skipped"):
        item["outcome"]="passed"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    if report.when!="call":
        return
    candidates=list(item.funcargs.values())
    for value in list(candidates):
        if isinstance(value,tuple):
            candidates.extend(value)
    cfg=next((v for v in candidates if all(hasattr(v,k) for k in ("scenario","rules","arena","sensors"))),None)
    if cfg is None:
        cfg=next((getattr(v,"config",None) for v in candidates if hasattr(getattr(v,"config",None),"scenario")),None)
    context={"rule_profile_hash":None,"scenario_hash":None,"seed":None,"backend":"not_applicable",
             "sensor_mode":"not_applicable"}
    if cfg is not None:
        def digest(value):
            return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        context.update(rule_profile_hash=digest(cfg.rules),scenario_hash=digest(cfg.scenario),seed=cfg.scenario["seed"],
                       backend="core",sensor_mode=cfg.scenario["noise_profile"])
    report.user_properties.append(("acceptance_context",context))


def pytest_sessionfinish(session,exitstatus):
    manifest_path=ROOT/"tests/acceptance_manifest.json"
    if not manifest_path.exists():
        return
    manifest=json.loads(manifest_path.read_text())
    def command(args):
        try:
            p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
        except OSError:
            return None
        return p.stdout.strip() if p.returncode==0 else None
    for nodeid in _collected:
        _reports.setdefault(nodeid,{"nodeid":nodeid,"outcome":"not_run","duration_s":0.,"phases":{}})
    cases=[]
    for entry in manifest["cases"]:
        matched=sorted(n for n in _reports if any(fnmatch.fnmatchcase(n,p) for p in entry["tests"]))
        statuses=[_reports[n]["outcome"] for n in matched]
        if not statuses: outcome="not_run"
        elif "failed" in statuses: outcome="failed"
        elif "not_run" in statuses: outcome="not_run"
        elif "skipped" in statuses: outcome="skipped"
        else: outcome="passed"
        acceptance=outcome
        if outcome=="passed" and entry["coverage"]!="mapped":
            acceptance="partial"
        # Explicit node/file selections cannot establish complete parametric
        # acceptance coverage. Full-suite CI invocations collect every case.
        args=[str(v) for v in session.config.args]
        full_collection=not args or args==["tests"] or args==[str(ROOT/"tests")]
        if acceptance=="passed" and not full_collection:
            acceptance="selected_tests_passed"
        cases.append({"test_id":entry["id"],"source":entry["source"],"coverage":entry["coverage"],
                      "outcome":outcome,"acceptance_outcome":acceptance,"tests":matched,
                      **({"limitation":entry["limitation"]} if "limitation" in entry else {})})
    lock=ROOT/"uv.lock"
    report={"schema_version":"1.0","generated_at":datetime.now(timezone.utc).isoformat(),
      "source_commit":command(["git","rev-parse","--verify","HEAD"]),
      "simulator_version":"0.1.0","dependency_lock_hash":hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
      "platform":platform.platform(),"python":platform.python_version(),"pytest_args":session.config.invocation_params.args,
      "exit_status":int(exitstatus),"collected":len(_collected),"test_counts":dict(Counter(v["outcome"] for v in _reports.values())),
      "base_acceptance_counts":dict(Counter(e["acceptance_outcome"] for e in cases if e["source"]=="base")),
      "cases":cases,"tests":list(_reports.values())}
    all_ids={case["test_id"] for case in cases}
    g0={v for v in all_ids if v.split("-")[0] in ("RULE","TIME","API","ISO")}|{"PACK-006","PACK-007"}
    g1=g0|{v for v in all_ids if v.startswith(("GEO-","D2-"))}
    g1|={f"E2E-{i:03}" for i in (1,2,3,8,9,10,12)}
    g2=g1|{v for v in all_ids if v.startswith(("RENDER-","T3D-"))}
    report["gates"]={}
    by_id={case["test_id"]:case for case in cases}
    for gate,required in (("G0",g0),("G1",g1),("G2",g2),("G3",all_ids)):
        unresolved=[v for v in sorted(required) if by_id[v]["acceptance_outcome"]!="passed"]
        report["gates"][gate]={"status":"passed" if not unresolved else "in_progress",
            "required_count":len(required),"unresolved":unresolved}
    # Exact test inputs (scenario/profile/seed/backend) are recorded in fixture
    # artifacts/run manifests; do not invent a single condition for this suite.
    target=Path(os.environ.get("MAICON_TEST_RESULTS",str(ROOT/"artifacts/test-results.json")))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
