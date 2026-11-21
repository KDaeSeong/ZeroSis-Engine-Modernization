"""Apply only the reviewed failed-Host pair through the shared safe-unlink contract."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(os.path.abspath(__file__)).parents[3]
FAILED = "20261008T115403Z_7b2d941d8dc2"
EXPECTED_DIRS = {
    f"Build/UiWindowHost/{FAILED}".replace("/", os.sep),
    f"evidence/ui_window_host/{FAILED}".replace("/", os.sep),
}
CONTRACT_FILE = ROOT / "tools/prune_superseded_runtime_artifacts.py"

def require(value, message):
    if not value:
        raise RuntimeError(message)

def load_contract():
    spec = importlib.util.spec_from_file_location("runtime_retirement_contract", CONTRACT_FILE)
    require(spec and spec.loader, "Cannot load safe unlink contract")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    require(module.ROOT == ROOT, "Cleanup contract resolved a different project root")
    def lexical_boundary(path: Path) -> Path:
        absolute = Path(os.path.abspath(path))
        require(absolute.is_relative_to(ROOT) and absolute != ROOT,
                "Outside project: " + str(path))
        current = absolute
        while True:
            info = current.lstat()
            require(not getattr(info, "st_file_attributes", 0) & 0x400,
                    "Reparse point or ancestor: " + str(current))
            if current == ROOT:
                break
            parent = current.parent
            require(parent != current, "Project root was not reached: " + str(path))
            current = parent
        return absolute
    module.boundary = lexical_boundary
    return module

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", type=Path, required=True)
    args = parser.parse_args()
    contract = load_contract()
    plan_path = contract.boundary(args.apply)
    output = contract.boundary(Path(os.path.abspath(__file__)).parent)
    require(plan_path.parent == output and plan_path.name == "plan.json",
            "Plan must be this draft folder's exact plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    require(plan.get("status") == "PREVIEW_ONLY" and plan.get("root") == str(ROOT) and
            plan.get("scope") == "EXACT_FAILED_UI_WINDOW_HOST_BUILD_AND_EVIDENCE_PAIR" and
            plan.get("retirement_run_ids") == [FAILED],
            "Plan identity or scope differs from this reviewed failed-Host cleanup")
    observed = {row["path"].replace("/", os.sep) for row in plan.get("directories", [])}
    require(observed == EXPECTED_DIRS and len(plan.get("directories", [])) == 2,
            "Plan does not contain exactly the reviewed failed Host Build/evidence pair")
    require(plan.get("deletion_performed") is False and
            plan.get("source_tests_tools_docs_game_mods_and_user_saves_deleted") is False,
            "Plan indicates a broader or already-applied action")
    contract.apply(plan_path)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RETIREMENT_NOT_APPLIED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)

