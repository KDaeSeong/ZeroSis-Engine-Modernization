"""Build a narrow PREVIEW_ONLY retirement plan for one failed UI Host run."""
from __future__ import annotations
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
FAILED = "20261008T115403Z_7b2d941d8dc2"
PASSED = "20261008T115702Z_523eb1f915f7"
ACTIVE_SOURCE = "20261008T115935Z_1dd44881d206"
EXPECTED_PASS_SHA = "c29b37f1cfea49be78c63714376b71834233c95eff9311758bc675e287a39dda"
CURRENT_MANUAL = "20261007T202612Z_d895c0fe84ab"
CURRENT_MANUAL_HOST_SHA = "7d75dbd22b7bc08ff57df6d2ff96b87e5f37698bbe68ca8aa563ace1ed8a4fca"
PROMOTION = ROOT / "evidence/runtime_promotion/20261007T203124Z"
CONTRACT_FILE = ROOT / "tools/prune_superseded_runtime_artifacts.py"
RUN = __import__("re").compile(r"\d{8}T\d{6}Z_[0-9a-f]{12}")

def require(value, message):
    if not value:
        raise RuntimeError(message)

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_contract():
    spec = importlib.util.spec_from_file_location("runtime_retirement_contract", CONTRACT_FILE)
    require(spec and spec.loader, "Cannot load safe unlink contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    require(module.ROOT == ROOT, "Cleanup contract resolved a different project root")
    return module

def lexical_boundary(path: Path) -> Path:
    """Check the project boundary and ancestors without following reparse points."""
    absolute = Path(os.path.abspath(path))
    require(absolute.is_relative_to(ROOT) and absolute != ROOT, "Outside project: " + str(path))
    current = absolute
    while True:
        info = current.lstat()
        require(not getattr(info, "st_file_attributes", 0) & 0x400, "Reparse point or ancestor: " + str(current))
        if current == ROOT:
            break
        parent = current.parent
        require(parent != current, "Project root was not reached: " + str(path))
        current = parent
    return absolute

def add_protected(protected: dict[str, str], path: Path, expected: str | None = None):
    path = contract.boundary(path)
    info = contract.regular(path)
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    actual = digest(path)
    require(expected is None or actual.lower() == expected.lower(), "Protected baseline changed: " + str(path))
    require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
             path.stat().st_mtime_ns) == identity, "Protected file changed while hashing: " + str(path))
    protected[str(path)] = actual
    return actual

contract = load_contract()
contract.boundary = lexical_boundary
output = contract.boundary(Path(os.path.abspath(__file__)).parent)
require(output.is_relative_to(ROOT / "evidence/storage_cleanup"), "Output outside cleanup evidence")
plan_path = output / "plan.json"
require(not plan_path.exists() and not (output / "cleanup.json").exists(),
        "Refusing to overwrite or replay an existing cleanup plan")

targets = [
    contract.legal_target(ROOT / "Build/UiWindowHost" / FAILED),
    contract.legal_target(ROOT / "evidence/ui_window_host" / FAILED),
]
require(len(set(targets)) == 2 and all(path.is_dir() for path in targets),
        "The exact failed Build/evidence pair is not present")
require(RUN.fullmatch(FAILED) and RUN.fullmatch(PASSED) and RUN.fullmatch(ACTIVE_SOURCE),
        "Malformed reviewed run ID")
require(FAILED < PASSED and FAILED != PASSED, "Failed run is not a distinct older Host run")

failed_result_path = targets[1] / "build_result.json"
failed_result = json.loads(failed_result_path.read_text(encoding="utf-8-sig"))
require(failed_result.get("build_id") == FAILED and
        failed_result.get("status") == "UI_WINDOW_HOST_BUILD_FAILED" and
        failed_result.get("executable") is None and
        failed_result.get("host_runtime_executed") is False and
        failed_result.get("mods_updated") is False and
        failed_result.get("stage_updated") is False and
        "C4063" in failed_result.get("error", ""),
        "Failed Host evidence no longer matches the reviewed enum-switch dependency-discovery failure")

passed_result_path = ROOT / "evidence/ui_window_host" / PASSED / "build_result.json"
passed_result = json.loads(contract.boundary(passed_result_path).read_text(encoding="utf-8-sig"))
require(passed_result.get("build_id") == PASSED and
        passed_result.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
        passed_result.get("source_inputs_unchanged") is True,
        "Passed replacement Host result is missing or no longer passing")
passed_exe = contract.boundary(Path(passed_result["executable"]["path"]))
require(passed_exe.is_relative_to((ROOT / "Build/UiWindowHost" / PASSED)) and
        passed_result["executable"]["sha256"].lower() == EXPECTED_PASS_SHA and
        digest(passed_exe) == EXPECTED_PASS_SHA,
        "Passed replacement Host executable identity differs")

source_request_path = ROOT / "evidence/interactive_game" / ACTIVE_SOURCE / "request.json"
source_request = json.loads(contract.boundary(source_request_path).read_text(encoding="utf-8-sig"))
source_hosts = [row for row in source_request.get("runtime_inputs", [])
                if Path(row.get("path", "")).name == "ZeroSisHost_x64.exe"]
require(source_request.get("run_id") == ACTIVE_SOURCE and source_request.get("smoke") is True and
        len(source_hosts) == 1 and source_hosts[0].get("sha256", "").lower() == EXPECTED_PASS_SHA,
        "Current running source run does not identify the passed replacement Host")
source_request_sha = digest(source_request_path)

launcher = contract.boundary(ROOT / "tools/Start-Engine.ps1")
launcher_text = launcher.read_text(encoding="utf-8-sig")
require(CURRENT_MANUAL in launcher_text and FAILED not in launcher_text and PASSED not in launcher_text,
        "Stable launcher selection changed or names a cleanup candidate")
promotion_path = contract.boundary(PROMOTION / "promotion.json")
validation_path = contract.boundary(PROMOTION / "launcher_validation.json")
promotion = json.loads(promotion_path.read_text(encoding="utf-8-sig"))
validation = json.loads(validation_path.read_text(encoding="utf-8-sig"))
require(promotion.get("status") == "PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES" and
        promotion.get("run_id") == CURRENT_MANUAL and
        promotion.get("launcher_sha256") == digest(launcher) and
        validation.get("status") == "PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES" and
        validation.get("count") == 10 and validation.get("user_saves") == 8 and
        validation.get("saves_unchanged") is True and validation.get("gameplay_launched") is False,
        "Stable manual promotion or its 10-route PlanOnly validation changed")
manual_request_path = ROOT / "evidence/interactive_game" / CURRENT_MANUAL / "request.json"
manual_request = json.loads(contract.boundary(manual_request_path).read_text(encoding="utf-8-sig"))
manual_hosts = [row for row in manual_request.get("runtime_inputs", [])
                if Path(row.get("path", "")).name == "ZeroSisHost_x64.exe"]
require(manual_request.get("run_id") == CURRENT_MANUAL and manual_request.get("smoke") is False and
        len(manual_hosts) == 1 and manual_hosts[0].get("sha256", "").lower() == CURRENT_MANUAL_HOST_SHA,
        "Current manual runtime is no longer bound to its retained Host")

protected: dict[str, str] = {}
protected_files = [
    launcher, promotion_path, validation_path, manual_request_path,
    ROOT / "Build/InteractiveGameRuntime" / CURRENT_MANUAL / "Play.ps1",
    ROOT / "Build/InteractiveGameRuntime" / CURRENT_MANUAL / "bundle.manifest",
    ROOT / "Build/InteractiveGameRuntime" / CURRENT_MANUAL / "ZeroSisHost_x64.exe",
    passed_result_path, passed_exe,
    source_request_path,
]
for path in protected_files:
    add_protected(protected, path)
require(protected[str(passed_exe)].lower() == EXPECTED_PASS_SHA,
        "Passed Host was not recorded as protected")

save_rows = validation.get("saves_before")
require(isinstance(save_rows, list) and len(save_rows) == 8 and
        save_rows == validation.get("saves_after"),
        "Expected eight unchanged user-save records")
for row in save_rows:
    save_path = Path(row["path"])
    require(save_path.is_absolute(), "User-save path is not absolute")
    add_protected(protected, save_path, row["sha256"])

# Preserve the current manual Host build identity as an explicit check.
manual_host_exe = ROOT / "Build/InteractiveGameRuntime" / CURRENT_MANUAL / "ZeroSisHost_x64.exe"
require(protected[str(contract.boundary(manual_host_exe))].lower()
        == CURRENT_MANUAL_HOST_SHA, "Stable manual Host hash differs")

candidate_rows = []
directory_summaries = []
for target in targets:
    count = total = 0
    for path, info in contract.inventory(target):
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        sha = digest(path)
        require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
                 path.stat().st_mtime_ns) == identity, "Candidate changed during hashing: " + str(path))
        candidate_rows.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": sha,
            "bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "device": info.st_dev,
            "file_id": info.st_ino,
        })
        count += 1
        total += info.st_size
    directory_summaries.append({"path": str(target.relative_to(ROOT)),
                                "files": count, "logical_bytes": total})
require(candidate_rows and len({row["path"] for row in candidate_rows}) == len(candidate_rows),
        "Candidate inventory is empty or contains duplicate paths")
for path in protected:
    p = Path(path)
    require(all(not p.is_relative_to(target) for target in targets),
            "Protected path overlaps the exact retirement pair: " + path)

archive_path = output / "failed-host-build-result.json.gz"
summary_path = output / "failure-summary.json"
ledger_path = output / "retired-files.jsonl.gz"
protected_path = output / "protected.json.gz"
require(not any(path.exists() for path in (archive_path, summary_path, ledger_path, protected_path)),
        "Draft output already contains a generated artifact")
with gzip.open(archive_path, "wb", compresslevel=9) as stream:
    stream.write(failed_result_path.read_bytes())
with gzip.open(ledger_path, "wt", encoding="utf-8") as stream:
    for row in sorted(candidate_rows, key=lambda row: row["path"].casefold()):
        stream.write(json.dumps(row, separators=(",", ":")) + "\n")
with gzip.open(protected_path, "wt", encoding="utf-8") as stream:
    json.dump(protected, stream, separators=(",", ":"))
failure_summary = {
    "status": "REVIEWED_FAILED_HOST_BUILD_RETIREMENT_CANDIDATE",
    "failed_host_run": FAILED,
    "failed_host_status": failed_result["status"],
    "failure_reason": "Dependency discovery stopped on C4063 enum-switch warning in InteractiveUiSession.h; executable absent.",
    "failed_result_sha256": digest(failed_result_path),
    "failed_result_archive": str(archive_path.relative_to(ROOT)),
    "failed_result_archive_sha256": digest(archive_path),
    "failed_host_runtime_executed": False,
    "mods_updated": False,
    "stage_updated": False,
    "replacement_host_run": PASSED,
    "replacement_host_sha256": EXPECTED_PASS_SHA,
    "active_source_run": ACTIVE_SOURCE,
    "active_source_request_sha256": source_request_sha,
}
summary_path.write_text(json.dumps(failure_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
require(digest(failed_result_path) == digest(archive_path) if False else True,
        "Archive comparison is performed below")
with gzip.open(archive_path, "rb") as stream:
    require(stream.read() == failed_result_path.read_bytes(),
            "Compressed original build_result does not decompress byte-exactly")

plan = {
    "status": "PREVIEW_ONLY",
    "scope": "EXACT_FAILED_UI_WINDOW_HOST_BUILD_AND_EVIDENCE_PAIR",
    "root": str(ROOT),
    "retirement_run_ids": [FAILED],
    "failed_host_run": FAILED,
    "failed_host_status": failed_result["status"],
    "failure_summary": {"path": str(summary_path.relative_to(ROOT)), "sha256": digest(summary_path)},
    "failed_build_result_archive": {"path": str(archive_path.relative_to(ROOT)),
                                    "sha256": digest(archive_path),
                                    "source_sha256": digest(failed_result_path)},
    "replacement_host": {"run_id": PASSED, "sha256": EXPECTED_PASS_SHA,
                         "result_path": str(passed_result_path.relative_to(ROOT)),
                         "source_inputs_unchanged": True},
    "active_source_run": {"run_id": ACTIVE_SOURCE,
                          "request_path": str(source_request_path.relative_to(ROOT)),
                          "request_sha256": source_request_sha,
                          "currently_running": True},
    "stable_manual": {"run_id": CURRENT_MANUAL,
                      "host_sha256": CURRENT_MANUAL_HOST_SHA,
                      "launcher_sha256": digest(launcher),
                      "user_save_count": 8,
                      "user_saves_unchanged": True},
    "directories": directory_summaries,
    "files": len(candidate_rows),
    "logical_bytes": sum(row["bytes"] for row in candidate_rows),
    "candidate_file_identity_fields": ["path", "device", "file_id", "bytes", "mtime_ns", "sha256"],
    "protected_file_count": len(protected),
    "protected": {"path": str(protected_path), "sha256": digest(protected_path)},
    "ledger": {"path": str(ledger_path), "sha256": digest(ledger_path)},
    "script_sha256": contract.digest(CONTRACT_FILE),
    "deletion_performed": False,
    "source_tests_tools_docs_game_mods_and_user_saves_deleted": False,
}
plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({
    "status": plan["status"],
    "plan": str(plan_path),
    "candidate_directories": directory_summaries,
    "candidate_files": plan["files"],
    "candidate_logical_bytes": plan["logical_bytes"],
    "protected_file_count": len(protected),
    "protected_keys_verified": [
        "stable manual runtime + embedded Host",
        "Start-Engine.ps1",
        "10-route PlanOnly launcher promotion",
        "8 exact user saves",
        "passed replacement Host result + executable",
        "current source smoke request selects passed Host SHA",
    ],
    "failure_summary": str(summary_path),
    "compressed_original_build_result": str(archive_path),
    "apply_command": f'"{sys.executable}" "{CONTRACT_FILE}" --apply "{plan_path}"',
}, ensure_ascii=False))




