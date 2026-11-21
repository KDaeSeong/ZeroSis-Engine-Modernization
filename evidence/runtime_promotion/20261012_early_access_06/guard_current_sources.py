"""Preserve the current Host's 64 original translation-unit and header inputs."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import prune_selected_ui_hosts as guard

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("phase", choices=("before", "after"))
parser.add_argument("plan")
args = parser.parse_args()
plan_path = guard.safety.boundary(Path(args.plan))
guard.require(plan_path.is_relative_to(ROOT / "evidence/storage_cleanup/selected_ui_host_plans"), "Unexpected plan")
plan_sha = guard.safety.digest(plan_path)
guard.require(plan_sha == "c245f5880e012028a4dd9646c24020373a8a75f9a358ba4754541571af21c9c1", "Different reviewed plan")
host_path = ROOT / "evidence/ui_window_host/20261011T124501Z_5bf7bf678d40/build_result.json"
host = json.loads(host_path.read_text(encoding="utf-8-sig"))
sources = []
lua_sources = []
for row in host["sources"]:
    path, info = guard.checked_file(row["original_source"])
    guard.require(path.is_relative_to(ROOT / "Source"), "Original input escaped Source")
    sha = guard.safety.digest(path)
    guard.require(guard.file_metadata(path.lstat()) == guard.file_metadata(info), "Source metadata changed while hashing")
    record = dict(path=str(path), sha256=sha, identity=list(guard.identity(info)), metadata=guard.file_metadata(info))
    if path.suffix.lower() == ".lua":
        record.update(host_frozen_sha256=row["sha256"], changed_since_host_snapshot=sha != row["sha256"])
        lua_sources.append(record)
    else:
        guard.require(path.suffix.lower() in (".cpp", ".h", ".hpp", ".hh") and sha == row["sha256"],
                      "Current C++ source differs from frozen Host input")
        sources.append(record)
sources.sort(key=lambda row: row["path"])
lua_sources.sort(key=lambda row: row["path"])
guard.require(len(sources) == 64 and len(lua_sources) == 10, "Unexpected Host input count")
if args.phase == "after":
    before = json.loads((plan_path.parent / "source_guard_before.json").read_text(encoding="utf-8"))
    guard.require(before["plan_sha256"] == plan_sha and before["sources"] == sources and before["lua_sources"] == lua_sources,
                  "Source changed across retirement")
result = dict(status="CURRENT_HOST_64_SOURCE_CONTENT_AND_METADATA_PASS", phase=args.phase, plan_sha256=plan_sha,
              host_result_sha256=guard.safety.digest(host_path), sources=sources, source_count=len(sources),
              lua_sources=lua_sources, lua_source_count=len(lua_sources),
              lua_annotation_drift_count=sum(row["changed_since_host_snapshot"] for row in lua_sources),
              outside_source_mutation=False)
output = plan_path.parent / ("source_guard_" + args.phase + ".json")
guard.require(not output.exists(), "Refuse to replace a source guard")
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(dict(status=result["status"], phase=args.phase, source_count=64, lua_sources=10,
                     lua_annotation_drift=result["lua_annotation_drift_count"], report=str(output))))
