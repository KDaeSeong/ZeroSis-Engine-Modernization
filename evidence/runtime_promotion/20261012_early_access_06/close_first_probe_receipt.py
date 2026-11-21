"""Record the closed first probe and preserve its own save outside Continue."""
from pathlib import Path
import hashlib
import json
import runpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LAUNCH = ROOT / "evidence/manual_play/20261012T123941Z_6e96908b7ad2"
SESSION = ROOT / "Build/InteractiveGameRuntime/20261012T121847Z_732a6d5f07ea/sessions/6af97b586aa2c9f109fd0ba55754f43a"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    output = HERE / "first_probe_close.json"
    assert not output.exists()
    launch = json.loads((LAUNCH / "launch.json").read_text(encoding="utf-8-sig"))
    driver = json.loads((LAUNCH / "driver_result.json").read_text(encoding="utf-8-sig"))
    assert launch["status"] == "CLOSED" and driver["status"] == "INTERACTIVE_UI_DRIVER_PASS"
    assert driver["returncode"] == 0 and driver["command"][1] == "--play"
    probe = runpy.run_path(str(HERE / "manual_probe.py"), run_name="probe_cleanup")
    assert probe["find_owned_host"](int(launch["driver_pid"])) is None
    assert SESSION.resolve(strict=True) == SESSION
    source = SESSION / "play-save-1-turn-0.zssave"
    target = source.with_name("verification-" + source.name)
    assert source.is_file() and not target.exists()
    info = source.stat()
    digest = sha(source)
    source.rename(target)
    current = target.stat()
    assert (current.st_ino, current.st_size, current.st_mtime_ns) == (info.st_ino, info.st_size, info.st_mtime_ns)
    assert sha(target) == digest
    record = {
        "status": "FIRST_PROBE_LOG_LOCK_FAILURE_PRESERVED_NATIVE_NEW_CLOSED",
        "original_native_result_reclassified": False,
        "native_new_close_pass": True, "f5_save_verified": False,
        "original_path": str(source), "verification_path": str(target),
        "bytes": current.st_size, "sha256": digest, "file_id": str(current.st_ino),
        "driver_result_sha256": sha(LAUNCH / "driver_result.json"),
        "scope": "Only first machine-created test save; no user save touched.",
    }
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "bytes": record["bytes"], "sha256": digest}))


if __name__ == "__main__":
    main()
