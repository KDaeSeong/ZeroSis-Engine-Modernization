"""Feed one length-prefix hypothesis to the retained pure Game/Map diagnostic.

Only pinned public fixtures are downloaded. Raw/inflated bytes stay in RAM.
Neither successful framing nor an open zlib stream approves a retail save.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.request
import zlib

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/retail_save_container/map_trace"
REFERENCE = STAGE / "input_chunk_comparison.json"
RESULT = STAGE / "declared_frames_trace.json"
EXE = PROJECT / "Build/RetailMapTrace/e0227998ab0433775c3e/RetailPublicProbe.exe"
EXE_SHA = "8861786cd5e2c3e5d0579574ca9813fa6013f4db29ba03fe0ea3314112f72838"
MAX_OUTPUT = 64 * 1024 * 1024


def main():
    assert len(sys.argv) == 1 and os.name == "nt" and not sys.flags.optimize
    helper = PROJECT / "tools/probe_public_retail_save.py"
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962"
    import probe_public_retail_save as g
    assert Path(g.__file__).absolute() == helper
    def checked_artifact(row):
        current = g.artifact(row["path"])
        for field in ("bytes", "sha256", "file_identity", "mtime_ns"):
            if field in row:
                assert current[field] == row[field], "Changed pinned artifact: " + row["path"]
        return current
    assert not RESULT.exists()
    reference_pin = g.artifact(REFERENCE)
    assert reference_pin["sha256"] == "04972c76cb6818e21e178363be4bc7ff7da74768f0c62b6d69f5ff3f8504b390"
    prior = g.read_json(REFERENCE)
    own = g.artifact(Path(__file__).absolute())
    executable = g.artifact(EXE)
    assert executable["sha256"] == EXE_SHA and executable["bytes"] == 310784
    build_path = STAGE / "compile_e0227998ab0433775c3e/build_result.json"
    build_pin = g.artifact(build_path)
    assert build_pin["sha256"] == "0158201613a64c4755312a8082171457ef529e3f0a69f0c8efefb4b846cbce14"
    build = g.read_json(build_path)
    preflight_path = STAGE / "input_chunk_preflight.json"
    preflight = g.read_json(preflight_path)
    baseline = g.read_json(Path(preflight["protected_baseline"]["path"]))
    revisions = {row["path"]: row for row in preflight["intentional_metadata_revisions"].values()}
    protected = [checked_artifact(revisions.get(row["path"], row)) for row in baseline["protected"]]
    inputs = [own, reference_pin, executable, build_pin, g.artifact(helper), g.artifact(preflight_path)]
    inputs += [g.artifact(row["path"]) for row in prior["inputs"]]
    inputs += build["inputs"] + list(build["artifacts"].values())
    inputs = [checked_artifact(row) for row in inputs]
    g.unchanged(inputs + protected)
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    buffers = []
    for case in prior["cases"]:
        fixture = case["fixture"]
        request = urllib.request.Request(fixture["raw_url"], headers={"User-Agent": "ZeroSis-offline-fixture-audit"})
        with opener.open(request, timeout=20) as response:
            assert response.geturl() == fixture["raw_url"]
            raw = response.read(fixture["bytes"] + 1)
        assert len(raw) == fixture["bytes"] and hashlib.sha256(raw).hexdigest() == case["raw_sha256"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest() == fixture["git_blob_sha1"]
        framing = case["declared_frame_candidate"]
        assert framing["declared_lengths_cover_input"] and framing["start"] == case["compressed_offset"] - 4
        position = framing["start"]
        decoder = zlib.decompressobj()
        output = bytearray()
        for frame in framing["frames"]:
            assert frame["length_offset"] == position and 0 < frame["bytes"] <= 65536
            assert int.from_bytes(raw[position:position + 4], "little") == frame["bytes"]
            begin = position + 4
            assert begin == frame["payload_offset"] and frame["bytes"] <= len(raw) - begin
            payload = raw[begin:begin + frame["bytes"]]
            assert hashlib.sha256(payload).hexdigest() == frame["payload_sha256"]
            assert len(output) < MAX_OUTPUT
            output.extend(decoder.decompress(payload, MAX_OUTPUT - len(output)))
            assert not decoder.unconsumed_tail and not decoder.unused_data
            position = begin + frame["bytes"]
        assert position == len(raw)
        expected = framing["candidate_zlib"]
        assert len(output) == expected["output_bytes"] and hashlib.sha256(output).hexdigest() == expected["output_sha256"]
        assert decoder.eof == expected["eof"]
        buffers.append((case, bytes(output)))
    # Keep the exact original awards and bool policy for a before/after comparison.
    commands = [(str(EXE), "--awards", "5", "--boolean-encoding", "sdk-byte",
                 "--max-input", str(len(data))) for _case, data in buffers]
    assert len(commands) == 2 and len(set(commands)) == 2
    guard = g.OfflineGuard(commands=commands, directory=EXE.parent,
        readable=[Path(row["path"]) for row in inputs + protected], writable=[RESULT], directories=[])
    sys.addaudithook(guard.audit)
    observations = []
    for (case, data), command in zip(buffers, commands):
        completed = subprocess.run(command, cwd=EXE.parent, input=data, capture_output=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        assert completed.returncode in (0, 1) and len(completed.stdout) <= 64 * 1024 and len(completed.stderr) <= 16 * 1024
        native = json.loads(completed.stdout.decode("utf-8-sig"))
        assert native["schema"] == "zerosis.retail.map_trace.v1" and native["stdin_read_complete"] is True
        assert native["input_bytes"] == len(data) and native["profiles"]["boolean_encoding"] == "sdk-byte"
        assert all(native[name] is False for name in ("gamecore_loaded", "window_created", "game_accessed",
            "user_saves_accessed", "complete_save_verified", "restore_approved", "full_engine_goal_complete"))
        observations.append({"fixture": case["fixture"], "raw_sha256": case["raw_sha256"],
            "framing_candidate": case["declared_frame_candidate"], "input_bytes": len(data),
            "input_sha256": hashlib.sha256(data).hexdigest(), "native_returncode": completed.returncode,
            "native_observation": native, "stderr": completed.stderr.decode("utf-8", errors="replace")})
    g.unchanged(inputs + protected)
    assert len(guard.calls) == 2 and not guard.denied
    result = {"schema": "zerosis.retail.declared_frames_trace.v1", "status": "OBSERVED_LENGTH_PREFIXED_PUBLIC_MAP_INPUTS",
        "utc": datetime.now(timezone.utc).isoformat(), "inputs": inputs, "protected_baseline": preflight["protected_baseline"],
        "protected_count": len(protected), "metadata_revisions": preflight["intentional_metadata_revisions"],
        "executable": executable, "build_reused": True, "new_compilation": False,
        "cases": observations, "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
        "source_headers_or_parser_profiles_changed": False, "declared_frame_producer_contract_verified": False,
        "raw_inflated_or_database_saved": False, "sdk_host_hwnd_or_original_game_executed": False,
        "user_game_files_accessed": False, "complete_save_validated": False, "full_engine_goal_complete": False}
    g.write_json(RESULT, result)
    print(json.dumps({"report": g.artifact(RESULT), "cases": [{"id": row["fixture"]["id"],
        "status": row["native_observation"]["status"], "stage": row["native_observation"]["stage"],
        "plots_completed": row["native_observation"]["plots_completed"],
        "map_wire_framed": row["native_observation"]["map_wire_framed"],
        "error": row["native_observation"]["error"]} for row in observations]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
