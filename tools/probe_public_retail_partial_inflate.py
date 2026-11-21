"""Observe the emitted prefix before a public fixture's first zlib failure.

The verified generic probe remains unchanged. This import-safe wrapper neither
compiles nor stores raw, inflated or embedded-database payloads on disk.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import zlib


GENERIC_SHA256 = "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962"
BUILD_FINGERPRINT = "697ab5173f5263684de7"
BUILD_REPORT_SHA256 = "fcc889b4b71ffc9451eaa7dd3c33bdd376c040b4c6d0c12a842d548c04537ec7"
ORIGINAL_PROBE_ID = "8fe49418cee5e69aefac"
ORIGINAL_REPORT_SHA256 = "d90dce03c773034cc44afd311b0ae6a1b84b3afd6d3be48dc0dc2677e86966d7"
CHUNK_BYTES = 64 * 1024
MAX_CHUNKS = 128
MAX_RAW_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
WIDTHS = {"awards": 5, "grand": 4, "projects": 6}
_MAIN_USED = False


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def load_generic(project: Path):
    path = project / "tools/probe_public_retail_save.py"
    for part in (path, *path.parents):
        if part.exists():
            info = part.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                    "Frozen generic helper path is not ordinary")
    require(path.stat().st_size <= 128 * 1024, "Frozen generic helper is oversized")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == GENERIC_SHA256, "Frozen generic helper changed")
    import probe_public_retail_save as generic
    require(Path(generic.__file__).absolute() == path.absolute() and not generic._MAIN_USED,
            "Unexpected generic helper module identity or prior entry-point execution")
    return generic


def tail_observation(decoder) -> dict:
    return {"decoder_eof": decoder.eof,
            "unconsumed_tail_bytes": len(decoder.unconsumed_tail),
            "unconsumed_tail_sha256": hashlib.sha256(decoder.unconsumed_tail).hexdigest(),
            "unused_data_bytes": len(decoder.unused_data),
            "unused_data_sha256": hashlib.sha256(decoder.unused_data).hexdigest()}


def emitted_prefix(raw: bytes, offset: int) -> tuple[bytes, dict]:
    """One decoder, consecutive fixed input chunks, no flush or replay calls.

    An exception can occur after the codec internally emitted bytes that Python
    never returned. Such bytes are unavailable and are not part of this prefix.
    """
    require(type(offset) is int and 0 <= offset <= len(raw) <= MAX_RAW_BYTES, "Invalid bounded compressed span")
    compressed = memoryview(raw)[offset:]
    require((len(compressed) + CHUNK_BYTES - 1) // CHUNK_BYTES <= MAX_CHUNKS, "Compressed input exceeds 128 chunks")
    decoder = zlib.decompressobj()
    prefix = bytearray()
    rows = []
    fully_consumed = 0
    submitted = 0
    stop_reason = "compressed_input_exhausted"
    first_error = None
    for index, start in enumerate(range(0, len(compressed), CHUNK_BYTES)):
        if len(prefix) == MAX_OUTPUT_BYTES:
            stop_reason = "output_byte_limit"
            break
        end = min(start + CHUNK_BYTES, len(compressed))
        chunk = compressed[start:end]
        submitted = end
        row = {"index": index, "compressed_start": start, "compressed_end": end,
               "raw_start": offset + start, "raw_end": offset + end, "input_bytes_submitted": len(chunk),
               "input_sha256": hashlib.sha256(chunk).hexdigest(), "output_bytes_before_call": len(prefix)}
        try:
            returned = decoder.decompress(chunk, MAX_OUTPUT_BYTES - len(prefix))
        except zlib.error as error:
            # Stop immediately: no output from this failed call is available.
            row.update({"returned_successfully": False, "returned_output_bytes": None,
                        "returned_output_sha256": None, "retained_output_from_call": 0,
                        "consumed_entire_submitted_chunk": None, "consumed_input_bytes": None,
                        "output_bytes_after_call_retained": len(prefix), **tail_observation(decoder)})
            rows.append(row)
            first_error = {"chunk_index": index, "compressed_start": start, "compressed_end": end,
                           "raw_start": offset + start, "raw_end": offset + end, "message": str(error),
                           "exact_failing_byte_known": False, "unreturned_codec_output_retained": False}
            stop_reason = "first_zlib_error"
            break
        prefix.extend(returned)
        require(len(prefix) <= MAX_OUTPUT_BYTES, "Returned prefix exceeded its fixed byte budget")
        tails = tail_observation(decoder)
        consumed_all = not decoder.unconsumed_tail and not decoder.unused_data
        if consumed_all:
            fully_consumed = end
        row.update({"returned_successfully": True, "returned_output_bytes": len(returned),
                    "returned_output_sha256": hashlib.sha256(returned).hexdigest(),
                    "retained_output_from_call": len(returned), "consumed_entire_submitted_chunk": consumed_all,
                    "consumed_input_bytes": len(chunk) if consumed_all else None,
                    "output_bytes_after_call_retained": len(prefix), **tails})
        rows.append(row)
        if decoder.eof:
            stop_reason = "decoder_eof_observed"
            break
        if decoder.unconsumed_tail:
            # This occurs when max_length capped output. Retrying the same input
            # would violate the one-pass diagnostic, so no such retry is made.
            stop_reason = "output_byte_limit"
            break
    if len(prefix) == MAX_OUTPUT_BYTES and not decoder.eof and stop_reason == "compressed_input_exhausted":
        stop_reason = "output_byte_limit"
    require(len(rows) <= MAX_CHUNKS, "Decoder call count exceeded its fixed bound")
    result = bytes(prefix)
    return result, {"schema": "zerosis.public_retail_partial_inflate.chunks.v1",
        "status": "INCOMPLETE_EMITTED_PREFIX_OBSERVED", "compressed_offset": offset,
        "compressed_bytes": len(compressed), "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
        "input_chunk_bytes": CHUNK_BYTES, "maximum_chunks": MAX_CHUNKS, "calls": len(rows),
        "compressed_bytes_submitted": submitted, "fully_consumed_successful_chunks_bytes": fully_consumed,
        "compressed_bytes_never_submitted": len(compressed) - submitted,
        "stop_reason": stop_reason, "first_failing_chunk": first_error,
        "retained_prefix_bytes": len(result), "retained_prefix_sha256": hashlib.sha256(result).hexdigest(),
        "maximum_output_bytes": MAX_OUTPUT_BYTES, "chunks": rows, **tail_observation(decoder),
        "decoder_instances": 1, "decoder_resets": 0, "chunk_retries": 0, "flush_calls": 0,
        "signature_search_used": False, "skipped_input_bytes": 0, "fabricated_trailer_bytes": 0,
        "prefix_explicitly_incomplete": True, "complete_save_validated": False,
        "raw_or_inflated_or_database_saved": False, "restore_approved": False}


def never_compile(*args, **kwargs):
    raise RuntimeError("This partial diagnostic cannot initialize or compile a native build")


def verify_original(generic, project: Path, inputs: list[dict], compiler: dict,
                    manifest_pin: dict, candidate: dict) -> tuple[dict, dict, list[dict]]:
    directory = project / "evidence/retail_save_container/players/probes" / ("jpl_before_" + ORIGINAL_PROBE_ID)
    path = directory / "probe_result.json"
    pin = generic.artifact(path)
    require(pin["sha256"] == ORIGINAL_REPORT_SHA256, "Frozen original probe report changed")
    original = generic.read_json(path)
    require(original.get("status") == "OBSERVED_PUBLIC_RETAIL_SAVE_PROBE" and
            original.get("build_fingerprint") == BUILD_FINGERPRINT and original.get("profiles") == WIDTHS and
            original.get("fixture") == candidate and original.get("candidate_manifest") == manifest_pin and
            original.get("inputs") == inputs and original.get("compiler") == compiler and
            original.get("guard_passed") is True and original.get("forbidden_access_attempts") == [] and
            all(original.get(name) is False for name in generic.FLAGS_FALSE), "Frozen original probe identity differs")
    rows = original.get("native_results")
    require(isinstance(rows, list) and len(rows) == 1 and rows[0].get("mode") == "header" and rows[0].get("returncode") == 0,
            "Original report is not the verified header-only observation")
    header = rows[0]
    expected_logs = {"json_log": directory / "header.json", "stderr_log": directory / "header.stderr.log"}
    for name, expected in expected_logs.items():
        require(generic.key(header[name]["path"]) == generic.key(expected), "Original header log path differs")
    require(generic.key(original["probe_started"]["path"]) == generic.key(directory / "probe_started.json"),
            "Original probe-start path differs")
    pins = [pin, original["probe_started"], *(header[name] for name in expected_logs)]
    generic.unchanged(pins)
    require(generic.read_json(directory / "header.json") == header["observation"], "Frozen header JSON content differs")
    observation = generic.small_native_json(json.dumps(header["observation"]).encode("utf-8"))
    require(observation.get("mode") == "header" and observation.get("stdin_read_complete") is True and
            observation.get("header_observed") is True and observation.get("pregame_observed") is True and
            observation.get("error", {}).get("domain") == "none" and
            observation.get("compressed_offset") == 11588 and
            all(observation.get("profiles", {}).get(name) == value for name, value in WIDTHS.items()) and
            observation.get("profiles", {}).get("widths_explicit") is True,
            "Frozen header observation is not the exact declared-width source of the offset")
    require(original.get("inflation", {}).get("status") == "ZLIB_DIAGNOSTIC_REJECTED",
            "Original one-shot inflation was not the expected diagnostic rejection")
    return original, pin, pins


def probe(argv: list[str] | None = None) -> dict:
    global _MAIN_USED
    require(not _MAIN_USED, "Partial diagnostic entry point is one-use per interpreter")
    _MAIN_USED = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--awards", type=int, required=True)
    parser.add_argument("--grand", type=int, required=True)
    parser.add_argument("--projects", type=int, required=True)
    args = parser.parse_args(argv)
    require(os.name == "nt" and not sys.flags.optimize, "Reviewed Windows interpreter invocation required")
    profiles = {"awards": args.awards, "grand": args.grand, "projects": args.projects}
    require(args.fixture == "jpl_before" and profiles == WIDTHS,
            "This one-use diagnostic accepts only jpl_before with explicit widths 5/4/6")
    project = Path(__file__).absolute().parents[1]
    generic = load_generic(project)
    project = generic.ordinary(project)
    own_path = generic.ordinary(Path(__file__).absolute(), file=True)
    require(own_path == project / "tools/probe_public_retail_partial_inflate.py", "Unexpected wrapper source path")
    own_input = generic.artifact(own_path)
    source = generic.ordinary(project / "Tests/retail_public_probe.cpp", file=True)
    helper_paths = [generic.ordinary(project / "tools" / name, file=True) for name in
                    ("probe_public_retail_save.py", "verify_retail_save_header.py", "native_build.py", "collect_baseline.py")]
    from verify_retail_save_header import COMPILER, COMPILER_SHA, VS, pe_imports
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"".decode(encoding)
    headers = generic.host_headers(source, project)
    inputs = [generic.artifact(path) for path in (source, *headers, *helper_paths)]
    compiler_path = generic.ordinary(COMPILER, file=True)
    compiler = generic.artifact(compiler_path)
    require(compiler["sha256"] == COMPILER_SHA, "Reviewed compiler changed")
    fingerprint = generic.identity({"schema": "zerosis.public_retail_probe.fingerprint.v1", "inputs": inputs, "compiler": compiler})
    require(fingerprint == BUILD_FINGERPRINT, "Existing generic build inputs no longer match the frozen fingerprint")
    parent = generic.ordinary(project / "evidence/retail_save_container/players/probes")
    root = generic.ordinary(project / "Build/RetailPublicProbe" / BUILD_FINGERPRINT)
    build_evidence = generic.ordinary(parent / ("compile_" + BUILD_FINGERPRINT))
    build_report_path = generic.ordinary(build_evidence / "build_result.json", file=True)
    require(root.is_dir() and build_evidence.is_dir(), "Verified existing build is unavailable; compilation is forbidden")
    build_pin = generic.artifact(build_report_path)
    require(build_pin["sha256"] == BUILD_REPORT_SHA256, "Frozen generic build report changed")
    build = generic.read_json(build_report_path)
    require(build.get("fingerprint") == BUILD_FINGERPRINT and build.get("inputs") == inputs and build.get("compiler") == compiler and
            generic.key(build.get("build_root", "")) == generic.key(root), "Frozen build/result inputs differ")
    manifest_path = generic.ordinary(project / "evidence/retail_save_container/players/public_fixture_candidates.json", file=True)
    manifest_pin = generic.artifact(manifest_path, generic.MAX_JSON)
    candidate = generic.select_fixture(generic.read_json(manifest_path), args.fixture)
    require(generic.identity({"build": BUILD_FINGERPRINT, "fixture": candidate, "profiles": WIDTHS,
                              "manifest": manifest_pin}) == ORIGINAL_PROBE_ID, "Original fixture observation identity differs")
    original, original_pin, original_pins = verify_original(generic, project, inputs, compiler, manifest_pin, candidate)
    require(original.get("compile_report") == build_pin, "Original observation points to a different build receipt")
    offset = original["native_results"][0]["observation"]["compressed_offset"]
    # Fetch the exact pinned raw fixture into RAM before the offline audit guard.
    raw, raw_identity = generic.fetch_fixture(candidate)
    require(raw_identity == original.get("raw") and len(raw) <= MAX_RAW_BYTES and
            original["native_results"][0].get("stdin_bytes") == len(raw) and
            original["native_results"][0].get("stdin_sha256") == raw_identity["sha256"],
            "Downloaded raw fixture differs from the exact original header observation")
    protected = [*inputs, compiler, manifest_pin, own_input, build_pin, *original_pins]
    generic.unchanged(protected)
    partial_id = generic.identity({"schema": "zerosis.public_retail_partial_inflate.identity.v1", "wrapper": own_input,
        "generic_build": build_pin, "original_probe": original_pin, "manifest": manifest_pin,
        "fixture": candidate, "profiles": WIDTHS, "chunk_bytes": CHUNK_BYTES,
        "python_version": sys.version.split()[0], "zlib_compile": zlib.ZLIB_VERSION, "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION})
    evidence = generic.ordinary(parent / ("partial_jpl_before_" + partial_id))
    report_path = evidence / "partial_result.json"
    require(not evidence.exists() or evidence.is_dir() and report_path.is_file(), "Inspect partial diagnostic output before retrying")
    require(parent.is_dir(), "Existing probe-evidence parent is unavailable")
    command = (str(root / "RetailPublicProbe.exe"), "--inflated", "--awards", "5", "--grand", "4", "--projects", "6")
    artifacts = build.get("artifacts")
    require(isinstance(artifacts, dict) and set(artifacts) == {"executable", "response", "dependencies", "compile_log"},
            "Frozen build artifact set differs")
    readable = [Path(row["path"]) for row in protected + list(artifacts.values())]
    writable = [evidence / name for name in ("partial_started.json", "chunks.json", "inflated.json", "inflated.stderr.log",
                                             "partial_result.json", "failed_attempt.json")]
    original_directory = Path(original_pin["path"]).parent

    class PartialGuard(generic.OfflineGuard):
        def audit(self, event, event_args):
            if event == "os.mkdir" and generic.key(self.target(event_args[0])) != generic.key(evidence):
                self.fail("Partial diagnostic cannot create or rebuild an existing build directory")
            if event == "os.remove":
                self.fail("Partial diagnostic never deletes files")
            super().audit(event, event_args)

    guard = PartialGuard(commands=[command], directory=root, readable=readable, writable=writable,
                         directories=[root, build_evidence, original_directory, evidence])
    sys.addaudithook(guard.audit)
    try:
        # Reuse the frozen generic helper's complete cache-validation branch.
        # Its environment initializer is replaced with a hard failure, and no
        # compiler or command-processor command is in this guard's allowlist.
        verified_build, environment = generic.ensure_build(project=project, root=root, evidence=build_evidence,
            source=source, headers=headers, inputs=inputs, compiler=compiler, compiler_path=compiler_path,
            vs=VS, command=(), environment_for=never_compile, pe_imports=pe_imports, guard=guard,
            fingerprint=BUILD_FINGERPRINT)
        require(verified_build == build and not guard.calls, "Existing build validation unexpectedly launched a child")
        if report_path.exists():
            prior = generic.read_json(report_path)
            require(prior.get("status") == "OBSERVED_INCOMPLETE_PUBLIC_RETAIL_PREFIX" and
                    prior.get("partial_identity") == partial_id and prior.get("wrapper_input") == own_input and
                    prior.get("generic_build_report") == build_pin and prior.get("original_probe_report") == original_pin and
                    prior.get("raw") == raw_identity and prior.get("profiles") == WIDTHS and
                    prior.get("guard_passed") is True and prior.get("forbidden_access_attempts") == [] and
                    prior.get("prefix_explicitly_incomplete") is True and
                    all(prior.get(name) is False for name in generic.FLAGS_FALSE), "Existing partial observation identity differs")
            expected = {"partial_started.json", "chunks.json", "partial_result.json"}
            pins = []
            for name, file_name in (("started_log", "partial_started.json"), ("chunks_log", "chunks.json")):
                require(generic.key(prior[name]["path"]) == generic.key(evidence / file_name), "Cached partial log path differs")
                pins.append(prior[name])
            native = prior.get("native_result")
            if native is not None:
                require(native.get("mode") == "inflated", "Cached partial native mode differs")
                for name, file_name in (("json_log", "inflated.json"), ("stderr_log", "inflated.stderr.log")):
                    require(generic.key(native[name]["path"]) == generic.key(evidence / file_name), "Cached native log path differs")
                    pins.append(native[name]); expected.add(file_name)
                require(generic.read_json(evidence / "inflated.json") == native["observation"], "Cached native observation differs")
                generic.small_native_json(json.dumps(native["observation"]).encode("utf-8"))
            generic.unchanged(pins + protected + list(artifacts.values()))
            require({child.name for child in evidence.iterdir()} == expected and not guard.denied and not guard.calls,
                    "Cached partial directory or offline state differs")
            return {"status": prior["status"], "reused": True, "report": generic.artifact(report_path),
                    "prefix_explicitly_incomplete": True, "new_compilation_permitted": False,
                    **{name: False for name in generic.FLAGS_FALSE}}
        evidence.mkdir()
        generic.write_json(evidence / "partial_started.json", {"schema": "zerosis.public_retail_partial_inflate.started.v1",
            "partial_identity": partial_id, "wrapper_input": own_input, "generic_build_report": build_pin,
            "original_probe_report": original_pin, "fixture": candidate, "raw": raw_identity, "profiles": WIDTHS,
            "compressed_offset_from_original_header": offset, "new_compilation_permitted": False,
            "prefix_explicitly_incomplete": True})
        prefix, observation = emitted_prefix(raw, offset)
        generic.write_json(evidence / "chunks.json", observation)
        native = None
        if prefix:
            native = generic.run_native(command, prefix, root=root, environment=environment, evidence=evidence, mode="inflated")
        generic.unchanged(protected + list(artifacts.values()))
        require(not guard.denied and guard.calls == ([list(command)] if prefix else []),
                "Partial diagnostic exceeded its single native-command allowance")
        report = {"schema": "zerosis.public_retail_partial_inflate.observation.v1",
            "status": "OBSERVED_INCOMPLETE_PUBLIC_RETAIL_PREFIX", "utc": datetime.now(timezone.utc).isoformat(),
            "partial_identity": partial_id, "wrapper_input": own_input, "generic_helper_sha256": GENERIC_SHA256,
            "generic_build_fingerprint": BUILD_FINGERPRINT, "generic_build_report": build_pin,
            "original_probe_report": original_pin, "fixture": candidate, "raw": raw_identity, "profiles": WIDTHS,
            "python_version": sys.version.split()[0], "zlib_compile": zlib.ZLIB_VERSION, "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
            "inflation": {name: value for name, value in observation.items() if name != "chunks"},
            "started_log": generic.artifact(evidence / "partial_started.json"),
            "chunks_log": generic.artifact(evidence / "chunks.json"), "native_result": native,
            "native_skipped_reason": "no_successfully_returned_prefix" if native is None else None,
            "native_stdin_explicitly_incomplete": True, "guard_passed": True, "child_commands": guard.calls,
            "forbidden_access_attempts": guard.denied, "new_compilation_permitted": False,
            "prefix_explicitly_incomplete": True, "whole_compressed_stream_validated": False,
            "raw_or_inflated_or_database_saved": False, "existing_inputs_and_artifacts_unchanged": True,
            "complete_container_validated": False, "sdk_restore_verified": False, "full_engine_goal_complete": False,
            **{name: False for name in generic.FLAGS_FALSE}}
        generic.write_json(report_path, report)
        return {"status": report["status"], "reused": False, "report": generic.artifact(report_path),
            "inflation": report["inflation"], "native_status": native["observation"]["status"] if native else None,
            "prefix_explicitly_incomplete": True, "new_compilation_permitted": False,
            **{name: False for name in generic.FLAGS_FALSE}}
    except BaseException as error:
        if evidence.is_dir() and not (evidence / "failed_attempt.json").exists():
            generic.write_json(evidence / "failed_attempt.json", {"status": "FAILED_PUBLIC_RETAIL_PARTIAL_DIAGNOSTIC",
                "error": type(error).__name__ + ": " + str(error), "partial_identity": partial_id,
                "wrapper_input": own_input, "generic_build_report": build_pin, "original_probe_report": original_pin,
                "raw": raw_identity, "profiles": WIDTHS, "child_commands": guard.calls,
                "forbidden_access_attempts": guard.denied, "prefix_explicitly_incomplete": True,
                "new_compilation_permitted": False, "raw_or_inflated_or_database_saved": False,
                **{name: False for name in generic.FLAGS_FALSE}})
        raise


def main(argv: list[str] | None = None) -> int:
    try:
        print(json.dumps(probe(argv), ensure_ascii=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED_PUBLIC_RETAIL_PARTIAL_DIAGNOSTIC", "error": type(error).__name__ + ": " + str(error),
            "prefix_explicitly_incomplete": True, "new_compilation_permitted": False, "restore_approved": False,
            "complete_save_validated": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
