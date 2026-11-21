"""Compare fixed compressed prefixes in RAM; never approve or repair a save."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import zlib

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/retail_save_container/map_trace"
RESULT = STAGE / "input_chunk_comparison.json"
PREFIX_INPUT_BYTES = 131072
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
CASES = (
    "jpl_before_cbe56da043ef1ff7254a/result.json",
    "rivar_settler12_6401d1903f1ff45fcf8c/result.json",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    path = Path(path)
    before = path.stat()
    for part in (path, *path.parents):
        assert not part.lstat().st_file_attributes & 0x400, "Reparse input"
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    assert path.stat() == before
    return {"path": str(path), "bytes": before.st_size, "sha256": sha}


def decode(data, first):
    decoder = zlib.decompressobj()
    parts = (data,) if first == len(data) else (data[:first], data[first:])
    output = bytearray()
    calls = []
    for part in parts:
        assert len(output) < MAX_OUTPUT_BYTES
        block = decoder.decompress(part, MAX_OUTPUT_BYTES - len(output))
        output.extend(block)
        assert not decoder.unconsumed_tail and not decoder.unused_data
        calls.append({"input_bytes": len(part), "output_bytes": len(block),
                      "output_end": len(output), "output_sha256": digest(block)})
    return bytes(output), {"first_input_bytes": first, "calls": calls,
        "output_bytes": len(output), "output_sha256": digest(output), "eof": decoder.eof,
        "fresh_decoder_instances": 1, "resets": 0, "flushes": 0, "input_bytes_skipped": 0}


def declared_frame_candidate(raw, offset):
    """Inspect one explicitly declared length-prefix hypothesis, without scanning."""
    position = offset - 4
    frames = []
    payloads = []
    error = None
    for index in range(128):
        if position == len(raw):
            break
        if position < 0 or len(raw) - position < 4:
            error = "incomplete_length_word"
            break
        length = int.from_bytes(raw[position:position + 4], "little")
        if not 0 < length <= 65536:
            error = "length_outside_explicit_candidate_budget"
            break
        begin = position + 4
        if length > len(raw) - begin:
            error = "declared_payload_exceeds_input"
            break
        payload = raw[begin:begin + length]
        frames.append({"index": index, "length_offset": position, "bytes": length,
                       "payload_offset": begin, "payload_sha256": digest(payload)})
        payloads.append(payload)
        position = begin + length
    if position != len(raw) and error is None:
        error = "frame_count_budget"
    result = {"hypothesis": "u32_length_then_payload_repeated_from_first_length_word",
        "producer_contract_verified": False, "start": offset - 4, "end": position,
        "raw_bytes": len(raw), "frames": frames, "error": error,
        "declared_lengths_cover_input": error is None and position == len(raw),
        "signature_search": False, "resynchronization": False, "save_accepted": False}
    if result["declared_lengths_cover_input"]:
        decoder = zlib.decompressobj()
        output = bytearray()
        calls = []
        try:
            for payload in payloads:
                assert len(output) < MAX_OUTPUT_BYTES
                block = decoder.decompress(payload, MAX_OUTPUT_BYTES - len(output))
                output.extend(block)
                calls.append({"input_bytes": len(payload), "output_bytes": len(block),
                              "output_end": len(output), "eof": decoder.eof})
                assert not decoder.unconsumed_tail and not decoder.unused_data
            result["candidate_zlib"] = {"output_bytes": len(output), "output_sha256": digest(output),
                "eof": decoder.eof, "calls": calls, "unused_bytes": len(decoder.unused_data),
                "unconsumed_bytes": len(decoder.unconsumed_tail), "resets": 0, "flushes": 0}
        except zlib.error as failure:
            result["candidate_zlib"] = {"error": str(failure), "successful_output_bytes": len(output),
                "successful_output_sha256": digest(output), "eof": decoder.eof, "calls": calls}
    return result


def main():
    assert len(sys.argv) == 1 and os.name == "nt" and not sys.flags.optimize
    assert not RESULT.exists(), "Inspect the existing exact result before another comparison"
    preflight_path = STAGE / "input_chunk_preflight.json"
    assert pin(preflight_path)["sha256"] == "28b185224fe8cc2ca555147c3583038d485a5bc6c15d804512de67e93e58b84a"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    expected = {row["report"]["path"]: row["report"] for row in preflight["observations"]}
    own = pin(__file__)
    inputs = [own, pin(preflight_path), pin(Path(sys.executable).resolve())]
    module_file = getattr(zlib, "__file__", None)
    if module_file:
        inputs.append(pin(Path(module_file).resolve()))
    else:
        runtime = Path(sys.base_prefix) / ("python" + str(sys.version_info.major) + str(sys.version_info.minor) + ".dll")
        if runtime.is_file():
            inputs.append(pin(runtime.resolve()))
    network_url = None
    def audit(event, args):
        if event.startswith(("subprocess.", "ctypes.dlopen", "winreg.")) or event in (
                "os.system", "os.startfile", "os.startfile/2", "os.remove", "os.rmdir", "os.rename"):
            raise RuntimeError("No native execution, registry or deletion is allowed")
        if event == "urllib.Request" and args[0] != network_url:
            raise RuntimeError("Unexpected network URL")
        if event.startswith("socket.") and network_url is None:
            raise RuntimeError("Network disabled outside the pinned fixture download")
        if event == "open":
            write = isinstance(args[1], str) and any(char in args[1] for char in "wax+")
            write = write or isinstance(args[2], int) and bool(args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if write and os.path.normcase(os.path.abspath(args[0])) != os.path.normcase(str(RESULT)):
                raise RuntimeError("Only the small comparison receipt may be written")
    # Resolve default SSL context before the exact operation guard; no requests yet.
    import ssl
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=context))
    sys.addaudithook(audit)
    rows = []
    for relative in CASES:
        source_path = STAGE / relative
        source_pin = pin(source_path)
        assert source_pin == {k: expected[str(source_path)][k] for k in source_pin}
        inputs.append(source_pin)
        prior = json.loads(source_path.read_text(encoding="utf-8"))
        fixture = prior["fixture"]
        network_url = fixture["raw_url"]
        assert network_url.startswith("https://raw.githubusercontent.com/")
        request = urllib.request.Request(network_url, headers={"User-Agent": "ZeroSis-offline-fixture-audit"})
        with opener.open(request, timeout=20) as response:
            assert response.geturl() == network_url
            raw = response.read(fixture["bytes"] + 1)
        network_url = None
        assert len(raw) == fixture["bytes"] == prior["raw"]["bytes"]
        assert digest(raw) == prior["raw"]["sha256"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest() == fixture["git_blob_sha1"]
        offset = prior["body_offset"]
        compressed = raw[offset:offset + PREFIX_INPUT_BYTES]
        assert len(compressed) == PREFIX_INPUT_BYTES
        whole, reference = decode(compressed, PREFIX_INPUT_BYTES)
        comparisons = []
        for boundary in (65535, 65536, 65537):
            split, observation = decode(compressed, boundary)
            common = min(len(whole), len(split))
            first_difference = next((index for index in range(common) if whole[index] != split[index]), None)
            observation.update({"common_bytes": common, "first_different_byte": first_difference,
                "all_common_bytes_equal": first_difference is None, "whole_output_equal": split == whole})
            if first_difference is not None:
                observation["whole_byte_at_first_difference"] = whole[first_difference]
                observation["split_byte_at_first_difference"] = split[first_difference]
            comparisons.append(observation)
        rows.append({"fixture": fixture, "raw_sha256": digest(raw), "raw_bytes": len(raw),
            "compressed_offset": offset, "compressed_prefix_bytes": len(compressed),
            "compressed_prefix_sha256": digest(compressed), "reference": reference, "comparisons": comparisons,
            "declared_frame_candidate": declared_frame_candidate(raw, offset),
            "map_first_failure": prior["native_observation"]["error"], "raw_or_output_saved": False})
    assert network_url is None and all(pin(row["path"]) == row for row in inputs)
    equal = all(comparison["whole_output_equal"] for row in rows for comparison in row["comparisons"])
    result = {"schema": "zerosis.retail.input_chunk_comparison.v1",
        "status": "EQUAL_FIXED_COMPRESSED_PREFIX_OUTPUTS" if equal else "DIVERGENT_FIXED_COMPRESSED_PREFIX_OUTPUTS",
        "utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
        "zlib_module_origin": zlib.__spec__.origin,
        "zlib_compile_version": zlib.ZLIB_VERSION, "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        "inputs": inputs, "cases": rows, "no_signature_scanning_or_byte_repair": True,
        "compressed_stream_completeness_proved": False, "container_framing_proved": False,
        "raw_inflated_or_database_saved": False, "native_sdk_host_or_game_executed": False,
        "user_game_files_accessed": False, "full_engine_goal_complete": False}
    with RESULT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "report": pin(RESULT),
        "comparisons": [{"id": row["fixture"]["id"], "reference_bytes": row["reference"]["output_bytes"],
            "first_differences": [r["first_different_byte"] for r in row["comparisons"]],
            "equal": [r["whole_output_equal"] for r in row["comparisons"]],
            "frame_candidate": {key: value for key, value in row["declared_frame_candidate"].items()
                                if key in ("declared_lengths_cover_input", "end", "error", "candidate_zlib")}}
            for row in rows]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
