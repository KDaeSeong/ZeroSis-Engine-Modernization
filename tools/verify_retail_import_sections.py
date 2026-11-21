"""Build one portable import-section component and inspect two pinned RAM inputs.

Importing this module performs no file access, downloads, builds or child runs.
No original, inflated, prepared-payload or embedded-database bytes are saved.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import ssl
import stat
import subprocess
import sys
import urllib.request
import zlib

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/retail_save_container/import_sections"
SOURCE = PROJECT / "Tests/retail_save_import_sections.cpp"
SOURCE_SHA = "11ba7a0c15469570d3d9ac2c28db26cd7c35c6510a5ccac44b5703f0fe13b22a"
HEADER_PINS = {
    "RetailSavePregameImport.h": "f078766aa7c86ceab301d2a420c50feff4dd489fb6a01ee4ede8238bd55e17a9",
    "RetailSaveImportSections.h": "1ce2b49401bd4a55e5a560da127dbc20442bf8a5fe2d69eb7d03426e8a652872",
    "RetailSaveBodyImport.h": "b64bbfecde88ac7970436eecf058689791fbb9c1c1fdeacfa78362cce8ca406b",
}
POST = PROJECT / "evidence/retail_save_container/body_import/publication/post_checks.json"
POST_SHA = "36ed0b9b04a17baf86db772dddeba5b3fd3d7c2b171db8524f9b8649eb352881"
GOLDEN = PROJECT / "evidence/retail_save_container/body_import/result.json"
GOLDEN_SHA = "dc957f5a7277e57a98df77b4b4ae508d8ca276e99bf4043b3dc7b48dc1a60473"
PUBLIC = PROJECT / "evidence/retail_save_container/map_trace/chunk_frames_component/public_result.json"
PUBLIC_SHA = "9219e7b264e4190127a29f7d81f6bdfb403637221e1fd0d7ef275559dc7b614d"
PINS = {
    "verify_retail_body_import": "8870d5739f97286a9d28e8fe0f595fa86afb0b146c7a3ac6aa6b4da434979f87",
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header": "9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}
NEW_SOURCE_CONTRACTS = (
    ("Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPreGame.h", 20239,
     "be6d9d3923cddf517273fb9c779ab4baac821b452c0e9394043c1407ef5ac635"),
    ("Source/Providers/Serialization/SdkEnumTypes.inc", 2214,
     "deb2192f5bbec6082e9a919a07d9e8db00e9d30ae223630304970a04aa3cfb3a"),
    ("Source/SDK_BNW_Original/CvGameCoreDLLUtil/include/CvEnums.h", 85680,
     "6781f34a6a6a9fac1cbaad3a3477afabf540669af9f860f57ad54b967c22da9b"),
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def authenticate_module(path, digest):
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Reparse helper path is forbidden")
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= 2 * 1024 * 1024, "Helper size or kind differs")
    data = path.read_bytes()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and len(data) == before.st_size and
            hashlib.sha256(data).hexdigest() == digest, "Frozen helper changed: " + path.name)


def prepare_input(g, case, expected, opener):
    fixture = g.select_fixture({"candidates": [case["fixture"]]}, case["fixture"]["id"])
    require(fixture["bytes"] == expected["raw_bytes"] and case["raw_sha256"] == expected["raw_sha256"] and
            case["inflated_bytes"] == expected["inflated_bytes"] and
            case["inflated_sha256"] == expected["inflated_sha256"], "Pinned public identity differs")
    request = urllib.request.Request(fixture["raw_url"], headers={
        "User-Agent": "ZeroSis-Portable-Import-Sections", "Accept-Encoding": "identity"})
    with opener.open(request, timeout=30) as response:
        require(response.status == 200 and response.geturl() == fixture["raw_url"], "Public response identity differs")
        length = response.headers.get("Content-Length")
        require(length is None or int(length) == fixture["bytes"], "Public content length differs")
        raw = response.read(fixture["bytes"] + 1)
    require(len(raw) == fixture["bytes"] and hashlib.sha256(raw).hexdigest() == expected["raw_sha256"],
            "Public raw size or SHA-256 differs")
    git_sha = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    require(git_sha == fixture["git_blob_sha1"], "Public Git blob SHA-1 differs")
    header = case["header"]["observation"]
    require(case["header"]["returncode"] == 0 and header["status"] == "DIAGNOSTIC_HEADER_PREFIX_OBSERVED",
            "Pinned C++ header observation did not succeed")
    frames, container = header["chunk_frames"]["frames"], header["chunk_frames"]["container_span"]
    require(len(frames) == 11 and container["offset"] == header["compressed_offset"] - 4 and
            container["bytes"] == len(raw) - container["offset"], "Pinned C++ frame container differs")
    decoder, body = zlib.decompressobj(), bytearray()
    cursor, total = container["offset"], 0
    for frame in frames:
        require(frame["header"] == {"offset": cursor, "bytes": 4}, "Frame length words are not consecutive")
        begin, size = frame["payload"]["offset"], frame["payload"]["bytes"]
        require(begin == cursor + 4 and 0 < size <= 65536 and size <= len(raw) - begin and
                int.from_bytes(raw[cursor:begin], "little") == size, "C++ payload span differs from raw length")
        remaining = expected["inflated_bytes"] + 1 - len(body)
        require(remaining > 0, "Inflated byte budget exhausted")
        body.extend(decoder.decompress(raw[begin:begin + size], remaining))
        require(len(body) <= expected["inflated_bytes"] and not decoder.unconsumed_tail and not decoder.unused_data,
                "Frame decompression exceeded its strict bound")
        cursor, total = begin + size, total + size
    require(cursor == len(raw) and total == header["chunk_frames"]["total_payload_bytes"] and decoder.eof is False,
            "Frame coverage or retained nonfinal codec observation differs")
    require(len(body) == expected["inflated_bytes"] and hashlib.sha256(body).hexdigest() == expected["inflated_sha256"],
            "Inflated size or SHA-256 differs")
    return raw, bytes(body), {"fixture": fixture, "raw_bytes": len(raw), "raw_sha256": expected["raw_sha256"],
        "git_blob_sha1": git_sha, "body_bytes": len(body), "body_sha256": expected["inflated_sha256"],
        "authenticated_cpp_frame_count": 11, "compressed_payload_bytes": total, "zlib_eof": False,
        "decoder_reset_flush_or_retry_used": False, "raw_inflated_or_database_saved": False}


def native_json(payload, base):
    value = json.loads(payload.decode("utf-8-sig"))
    require(isinstance(value, dict) and value.get("schema") == "zerosis.retail.import_sections_test.v1" and
            value.get("status") == "PASS_RETAIL_IMPORT_SECTIONS_COMPONENT", "Native schema or status differs")

    def visit(item, depth=0):
        require(depth <= 16, "Native JSON nesting exceeded its bound")
        if isinstance(item, str):
            require(len(item) <= 4096, "Native JSON contains a payload-sized string")
        elif isinstance(item, list):
            require(len(item) <= 256, "Native JSON contains a payload-sized array")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, dict):
            require(len(item) <= 128, "Native JSON object exceeded its bound")
            for child in item.values():
                visit(child, depth + 1)
    visit(value)
    require(all(value.get(name) is False for name in (*base.FALSE_FLAGS, "native_restore_approved")),
            "Native component exceeded its execution or approval scope")
    require(all(value.get(name) is True for name in
                ("input_bytes_unchanged", "input_files_unchanged", "all_failure_outputs_unchanged")) and
            type(value.get("checks")) is int and value["checks"] > 0, "Native preservation checks differ")
    return value


def run_once(g, base, command, data, root, environment, prefix):
    timed_out = False
    try:
        run = subprocess.run(command, cwd=root, env=environment, input=data, capture_output=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        stdout, stderr, code = run.stdout, run.stderr, run.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code = error.stdout or b"", error.stderr or b"", None
        timed_out = True
    stdout_path, stderr_path, process_path = [STAGE / (prefix + suffix)
        for suffix in (".stdout.log", ".stderr.log", ".process.json")]
    g.write_text(stdout_path, stdout[:128 * 1024].decode("utf-8-sig", errors="replace"), 384 * 1024)
    g.write_text(stderr_path, stderr[:16 * 1024].decode("utf-8", errors="replace"), 48 * 1024)
    g.write_json(process_path, {"command": list(command), "returncode": code, "timed_out": timed_out,
        "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
        "stdout_truncated": len(stdout) > 128 * 1024, "stderr_truncated": len(stderr) > 16 * 1024})
    require(not timed_out and code == 0 and len(stdout) <= 128 * 1024 and len(stderr) <= 16 * 1024,
            "Inspect the preserved native child logs")
    return native_json(stdout, base), {name: g.artifact(path) for name, path in
        (("stdout", stdout_path), ("stderr", stderr_path), ("process", process_path))}


def expected_sections(wire, pregame_bytes):
    def row(kind, index, storage, offset, count):
        return {"kind": kind, "index": index, "storage": storage, "offset": offset, "bytes": count}
    game_end, map_end = wire["game_map"]["game_end_offset"], wire["game_map"]["map_end_offset"]
    result = [row(2, 0, "pregame", 0, pregame_bytes), row(3, 0, "body", 0, game_end),
              row(4, 0, "body", game_end, map_end - game_end),
              row(5, 0, "body", wire["supporting"]["start"], wire["supporting"]["bytes"])]
    result += [row(6, team["slot"], "body", team["start"], team["end"] - team["start"]) for team in wire["teams"]]
    result += [row(7, player["slot"], "body", player["start"], player["end"] - player["start"]) for player in wire["players"]]
    require(len(result) == 132, "Golden wire does not contain 132 non-bundle sections")
    return result


def main():
    require(os.name == "nt" and len(sys.argv) == 1 and not sys.flags.optimize, "Require Windows and no runner arguments")
    require(len(SOURCE_SHA) == 64 and all(len(value) == 64 for value in HEADER_PINS.values()),
            "Component sources have not been frozen")
    sys.dont_write_bytecode = True
    for name, digest in PINS.items():
        authenticate_module(PROJECT / "tools" / (name + ".py"), digest)
    modules = {name: importlib.import_module(name) for name in PINS}
    require(all(Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py")
                for name, module in modules.items()), "Imported helper path differs")
    base, g, h, n = [modules[name] for name in
        ("verify_retail_body_import", "probe_public_retail_save", "verify_retail_save_header", "native_build")]
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"warm".decode(encoding)
    post_pin, golden_pin, public_pin = g.artifact(POST), g.artifact(GOLDEN), g.artifact(PUBLIC)
    require(post_pin["sha256"] == POST_SHA and golden_pin["sha256"] == GOLDEN_SHA and
            public_pin["sha256"] == PUBLIC_SHA, "Frozen publication or golden SHA differs")
    post, golden, public = g.read_json(POST), g.read_json(GOLDEN), g.read_json(PUBLIC)
    require(post["status"] == "PASS_BODY_PREPARATION_PROTECTED_INPUTS_AND_BOUNDED_RETIREMENT" and
            post["runtime_hold_unchanged"] is True and post["default_provider_unchanged"] is True and
            post["actual_import_entrypoint_implemented"] is False and post["sdk_restore_verified"] is False,
            "Previous publication scope differs")
    frozen = base.pinned_rows(g, post["protected_files"], 45) + base.pinned_rows(g, post["source_contract_inputs"], 14)
    frozen += base.pinned_rows(g, post["source_and_proof_files"], 26)
    new_contracts = []
    for relative, count, digest in NEW_SOURCE_CONTRACTS:
        row = g.artifact(PROJECT / relative)
        require(row["bytes"] == count and row["sha256"] == digest, "New source contract differs: " + relative)
        new_contracts.append(row)
    source_pin = g.artifact(SOURCE)
    require(source_pin["sha256"] == SOURCE_SHA, "Frozen test source SHA differs")
    for name, digest in HEADER_PINS.items():
        require(g.artifact(PROJECT / "Source/Host" / name)["sha256"] == digest, "Frozen import header SHA differs: " + name)
    headers = g.host_headers(SOURCE, PROJECT)
    require(all(PROJECT / "Source/Host" / name in headers for name in HEADER_PINS),
            "A production import helper is absent from the portable include closure")
    inputs = base.unique_rows(g, frozen + new_contracts + [post_pin, golden_pin, public_pin, source_pin,
        g.artifact(Path(__file__).absolute())] + [g.artifact(path) for path in headers] +
        [g.artifact(PROJECT / "tools" / (name + ".py")) for name in PINS])
    compiler = g.artifact(h.COMPILER)
    require(compiler["sha256"] == h.COMPILER_SHA, "Reviewed compiler SHA differs")
    fingerprint = g.identity({"schema": "zerosis.retail.import_sections.identity.v1", "inputs": inputs, "compiler": compiler})
    parent, stage = g.ordinary(PROJECT / "Build/RetailImportSections"), g.ordinary(STAGE)
    parent.mkdir(parents=True, exist_ok=True); stage.mkdir(parents=True, exist_ok=True)
    root, evidence = g.ordinary(parent / fingerprint), g.ordinary(stage / ("compile_" + fingerprint))
    result_path, started_path, failed_path = [stage / name for name in ("result.json", "started.json", "failed_attempt.json")]
    require(not any(path.exists() for path in (root, evidence, result_path, started_path, failed_path)),
            "Inspect the retained previous import-section attempt before retrying")
    require([case["fixture"]["id"] for case in public["cases"]] == list(base.EXPECTED) and
            [case["fixture"]["id"] for case in golden["cases"]] == list(base.EXPECTED) and
            golden["status"] == "PASS_PORTABLE_RETAIL_BODY_IMPORT_COMPONENT", "Pinned public fixture set differs")
    references = {case["fixture"]["id"]: case["observation"]["public"]["wire"] for case in golden["cases"]}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), g.NoRedirect())
    prepared = [prepare_input(g, case, base.EXPECTED[case["fixture"]["id"]], opener) for case in public["cases"]]
    g.unchanged(inputs + [compiler])
    compile_command = (str(h.COMPILER), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
        "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    env_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    executable = str(root / "RetailPublicProbe.exe")
    commands = [(executable, "--self-test")]
    commands += [(executable, "--public", str(len(raw)), str(len(body)), "5", "4", "6",
        str(base.EXPECTED[meta["fixture"]["id"]]["budget"])) for raw, body, meta in prepared]
    writable = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
        "dependencies.json", "read_build_environment.cmd")]
    writable += [evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    writable += [result_path, started_path, failed_path]
    for prefix in ("self", "public_0", "public_1"):
        writable += [stage / (prefix + suffix) for suffix in (".stdout.log", ".stderr.log", ".process.json")]
    require(not any(path.exists() for path in writable), "An unreviewed previous output exists")
    guard = g.OfflineGuard(commands=[env_command, compile_command, *commands], directory=root,
        readable=[Path(row["path"]) for row in inputs + [compiler]], writable=writable, directories=[root, evidence])
    sys.addaudithook(guard.audit)
    try:
        g.write_json(started_path, {"schema": "zerosis.retail.import_sections.started.v1", "fingerprint": fingerprint,
            "inputs": inputs, "public_inputs": [meta for _, _, meta in prepared],
            "commands": [env_command, compile_command, *commands], "sdk_or_host_or_game_executed": False})
        build, environment = g.ensure_build(project=PROJECT, root=root, evidence=evidence, source=SOURCE,
            headers=headers, inputs=inputs, compiler=compiler, compiler_path=h.COMPILER, vs=h.VS,
            command=compile_command, environment_for=n.environment_for, pe_imports=h.pe_imports,
            guard=guard, fingerprint=fingerprint)
        self_test, self_logs = run_once(g, base, commands[0], b"", root, environment, "self")
        require(self_test["mode"] == "self-test" and all(type(self_test.get(name)) is int and self_test[name] > 0
            for name in ("synthetic_pregame_cases", "truncations", "directed_corruptions", "atomic_failure_cases",
                         "elapsed_cases", "options_cases")), "Focused component coverage differs")
        cases = []
        for index, (raw, body, meta) in enumerate(prepared):
            native, logs = run_once(g, base, commands[index + 1], raw + body, root, environment, "public_" + str(index))
            observed, fixture_id = native["public"], meta["fixture"]["id"]
            expected, reference = base.EXPECTED[fixture_id], references[fixture_id]
            require(native["mode"] == "public" and observed["raw_bytes"] == len(raw) and observed["body_bytes"] == len(body) and
                    [observed[name] for name in ("awards", "grand", "projects")] == [5, 4, 6] and
                    observed["maximum_total_records"] == expected["budget"], "Public argument echo differs")
            require(all(name in observed["wire"] and base.same_structure(observed["wire"][name], reference[name])
                        for name in base.WIRE_GROUPS), "Body structure differs from the canonical body-import golden")
            require(base.same_structure(observed["synthetic_pregame_public_body_control"], {
                "verified": True, "section_count": 132, "actual_body_reused": True, "raw_bytes_unchanged": True,
                "intentionally_unpaired": True, "compressed_body_association_verified": False,
                "native_restore_approved": False, "restore_approved": False}),
                "The separate synthetic-Pregame control did not verify its bounded section path")
            pregame = observed["pregame"]
            offset, count = pregame["raw_offset"], pregame["bytes"]
            archive = pregame["archive_raw_offset"]
            header = public["cases"][index]["header"]["observation"]
            require(type(offset) is int and type(count) is int and offset >= header["metadata"]["metadata_prefix_bytes"] and
                    count > 0 and offset <= len(raw) and count <= len(raw) - offset and
                    offset + count == header["pregame"]["compression_header_offset"] and
                    pregame["raw_end"] == offset + count and type(archive) is int and offset <= archive < offset + count and
                    pregame["scalar_boolean_count"] == 17 and pregame["boolean_array_count"] == 9 and
                    pregame["canonical_booleans_checked"] is True and
                    type(pregame["boolean_bytes_checked"]) is int and 17 <= pregame["boolean_bytes_checked"] <= count and
                    type(pregame["network_id_count"]) is int and 0 <= pregame["network_id_count"] <= count // 4 and
                    type(pregame["maximum_option_name_bytes"]) is int and 0 <= pregame["maximum_option_name_bytes"] <= count and
                    type(pregame["option_name_has_embedded_null"]) is bool,
                    "First observed Pregame span or typed boolean-site coverage differs")
            require(type(observed["header_turn"]) is int and observed["header_turn"] == header["metadata"]["current_turn"] and
                    type(observed["turn"]) is int and -2147483648 <= observed["turn"] <= 2147483647 and
                    type(observed["elapsed"]) is int and 0 <= observed["elapsed"] <= 2147483647 and
                    type(observed["active_player"]) is int and -2147483648 <= observed["active_player"] <= 2147483647 and
                    type(observed["game_type"]) is int and -128 <= observed["game_type"] <= 127 and
                    observed["retail_header_turn_matches"] is (observed["header_turn"] == observed["turn"]),
                    "Typed save identity is outside its source-defined bounds")
            eligible = (0 <= observed["active_player"] < 64 and observed["turn"] >= 0 and observed["game_type"] == 0 and
                        pregame["network_id_count"] == 64 and
                        pregame["maximum_option_name_bytes"] <= 63 and not pregame["option_name_has_embedded_null"])
            require(type(observed["eligible"]) is bool and type(observed["accepted"]) is bool and
                    observed["eligible"] is eligible and observed["accepted"] is eligible and
                    observed["rejection_atomicity_verified"] is True and
                    type(observed["section_count"]) is int and type(observed["total_payload_bytes"]) is int,
                    "Candidate eligibility or failure atomicity differs from the explicit source policy")
            if eligible:
                require(observed["rejection"] is None and observed["section_count"] == 132 and
                        base.same_structure(observed["sections"], expected_sections(reference, count)) and
                        observed["total_payload_bytes"] == count + len(body) == sum(row["bytes"] for row in observed["sections"]),
                        "Accepted section ownership, ordering, spans or exact byte coverage differs")
            else:
                require(base.same_structure(observed["rejection"], {"domain": "pregame_import", "code": 1,
                            "raw_offset": archive,
                            "message": "Pregame does not meet offline native candidate metadata requirements"}) and
                        observed["section_count"] == 0 and observed["sections"] == [] and observed["total_payload_bytes"] == 0,
                        "Unsupported Pregame layout was not rejected atomically by its typed source policy")
            require(hashlib.sha256(raw).hexdigest() == meta["raw_sha256"] and
                    hashlib.sha256(body).hexdigest() == meta["body_sha256"], "Original RAM input changed")
            cases.append({**meta, "observation": native, **logs, "structural_reference": golden_pin,
                "structural_comparison": {name: True for name in base.WIRE_GROUPS},
                "pregame_span_first_observation": True, "previous_reports_contained_pregame_start": False,
                "pregame_span_end_matches_pinned_archive_end": True,
                "native_section_candidate_accepted": eligible,
                "native_import_gate": "candidate_eligible_restore_unverified" if eligible else "unsupported_pregame_layout"})
        g.unchanged(inputs + [compiler] + list(build["artifacts"].values()))
        require(not guard.denied and guard.calls == [list(command) for command in (env_command, compile_command, *commands)],
                "Offline guard observed missing, repeated or forbidden operations")
        report = {"schema": "zerosis.retail.import_sections.component.v1", "status": "PASS_PORTABLE_RETAIL_IMPORT_SECTIONS_COMPONENT",
            "utc": datetime.now(timezone.utc).isoformat(), "inputs": inputs, "previous_publication": post_pin,
            "frozen_previous_counts": {"protected": 45, "source_contracts": 14, "source_and_proof": 26},
            "new_source_contract_count": 3, "new_source_contracts": new_contracts,
            "build_report": g.artifact(evidence / "build_result.json"), "self_test": self_test,
            "self_logs": self_logs, "cases": cases, "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            "retired_intermediates": build["retired_intermediates"], "retired_logical_bytes": build["retired_logical_bytes"],
            "accepted_public_candidates": sum(case["native_section_candidate_accepted"] for case in cases),
            "rejected_public_candidates": sum(not case["native_section_candidate_accepted"] for case in cases),
            "synthetic_pregame_public_body_control_count": len(cases),
            "synthetic_controls_count_as_public_acceptance": False,
            "bundle_identity_verified": False, "native_archive_envelope_created": False,
            "actual_import_entrypoint_implemented": False, "menu_entrypoint_implemented": False,
            "sdk_restore_verified": False, "native_restore_approved": False,
            "raw_inflated_or_database_saved": False, "sdk_or_host_or_hwnd_or_original_game_executed": False,
            "user_game_files_accessed": False, "producer_contract_verified": False,
            "ruleset_compatibility_verified": False, "complete_save_verified": False,
            "restore_approved": False, "full_engine_goal_complete": False, "whole_project_storage_rescanned": False}
        g.write_json(result_path, report)
        print(json.dumps({"status": report["status"], "report": g.artifact(result_path),
            "retired_logical_bytes": build["retired_logical_bytes"]}))
        return 0
    except BaseException as error:
        if not failed_path.exists():
            g.write_json(failed_path, {"status": "FAILED_PORTABLE_IMPORT_SECTIONS_COMPONENT", "error": type(error).__name__ + ": " + str(error),
                "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
                "raw_inflated_or_database_saved": False, "sdk_or_host_or_game_executed": False,
                "actual_import_entrypoint_implemented": False, "native_archive_envelope_created": False,
                "sdk_restore_verified": False, "native_restore_approved": False,
                "restore_approved": False, "full_engine_goal_complete": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
