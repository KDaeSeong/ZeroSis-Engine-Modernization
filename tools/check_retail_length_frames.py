"""Build one no-SDK probe; feed its declared spans from two pinned public saves.

Raw and inflated bytes stay in RAM. Framing and wire diagnostics grant no
producer finish, retail outer-order, semantic or game restore approval.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.request
import zlib

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/retail_save_container/map_trace/chunk_frames_component"
PINS = {
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header": "9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}


def main():
    assert len(sys.argv) == 1 and os.name == "nt" and not sys.flags.optimize
    for name, digest in PINS.items():
        path = PROJECT / "tools" / (name + ".py")
        for part in (path, *path.parents):
            assert not part.lstat().st_file_attributes & 0x400
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    modules = {name: importlib.import_module(name) for name in PINS}
    for name, module in modules.items():
        assert Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py")
    g, h, n = [modules[name] for name in ("probe_public_retail_save", "verify_retail_save_header", "native_build")]
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"warm".decode(encoding)
    result_path, start_path = STAGE / "public_result.json", STAGE / "public_started.json"
    assert not result_path.exists() and not start_path.exists(), "Inspect the exact prior attempt"
    reference = PROJECT / "evidence/retail_save_container/map_trace/input_chunk_comparison.json"
    reference_pin = g.artifact(reference)
    assert reference_pin["sha256"] == "04972c76cb6818e21e178363be4bc7ff7da74768f0c62b6d69f5ff3f8504b390"
    prior = g.read_json(reference)
    preflight_path = reference.parent / "input_chunk_preflight.json"
    preflight_pin = g.artifact(preflight_path)
    assert preflight_pin["sha256"] == "28b185224fe8cc2ca555147c3583038d485a5bc6c15d804512de67e93e58b84a"
    preflight = g.read_json(preflight_path)

    def checked(row):
        current = g.artifact(row["path"])
        for field in ("bytes", "sha256", "file_identity", "mtime_ns"):
            if field in row:
                assert row[field] == current[field], "Changed pinned input: " + row["path"]
        return current

    baseline_pin = checked(preflight["protected_baseline"])
    baseline = g.read_json(Path(baseline_pin["path"]))
    revisions = {row["path"]: row for row in preflight["intentional_metadata_revisions"].values()}
    protected = [checked(revisions.get(row["path"], row)) for row in baseline["protected"]]
    source = PROJECT / "Tests/retail_public_probe.cpp"
    source_pin = g.artifact(source)
    assert source_pin["sha256"] == "6d4c9a22434e6373b51b6615f5c32d4862729d394ff3bec47491d08df66a698d"
    headers = g.host_headers(source, PROJECT)
    assert hashlib.sha256((PROJECT / "Source/Host/RetailSaveChunkFrames.h").read_bytes()).hexdigest() == \
        "b355fc3b732825441a1464c36831eafe3e57d99c3ee86079c784b4969e71fea7"
    inputs = [g.artifact(path) for path in (source, *headers, Path(__file__).absolute(),
        *(PROJECT / "tools" / (name + ".py") for name in PINS))]
    inputs += [reference_pin, preflight_pin, baseline_pin]
    compiler = g.artifact(h.COMPILER)
    assert compiler["sha256"] == h.COMPILER_SHA
    fingerprint = g.identity({"schema": "zerosis.retail.length_frames.public.identity.v1", "inputs": inputs,
        "compiler": compiler})
    parent = g.ordinary(PROJECT / "Build/RetailPublicProbe")
    parent.mkdir(exist_ok=True); STAGE.mkdir(parents=True, exist_ok=True)
    root = g.ordinary(parent / fingerprint)
    evidence = g.ordinary(STAGE / ("compile_public_" + fingerprint))
    assert not root.exists() and not evidence.exists()
    assert len(prior["cases"]) == 2
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    buffers = []
    for case in prior["cases"]:
        fixture = case["fixture"]
        url = fixture["raw_url"]
        assert url.startswith("https://raw.githubusercontent.com/")
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "ZeroSis-public-framing-audit"}), timeout=20) as response:
            assert response.geturl() == url
            raw = response.read(fixture["bytes"] + 1)
        assert len(raw) == fixture["bytes"] and hashlib.sha256(raw).hexdigest() == case["raw_sha256"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest() == fixture["git_blob_sha1"]
        buffers.append((case, raw))
    env_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    compile_command = (str(h.COMPILER), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64", "/INCREMENTAL:NO",
        "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    commands = []
    for case, raw in buffers:
        common = ("--awards", "5", "--grand", "4", "--projects", "6", "--boolean-encoding", "sdk-byte", "--max-input")
        size = case["declared_frame_candidate"]["candidate_zlib"]["output_bytes"]
        commands += [(str(root / "RetailPublicProbe.exe"), "--header", "--framing", "u32-length-to-end", *common, str(len(raw))),
                     (str(root / "RetailPublicProbe.exe"), "--inflated", *common, str(size))]
    assert len(set(commands)) == 4
    outputs = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
        "dependencies.json", "read_build_environment.cmd")]
    outputs += [evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    outputs += [result_path, start_path, STAGE / "public_failed_attempt.json"]
    for index in range(4):
        outputs += [STAGE / ("public_" + str(index) + suffix) for suffix in (".stdout.log", ".stderr.log", ".process.json")]
    guard = g.OfflineGuard(commands=[env_command, compile_command, *commands], directory=root,
        readable=[Path(row["path"]) for row in inputs + protected + [compiler]], writable=outputs, directories=[root, evidence])
    sys.addaudithook(guard.audit)

    def native(index, data, environment):
        run = subprocess.run(commands[index], cwd=root, env=environment, input=data, capture_output=True, timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        assert len(run.stdout) <= 64 * 1024 and len(run.stderr) <= 16 * 1024
        stdout = STAGE / ("public_" + str(index) + ".stdout.log")
        stderr = STAGE / ("public_" + str(index) + ".stderr.log")
        process = STAGE / ("public_" + str(index) + ".process.json")
        g.write_text(stdout, run.stdout.decode("utf-8-sig", errors="replace"), 64 * 1024)
        g.write_text(stderr, run.stderr.decode("utf-8", errors="replace"), 32 * 1024)
        g.write_json(process, {"returncode": run.returncode, "stdout_bytes": len(run.stdout), "stderr_bytes": len(run.stderr)})
        assert run.returncode in (0, 1)
        observation = g.small_native_json(run.stdout)
        assert observation["stdin_read_complete"] and observation["input_bytes"] == len(data)
        assert observation["profiles"]["boolean_encoding"] == "sdk-byte" and observation["profiles"]["boolean_encoding_explicit"]
        assert observation["profiles"]["widths_explicit"]
        assert [observation["profiles"][key] for key in ("awards", "grand", "projects")] == [5, 4, 6]
        return {"observation": observation, "returncode": run.returncode, "stdout": g.artifact(stdout),
            "stderr": g.artifact(stderr), "process": g.artifact(process)}

    try:
        g.write_json(start_path, {"fingerprint": fingerprint, "inputs": inputs, "native_commands": commands,
            "raw_bytes_retained": False, "sdk_or_game_executed": False})
        build, environment = g.ensure_build(project=PROJECT, root=root, evidence=evidence, source=source, headers=headers,
            inputs=inputs, compiler=compiler, compiler_path=h.COMPILER, vs=h.VS, command=compile_command,
            environment_for=n.environment_for, pe_imports=h.pe_imports, guard=guard, fingerprint=fingerprint)
        cases = []
        for case_index, (case, raw) in enumerate(buffers):
            header = native(case_index * 2, raw, environment)
            observed = header["observation"]
            assert observed["mode"] == "header" and header["returncode"] == 0 and observed["status"] == "DIAGNOSTIC_HEADER_PREFIX_OBSERVED"
            frames = observed["chunk_frames"]
            candidate = case["declared_frame_candidate"]
            assert frames["container_span"] == {"offset": candidate["start"], "bytes": len(raw) - candidate["start"]}
            assert len(frames["frames"]) == 11 == len(candidate["frames"])
            decoder, inflated = zlib.decompressobj(), bytearray()
            position, total = candidate["start"], 0
            for actual, expected in zip(frames["frames"], candidate["frames"]):
                assert actual["header"] == {"offset": position, "bytes": 4}
                begin, size = actual["payload"]["offset"], actual["payload"]["bytes"]
                assert begin == position + 4 == expected["payload_offset"] and size == expected["bytes"]
                assert int.from_bytes(raw[position:position + 4], "little") == size and 0 < size <= 65536
                assert size <= len(raw) - begin
                payload = raw[begin:begin + size]
                assert hashlib.sha256(payload).hexdigest() == expected["payload_sha256"]
                remaining = 64 * 1024 * 1024 - len(inflated)
                assert remaining > 0
                inflated.extend(decoder.decompress(payload, remaining))
                assert not decoder.unconsumed_tail and not decoder.unused_data
                position, total = begin + size, total + size
            assert position == len(raw) and total == frames["total_payload_bytes"]
            expected = candidate["candidate_zlib"]
            digest = hashlib.sha256(inflated).hexdigest()
            assert len(inflated) == expected["output_bytes"] and digest == expected["output_sha256"]
            assert decoder.eof == expected["eof"] is False
            wire = native(case_index * 2 + 1, bytes(inflated), environment)
            assert wire["observation"]["mode"] == "inflated"
            assert wire["observation"]["retail_outer_sequence_verified"] is False
            cases.append({"fixture": case["fixture"], "raw_bytes": len(raw), "raw_sha256": case["raw_sha256"],
                "header": header, "inflated_bytes": len(inflated), "inflated_sha256": digest, "zlib_eof": decoder.eof,
                "zlib_reset_or_flush_used": False, "wire": wire})
        g.unchanged(inputs + protected + [compiler] + list(build["artifacts"].values()))
        assert len(guard.calls) == 6 and not guard.denied
        report = {"schema": "zerosis.retail.length_frames.public.v1", "status": "OBSERVED_CPP_FRAMED_PUBLIC_SAVE_DIAGNOSTICS",
            "utc": datetime.now(timezone.utc).isoformat(), "inputs": inputs, "protected_count": len(protected),
            "build_report": g.artifact(evidence / "build_result.json"), "cases": cases,
            "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            "retired_logical_bytes": build["retired_logical_bytes"], "producer_contract_verified": False,
            "raw_inflated_or_database_saved": False, "sdk_host_hwnd_or_original_game_executed": False,
            "user_game_files_accessed": False, "complete_save_verified": False, "restore_approved": False,
            "full_engine_goal_complete": False}
        g.write_json(result_path, report)
        print(json.dumps({"report": g.artifact(result_path), "cases": [{"id": row["fixture"]["id"],
            "status": row["wire"]["observation"]["status"], "phase": row["wire"]["observation"]["phase"],
            "teams": row["wire"]["observation"]["teams_completed"], "players": row["wire"]["observation"]["players_completed"],
            "error": row["wire"]["observation"]["error"]} for row in cases]}))
        return 0
    except BaseException as error:
        g.write_json(STAGE / "public_failed_attempt.json", {"error": type(error).__name__ + ": " + str(error),
            "child_commands": guard.calls, "forbidden_access_attempts": guard.denied, "sdk_or_game_executed": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
