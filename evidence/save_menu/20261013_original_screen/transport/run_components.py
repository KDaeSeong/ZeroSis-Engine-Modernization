"""Run existing focused conformance tools with isolated SaveMenu evidence paths."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
BUILD = ROOT / "Build" / "SaveMenuTransport"


def ref(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--suite", choices=("bitmap", "dispatch"), required=True)
    suite = args.parse_args().suite
    tool_name = "verify_bitmap_window.py" if suite == "bitmap" else "verify_ui_input_dispatch.py"
    tool = ROOT / "tools" / tool_name
    sys.path.insert(0, str(tool.parent))
    spec = importlib.util.spec_from_file_location("save_menu_" + suite, tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_record = {"schema": "ZEROSIS_FOCUSED_TRANSPORT_RUN_V1", "suite": suite,
                  "wrapper": ref(Path(__file__).resolve()), "verifier": ref(tool),
                  "path_overrides_only": True, "test_logic_modified_by_wrapper": False,
                  "full_host_build": False, "retail_game_launched": False,
                  "human_input_verified": False, "physical_korean_ime_verified": False}
    source_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(4)
    source_snapshot = EVIDENCE / "launches" / "source" / (source_stamp + "_" + suite + ".py")
    source_snapshot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve(), source_snapshot)
    run_record["wrapper_snapshot"] = ref(source_snapshot)
    if suite == "bitmap":
        def allocate():
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(6)
            build = BUILD / "B" / run_id[-12:]
            evidence = EVIDENCE / "bitmap" / run_id
            build.mkdir(parents=True, exist_ok=False)
            evidence.mkdir(parents=True, exist_ok=False)
            run_record.update(run_id=run_id, build=str(build), evidence=str(evidence))
            return run_id, build, evidence
        module.allocate = allocate
    else:
        module.EVIDENCE_ROOT = EVIDENCE / "dispatch"
        module.BUILD_ROOT = BUILD / "UiInputDispatch"
        original_run = module.run

        def run(command, **kwargs):
            command = list(command)
            if len(command) > 1 and Path(command[1]) == module.LEGACY_TOOL:
                index = command.index("--evidence-root") + 1
                legacy_id = Path(command[index]).name
                command[index] = EVIDENCE / "L" / legacy_id
                index = command.index("--build-root") + 1
                command[index] = BUILD / "UiInputLua" / legacy_id
                run_record.update(legacy_evidence=str(EVIDENCE / "L" / legacy_id),
                                  legacy_build=str(BUILD / "UiInputLua" / legacy_id))
            return original_run(command, **kwargs)
        module.run = run
    previous_argv = sys.argv
    sys.argv = [str(tool)]
    try:
        code = module.main()
    except Exception as exc:
        run_record.update(exit_code=1, wrapper_failure=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        sys.argv = previous_argv
        run_record.setdefault("exit_code", locals().get("code", 1))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(4)
        path = EVIDENCE / "launches" / (stamp + "_" + suite + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"suite": suite, "exit_code": run_record["exit_code"],
                          "launch_receipt": str(path)}, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
