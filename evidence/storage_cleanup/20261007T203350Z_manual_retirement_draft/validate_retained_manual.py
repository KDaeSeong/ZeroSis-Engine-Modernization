"""Independently recheck retained manual launch plans without starting gameplay."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
PROMOTION = ROOT / "evidence/runtime_promotion/20261007T203124Z/launcher_validation.json"
START_ENGINE = ROOT / "tools/Start-Engine.ps1"
CURRENT_MANUAL = "20261007T202612Z_d895c0fe84ab"
PWSH = Path(r"C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe")
OUTPUT_DIR = ROOT / "evidence/storage_cleanup/20261007T203350Z_manual_retirement_draft"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolved_file(path: Path, label: str) -> Path:
    require(not path.is_symlink(), f"{label} must not be a symbolic link: {path}")
    resolved = path.resolve(strict=True)
    require(resolved.is_file(), f"{label} is not a regular file: {path}")
    return resolved


def contained(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    require(resolved.is_relative_to(parent.resolve(strict=True)), f"{label} escapes its allowed directory: {path}")
    return resolved


def hidden_run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW,
        startupinfo=startup,
        check=False,
    )


def sha_records(rows: list[dict]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        path = resolved_file(Path(row["path"]), "Protected user save")
        contained(path, ROOT, "Protected user save")
        require(path.suffix.lower() == ".zssave", f"Unexpected protected file type: {path}")
        key = str(path)
        require(key not in result, f"Duplicate protected save: {path}")
        result[key] = digest(path)
    return result


def plan_once(mode: str, checkpoint: str | None) -> dict:
    command = [
        str(PWSH), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(START_ENGINE), "-Mode", mode, "-PlanOnly",
    ]
    if checkpoint:
        command.extend(["-Checkpoint", checkpoint])
    process = hidden_run(command, ROOT)
    require(process.returncode == 0, f"PlanOnly {mode} failed: {(process.stderr or process.stdout)[-2000:]}")
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"PlanOnly {mode} did not return JSON: {process.stdout[-2000:]}") from exc
    require(type(value) is dict, f"PlanOnly {mode} result is not an object")
    return value


def verify_plan(actual: dict, expected: dict, mode: str, checkpoint: str) -> dict:
    require(actual.get("requested_mode") == mode, f"Requested mode changed for {mode}")
    require(actual.get("mode") == expected.get("mode"), f"Effective mode changed for {mode}")
    require(actual.get("smoke_inputs") is False and actual.get("total_play_timeout_seconds") == 0,
            f"{mode} plan contains gameplay inputs or a timeout")

    actual_runtime = resolved_file(Path(actual["runtime"]) / "ZeroSisHost_x64.exe", f"{mode} Host").parent
    expected_runtime = Path(expected["runtime"]).resolve(strict=True)
    require(actual_runtime == expected_runtime, f"{mode} selected a different runtime")
    if mode == "New":
        require(actual_runtime.name == CURRENT_MANUAL,
                "New route no longer selects the current manual runtime")
    require(digest(actual_runtime / "ZeroSisHost_x64.exe") == actual.get("host_sha256") == expected.get("host_sha256"),
            f"{mode} Host identity changed")

    expected_launcher_name = "Play.ps1" if actual.get("mode") == "New" else "Resume.ps1"
    actual_launcher = resolved_file(Path(actual["launcher"]), f"{mode} prepared launcher")
    require(actual_launcher == actual_runtime / expected_launcher_name,
            f"{mode} selected an unexpected prepared launcher")

    actual_checkpoint = actual.get("checkpoint") or ""
    require(actual_checkpoint == (expected.get("checkpoint") or ""), f"{mode} checkpoint route changed")
    if checkpoint:
        require(Path(actual_checkpoint).resolve(strict=True) == Path(checkpoint).resolve(strict=True),
                f"Load route does not resolve to the requested save: {checkpoint}")
    elif actual_checkpoint:
        resolved_file(Path(actual_checkpoint), f"{mode} selected save")
    return {
        "requested_mode": mode,
        "mode": actual["mode"],
        "runtime": str(actual_runtime),
        "checkpoint": str(Path(actual_checkpoint).resolve(strict=True)) if actual_checkpoint else "",
        "host_sha256": actual["host_sha256"],
        "launcher": str(actual_launcher),
        "smoke_inputs": False,
        "total_play_timeout_seconds": 0,
        "plan_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New report path inside this draft directory")
    args = parser.parse_args()

    root = ROOT.resolve(strict=True)
    promotion_path = contained(PROMOTION, root / "evidence", "Launcher baseline")
    launcher_path = contained(START_ENGINE, root / "tools", "Manual launcher")
    pwsh_path = resolved_file(PWSH, "PowerShell 7 executable")
    output_parent = args.output.parent.resolve(strict=True)
    require(output_parent == OUTPUT_DIR.resolve(strict=True), "Output must be inside the manual-retirement draft directory")
    output = output_parent / args.output.name
    require(not output.exists(), f"Refusing to overwrite existing report: {output}")

    promotion_sha_before = digest(promotion_path)
    launcher_sha_before = digest(launcher_path)
    baseline = json.loads(promotion_path.read_text(encoding="utf-8-sig"))
    require(baseline.get("status") == "PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES"
            and baseline.get("count") == 10 and baseline.get("user_saves") == 8
            and baseline.get("plan_only") is True and baseline.get("gameplay_launched") is False,
            "Existing launcher validation is not the expected 10-route PlanOnly baseline")
    require(launcher_sha_before == baseline.get("launcher_sha256"), "Start-Engine.ps1 differs from the baseline launcher")

    plans = baseline.get("plans")
    saves_before_rows, saves_after_rows = baseline.get("saves_before"), baseline.get("saves_after")
    require(type(plans) is list and len(plans) == 10, "Baseline does not contain New, Continue and eight Load plans")
    require(type(saves_before_rows) is list and len(saves_before_rows) == 8
            and saves_before_rows == saves_after_rows and baseline.get("saves_unchanged") is True,
            "Baseline does not certify the exact eight preserved user saves")

    current_saves_before = sha_records(saves_before_rows)
    saved_by_path = {str(Path(row["path"]).resolve(strict=True)): row["sha256"] for row in saves_before_rows}
    require(len(saved_by_path) == 8 and current_saves_before == saved_by_path,
            "A user save is missing or differs from its baseline SHA-256")

    version = hidden_run([str(pwsh_path), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                          "$PSVersionTable.PSVersion.ToString()"], root)
    require(version.returncode == 0 and version.stdout.strip() == baseline.get("powershell_version"),
            "PowerShell version differs from the recorded PlanOnly baseline")

    verified_plans = []
    for index, expected in enumerate(plans):
        mode = expected.get("requested_mode")
        require(mode in ("New", "Continue", "Load"), f"Unexpected baseline route at index {index}")
        checkpoint = expected.get("checkpoint") or ""
        if mode == "New":
            require(not checkpoint, "New route unexpectedly has a checkpoint")
        elif mode == "Load":
            require(checkpoint in saved_by_path, f"Load route is not one of the eight protected saves: {checkpoint}")
        actual = plan_once(mode, checkpoint if mode == "Load" else None)
        verified_plans.append(verify_plan(actual, expected, mode, checkpoint))
    require([row["requested_mode"] for row in verified_plans].count("New") == 1
            and [row["requested_mode"] for row in verified_plans].count("Continue") == 1
            and [row["requested_mode"] for row in verified_plans].count("Load") == 8,
            "Did not verify the required New/Continue/eight-Load route matrix")

    current_saves_after = sha_records(saves_before_rows)
    require(current_saves_after == current_saves_before, "A protected user save changed during PlanOnly checks")
    require(digest(promotion_path) == promotion_sha_before and digest(launcher_path) == launcher_sha_before,
            "Launcher baseline or Start-Engine.ps1 changed during verification")

    report = {
        "status": "PASS_RETAINED_MANUAL_PLANONLY_AND_USER_SAVE_HASHES",
        "gameplay_launched": False,
        "plan_only": True,
        "process_window": "hidden",
        "powershell_version": version.stdout.strip(),
        "verifier": {"path": str(Path(__file__).resolve(strict=True)), "sha256": digest(Path(__file__).resolve(strict=True))},
        "launcher": {"path": str(launcher_path), "sha256_before": launcher_sha_before, "sha256_after": digest(launcher_path)},
        "baseline": {"path": str(promotion_path), "sha256_before": promotion_sha_before, "sha256_after": digest(promotion_path)},
        "powershell_executable": {"path": str(pwsh_path), "sha256": digest(pwsh_path)},
        "routes": verified_plans,
        "user_saves": [{"path": path, "sha256_before": current_saves_before[path],
                        "sha256_after": current_saves_after[path]} for path in sorted(current_saves_before)],
        "user_saves_unchanged": True,
    }
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "routes": len(verified_plans),
                      "user_saves": len(current_saves_after), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"VALIDATION_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
