"""Check the shared native V1 codec without executing any SDK consumer.

Importing this module performs no file access, builds, downloads or child runs.
Only the portable console runs; the existing SDK archive test is compiled /c.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/native_save_archive/portable_envelope"
SOURCE = PROJECT / "Tests/native_save_envelope.cpp"
SOURCE_SHA = "152d07b042c409bf8d32d866619121ef42980f3d1af03b2154ee2aa22a238567"
SOURCE_BYTES = 41523
ENVELOPE = PROJECT / "Source/Host/NativeSaveEnvelope.h"
ENVELOPE_SHA = "f8f343d891e4e9fe7aa9d756e1c467971586125803163edf1e478717c11aa7a8"
ARCHIVE = PROJECT / "Source/Host/NativeSaveArchive.h"
ARCHIVE_SHA = "e3be711d114807d68ac2e965622dd622eb1f36c81e1da1c64f94a3a97b9e36c6"
ARCHIVE_BEFORE_SHA = "d1ce478b093adb53acb280ff8d286ffa1d791f28783d888d9f22738e69a8e5dc"
POST = PROJECT / "evidence/retail_save_container/import_sections/publication/post_checks.json"
POST_SHA = "4e634135ee2d4328d3cd42613d53e3b9d12e76da1e3354021a59295964d597e3"
CHANGE = STAGE / "source_change.json"
CHANGE_SHA = "7327f1fac7f4b7ead1f7bb19237a29c217d0e2eb1faf5867f3d9169ddafa7b99"
BACKUP = STAGE / "NativeSaveArchive.h.before.gz"
BACKUP_SHA = "8b4b9329a75ed6fa809afa000c35acb61cad77997752137b4963d8b3ccaa3953"
HISTORY = PROJECT / "evidence/native_save_archive/conformance.json"
HISTORY_SHA = "f09cd04f60154091c47e37e1b38e92085f5c728e69fba62d6e225b6f5581fa0c"
SDK_SOURCE = PROJECT / "Tests/native_save_archive.cpp"
SDK_SOURCE_SHA = "5ed4101e0b56cb167d1be2905d7bceab74bbd3c5fdd48d0d794d571cf7d08ec7"
SDK_RECIPE = PROJECT / "tools/verify_native_save_archive.py"
SDK_RECIPE_SHA = "05a46670c798237d5c763e5d6d5ef64d8fb48e78e0e22bb1c6705c7c86fa37f4"
HOST_FILES_SHA = "cd54e53060ec4699af5b5e6505d46314e12ee9f2134221a988b1d420cca522f3"
RUNTIME = PROJECT / "Build/InteractiveGameRuntime/20261022T001546Z_7fba195072e4"
REQUEST = PROJECT / "evidence/interactive_game/20261022T001546Z_7fba195072e4/request.json"
NATIVE_INPUT = RUNTIME / "sessions/5cf0696b4369a6f8a2f7a9d9419fc8d7/autosave-0-turn-0.zssave"
NATIVE_INPUT_SHA = "d4f51ae15c11bce5dbec849d271a3c6cc80c8ae9d88b8a3b2e35069b0193c07b"
MANIFEST = RUNTIME / "bundle.manifest"
MANIFEST_SHA = "3433de4f5c480f3a2a9829470982cf960acf9cd02ce4b0c4a2f17056cbb81c3b"
PINS = {
    "verify_retail_body_import": "8870d5739f97286a9d28e8fe0f595fa86afb0b146c7a3ac6aa6b4da434979f87",
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header": "9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}


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


def merge_rows(g, rows):
    """Windows path spelling is not a separate file identity."""
    result = {}
    for row in rows:
        key = g.key(row["path"])
        if key in result:
            require({name: value for name, value in result[key].items() if name != "path"} ==
                    {name: value for name, value in row.items() if name != "path"}, "Conflicting current input pins")
        else:
            result[key] = row
    return [result[key] for key in sorted(result)]


def native_v1_sample():
    """Independent format construction, without calling any C++ encoder."""
    payload = bytearray(b"ZEROSIS_SAVE_V1\0" + struct.pack("<8I", 1, 3, 123, 234, 63, 64, 64, 133))
    identities = [(kind, 0) for kind in (1, 2, 3, 4, 5)]
    identities += [(6, slot) for slot in range(64)] + [(7, slot) for slot in range(64)]
    for index, (kind, slot) in enumerate(identities):
        value = bytes((0, index, 255, 128, index ^ 165, 1, 0, (17 * index) % 256))
        payload.extend(struct.pack("<3I", kind, slot, 8))
        payload.extend(value)
    digest = hashlib.sha256(payload).digest()
    wire = bytes(payload) + digest
    require(len(payload) == 2708 and len(wire) == 2740, "Independent V1 recipe size differs")
    return {"recipe": "fixed133_binary8_v1", "flags": 3, "turn": 123, "elapsed": 234,
        "active_player": 63, "section_count": 133, "payload_bytes": len(payload), "wire_bytes": len(wire),
        "payload_sha256": digest.hex(), "wire_sha256": hashlib.sha256(wire).hexdigest(), "checksum_hex": digest.hex()}


def strict_native_v1(data, manifest):
    require(80 <= len(data) <= 32 * 1024 * 1024 and data[:16] == b"ZEROSIS_SAVE_V1\0",
            "Retained native input has an invalid V1 header or byte bound")
    end = len(data) - 32
    version, flags, turn, elapsed, active, teams, players, count = struct.unpack_from("<8I", data, 16)
    require(version == 1 and flags <= 3 and turn <= 2147483647 and elapsed <= 2147483647 and
            active < 64 and (teams, players, count) == (64, 64, 133), "Native V1 metadata or slot counts differ")
    digest = hashlib.sha256(data[:end]).digest()
    require(digest == data[end:], "Native V1 SHA256 trailer differs")
    identities = [(kind, 0) for kind in (1, 2, 3, 4, 5)]
    identities += [(6, slot) for slot in range(64)] + [(7, slot) for slot in range(64)]
    sections, cursor = [], 48
    for expected in identities:
        require(cursor <= end and end - cursor >= 12, "Native V1 descriptor is truncated")
        kind, index, size = struct.unpack_from("<3I", data, cursor)
        cursor += 12
        require((kind, index) == expected and 0 < size <= 2147483647 and size <= end - cursor,
                "Native V1 section identity, order or payload bound differs")
        sections.append({"kind": kind, "index": index, "offset": cursor, "bytes": size})
        cursor += size
    require(cursor == end, "Native V1 has trailing or missing section bytes")
    bundle = sections[0]
    require(data[bundle["offset"]:bundle["offset"] + bundle["bytes"]] == manifest,
            "Native V1 Bundle section does not match the retained request manifest bytes")
    return {"input_bytes": len(data), "payload_bytes": end, "wire_bytes": len(data), "section_count": 133,
        "flags": flags, "turn": turn, "elapsed": elapsed, "active_player": active,
        "payload_sha256": digest.hex(), "wire_sha256": hashlib.sha256(data).hexdigest(), "checksum_hex": data[end:].hex(),
        "roundtrip_exact": True, "all_sections_nonempty": True, "ordered_section_layout": True,
        "source_bytes_unchanged": True, "decoded_storage_owned": True, "sections": sections,
        "bundle_bytes": len(manifest), "bundle_sha256": hashlib.sha256(manifest).hexdigest()}


def block(data, start, end):
    first = data.index(start)
    return data[first:data.index(end, first) + len(end)]


def source_proof(g, before):
    after, codec = g.read_bytes(ARCHIVE, 8192), g.read_bytes(ENVELOPE, 8192)
    regions = {}
    markers = {
        "transaction": (b"class NativeSaveTransaction final {", b"\n};\n"),
        "cng_digest": (b"    static std::array<unsigned char,32> Digest(", b"\n    }\n"),
        "read": (b"    static std::vector<unsigned char> Read(", b"\n    }\n"),
        "write_atomic": (b"    static void WriteAtomic(", b"\n    }\n"),
    }
    for name, (start, end) in markers.items():
        old, new = block(before, start, end), block(after, start, end)
        require(old == new, "Platform archive implementation changed: " + name)
        regions[name] = {"bytes": len(old), "sha256": hashlib.sha256(old).hexdigest(), "before_after_identical": True}
    start = b"    static unsigned SectionCount() noexcept"
    old = before[before.index(start):before.index(b"    static std::vector<unsigned char> Read(")]
    restored = codec[codec.index(start):codec.index(b"private:\n")]
    for left, right in (
        (b"    template<class DigestFunction>\n", b""),
        (b"Encode(DigestFunction digestFunction) const", b"Encode() const"),
        (b"bytes,DigestFunction digestFunction)", b"bytes)"),
        (b"const std::array<unsigned char,32> digest=digestFunction(", b"const auto digest=Digest("),
        (b"NativeSaveEnvelope", b"NativeSaveArchive"),
        (b"TeamSlots", b"MAX_TEAMS"), (b"PlayerSlots", b"MAX_PLAYERS"),
        (b"static_cast<int>(MAX_PLAYERS)", b"MAX_PLAYERS"),
    ):
        restored = restored.replace(left, right)
    require(restored == old and block(before, b"    static void Put(", b"\n    }\n") ==
            block(codec, b"    static void Put(", b"\n    }\n") and
            block(before, b"struct NativeSaveSection {", b"\n};\n") ==
            block(codec, b"struct NativeSaveSection {", b"\n};\n"),
            "Extracted V1 codec differs after the declared class, slot and digest substitutions")
    compact = re.sub(rb"\s+", b"", after)
    require(all(value in compact for value in (
        b"structNativeSaveArchive:NativeSaveEnvelope{",
        b"returnNativeSaveEnvelope::Encode(&NativeSaveArchive::Digest);",
        b"static_cast<NativeSaveEnvelope&>(result)=NativeSaveEnvelope::Decode(bytes,&NativeSaveArchive::Digest);",
        b"static_assert(static_cast<unsigned>(MAX_TEAMS)==NativeSaveEnvelope::TeamSlots&&static_cast<unsigned>(MAX_PLAYERS)==NativeSaveEnvelope::PlayerSlots,")),
        "Production wrapper delegation or SDK slot assertion differs")
    return {"codec_reverse_substitutions_match_original_bytes": True,
        "codec_original_region_bytes": len(old), "codec_original_region_sha256": hashlib.sha256(old).hexdigest(),
        "platform_regions": regions, "production_wrapper_delegates_to_shared_codec": True,
        "sdk_64_slot_static_assert_present": True, "cng_or_file_transactions_executed": False}


def current_sdk_graph(g, history, compiler_path):
    runs = [row for row in history["runs"] if row.get("flavor") == "optimized"]
    require(len(runs) == 1 and len(runs[0]["compiler_inputs"]) == 421 and
            history["test_source"]["sha256"] == SDK_SOURCE_SHA, "Historical SDK graph locator differs")
    roots = [PROJECT / relative for relative in ("Source/Host", "Source/Porting", "Source/SDK_BNW_x64")]
    roots += [compiler_path.parents[3] / "include",
        Path(r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0")]
    revisions, rows, seen = [], [], {}
    duplicates = 0
    known_revisions = {g.key(ARCHIVE): ARCHIVE_SHA, g.key(PROJECT / "Source/Host/HostFiles.h"): HOST_FILES_SHA}
    for old in runs[0]["compiler_inputs"]:
        key = g.key(old["path"])
        if key in seen:
            require(seen[key] == old["sha256"], "Repeated historical input has conflicting SHA256")
            duplicates += 1
            continue
        path = g.ordinary(Path(old["path"]), file=True)
        require((key == g.key(SDK_SOURCE) or any(g.within(path, root) for root in roots)) and
                not g.forbidden(path), "Historical SDK graph contains an unexpected source path")
        seen[key] = old["sha256"]
        current = g.artifact(path)
        if current["sha256"] != old["sha256"]:
            require(known_revisions.get(key) == current["sha256"], "Unreviewed historical SDK input revision: " + path.name)
            revisions.append({"path": current["path"], "historical_sha256": old["sha256"],
                "current_bytes": current["bytes"], "current_sha256": current["sha256"],
                "scope": "authorized_current_stage_archive_refactor" if key == g.key(ARCHIVE) else "pre_existing_revision"})
        rows.append(current)
    require(len(rows) == 390 and duplicates == 31, "Historical unique and repeated input counts differ")
    require({g.key(row["path"]) for row in revisions} == set(known_revisions), "Historical revision manifest differs")
    return rows, revisions


def sdk_response(root):
    sdk = PROJECT / "Source/SDK_BNW_x64"
    includes = [sdk / relative for relative in (
        "CvGameCoreDLL_Expansion2", "CvGameCoreDLLUtil/include", "CvGameDatabase/include", "CvLocalization/include",
        "CvWorldBuilderMap/include", "FirePlace/include", "FirePlace/include/FireWorks", "ThirdPartyLibs/Lua51/include")]
    flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/O2", "/MD", "/fp:strict", "/c",
        "/source-charset:windows-1252", "/external:W0", "/DWIN32", "/DNDEBUG", "/DFINAL_RELEASE",
        "/D_CRT_SECURE_NO_WARNINGS", "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS", "/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING"]
    flags += [f'/external:I"{path}"' for path in includes]
    flags += [f'/I"{PROJECT / "Source/Host"}"', f'/I"{PROJECT / "Source/Porting"}"', f'"{SDK_SOURCE}"',
        f'/Fo"{root / "sdk_native_save_archive.obj"}"', f'/sourceDependencies "{root / "sdk_dependencies.json"}"']
    return "\n".join(flags) + "\n"


def object_proof(g, path):
    data = g.read_bytes(path, 8 * 1024 * 1024)
    require(len(data) >= 20, "SDK object has no complete COFF header")
    machine, sections, _, symbols, count, optional, characteristics = struct.unpack_from("<HHIIIHH", data)
    require(machine == 0x8664 and sections > 0 and optional == 0 and characteristics & 0x0002 == 0 and
            20 + 40 * sections <= len(data) and symbols <= len(data) and count <= (len(data) - symbols) // 18,
            "Compile-only SDK output is not bounded standalone AMD64 COFF")
    return {"machine": "0x8664", "section_count": sections, "symbol_count": count,
        "optional_header_bytes": optional, "executable_image": False, "object_executed": False}


def capture(g, command, root, environment, prefix, encoding, maximum, timeout, data=b""):
    timed_out = False
    try:
        child = subprocess.run(command, cwd=root, env=environment, input=data, capture_output=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        stdout, stderr, code = child.stdout, child.stderr, child.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code = error.stdout or b"", error.stderr or b"", None
        timed_out = True
    paths = {name: STAGE / (prefix + suffix) for name, suffix in
        (("stdout", ".stdout.log"), ("stderr", ".stderr.log"), ("process", ".process.json"))}
    for name, data in (("stdout", stdout), ("stderr", stderr)):
        g.write_text(paths[name], data[:maximum].decode(encoding, errors="replace"), maximum * 3)
    g.write_json(paths["process"], {"command": list(command), "returncode": code, "timed_out": timed_out,
        "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
        "stdout_truncated": len(stdout) > maximum, "stderr_truncated": len(stderr) > maximum})
    require(not timed_out and code == 0 and len(stdout) <= maximum and len(stderr) <= maximum,
            "Inspect the preserved child logs: " + prefix)
    return stdout, stderr, {name: g.artifact(path) for name, path in paths.items()}


def check_native(base, stdout, sample, mode="self-test"):
    value = json.loads(stdout.decode("utf-8-sig"))
    require(type(value) is dict and value.get("schema") == "zerosis.native_save.envelope_test.v1" and
            value.get("status") == "PASS_NATIVE_SAVE_ENVELOPE_COMPONENT" and value.get("mode") == mode,
            "Portable envelope schema or status differs")
    require(all(type(value.get(name)) is int and value[name] >= (1 if mode == "self-test" else 0) for name in
        ("checks", "sha256_vectors", "literal_wire_cases", "roundtrip_cases", "truncations",
         "directed_corruptions", "atomic_failure_cases", "digest_callback_cases")) and value["checks"] > 0,
         "Portable coverage counters differ")
    require(all(value.get(name) is True for name in
        ("input_bytes_unchanged", "input_files_unchanged", "all_failure_outputs_unchanged", "test_only_sha256")) and
        value.get("digest_implementation") == "test_only_portable_sha256", "Portable preservation or digest scope differs")
    require(all(value.get(name) is False for name in (*base.FALSE_FLAGS, "native_restore_approved",
        "bundle_identity_verified", "producer_contract_verified", "complete_save_verified", "production_cng_executed",
        "payload_semantics_verified")), "Portable test exceeded its SDK, identity or approval scope")
    if mode == "self-test":
        require(base.same_structure(value.get("sample"), sample), "Independent Python full V1 bytes or SHA256 differ")
    else:
        require(value.get("sample") is None and value.get("stdin_read_complete") is True and
                value["roundtrip_cases"] > 0 and value["digest_callback_cases"] > 0 and
                base.same_structure(value.get("native_input"), sample), "Independent retained native V1 observation differs")
    return value


def main():
    require(os.name == "nt" and len(sys.argv) == 1 and not sys.flags.optimize, "Require Windows and no runner arguments")
    require(len(SOURCE_SHA) == 64, "Portable test source has not been frozen")
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
    fixed = {}
    for name, path, count, digest in (
        ("publication", POST, 47491, POST_SHA), ("source_change", CHANGE, 2174, CHANGE_SHA),
        ("before_gzip", BACKUP, 2781, BACKUP_SHA), ("historical_graph", HISTORY, 215516, HISTORY_SHA),
        ("sdk_recipe", SDK_RECIPE, 7011, SDK_RECIPE_SHA), ("sdk_test", SDK_SOURCE, 9327, SDK_SOURCE_SHA),
        ("portable_test", SOURCE, SOURCE_BYTES, SOURCE_SHA), ("envelope", ENVELOPE, 5188, ENVELOPE_SHA),
        ("archive", ARCHIVE, 5320, ARCHIVE_SHA), ("retained_native_input", NATIVE_INPUT, 9612910, NATIVE_INPUT_SHA),
        ("retained_bundle_manifest", MANIFEST, 2048, MANIFEST_SHA)):
        row = g.artifact(path)
        require(row["bytes"] == count and row["sha256"] == digest, "Frozen source or evidence differs: " + path.name)
        fixed[name] = row
    post, change, history = g.read_json(POST), g.read_json(CHANGE), g.read_json(HISTORY)
    require(post["status"] == "PASS_TYPED_PREGAME_AND_PAYLOAD_SECTIONS_PROTECTED_INPUTS_AND_BOUNDED_RETIREMENT" and
        post["actual_import_entrypoint_implemented"] is False and post["sdk_restore_verified"] is False and
        post["default_provider_unchanged"] is True, "Previous publication scope differs")
    require(change["schema"] == "zerosis.native_save_envelope.source_change.v1" and
        change["status"] == "BEFORE_REFACTOR_BACKUP_VERIFIED" and change["backup_roundtrip_verified"] is True and
        change["backup"] == fixed["before_gzip"], "Immutable prechange receipt differs")
    before = gzip.decompress(g.read_bytes(BACKUP, 4096))
    require(len(before) == 9151 and hashlib.sha256(before).hexdigest() == ARCHIVE_BEFORE_SHA and
        change["before"]["bytes"] == len(before) and change["before"]["sha256"] == ARCHIVE_BEFORE_SHA and
        g.key(change["before"]["path"]) == g.key(ARCHIVE), "Backup does not restore the original archive bytes")
    frozen, revisions = [], []
    for name, count in (("protected_files", 45), ("source_contract_inputs", 17), ("source_and_proof_files", 27)):
        rows = post[name]
        require(type(rows) is list and len(rows) == count, "Previous publication pin count differs")
        for row in rows:
            expected = {key: row[key] for key in base.PIN_KEYS}
            if g.key(expected["path"]) == g.key(ARCHIVE):
                require(expected == change["before"], "Authorized source revision does not match its published before pin")
                revisions.append({"before": expected, "after": fixed["archive"], "backup": fixed["before_gzip"]})
            else:
                require(g.artifact(expected["path"]) == expected, "Published input changed: " + expected["path"])
                frozen.append(expected)
    require(len(revisions) == 1, "The publication does not contain exactly one authorized archive revision")
    fixed["retained_runtime_request"] = g.artifact(REQUEST)
    request = g.read_json(REQUEST)
    require(g.key(request["cwd"]) == g.key(RUNTIME) and type(request["runtime_inputs"]) is list and
            len(request["runtime_inputs"]) == 24, "Retained runtime request identity or input count differs")
    protected_by_key = {g.key(row["path"]): row for row in frozen}
    runtime_keys = set()
    for row in request["runtime_inputs"]:
        key = g.key(row["path"])
        require(key not in runtime_keys and g.within(row["path"], RUNTIME) and key in protected_by_key and
                protected_by_key[key]["sha256"] == row["sha256"], "Retained runtime input differs from its protected request")
        runtime_keys.add(key)
    require(g.key(MANIFEST) in runtime_keys and g.key(REQUEST) in protected_by_key and
            fixed["retained_runtime_request"] == protected_by_key[g.key(REQUEST)], "Retained request manifest is not protected")
    native_bytes, manifest_bytes = g.read_bytes(NATIVE_INPUT, 32 * 1024 * 1024), g.read_bytes(MANIFEST, 16384)
    native_expected = strict_native_v1(native_bytes, manifest_bytes)
    retired = post["retired_files"]
    require(type(retired) is list and len(retired) == 5 and all(not g.ordinary(Path(row["path"])).exists() for row in retired),
            "A previously retired file has reappeared")
    static_proof = source_proof(g, before)
    sdk_rows, historical_revisions = current_sdk_graph(g, history, h.COMPILER)
    headers = g.host_headers(SOURCE, PROJECT)
    require({g.key(path) for path in headers} == {g.key(ENVELOPE)}, "Portable test includes a platform or SDK header")
    inputs = merge_rows(g, frozen + list(fixed.values()) + [g.artifact(Path(__file__).absolute())] + sdk_rows +
        [g.artifact(PROJECT / "tools" / (name + ".py")) for name in PINS])
    compiler = g.artifact(h.COMPILER)
    require(compiler["sha256"] == h.COMPILER_SHA, "Reviewed compiler differs")
    fingerprint = g.identity({"schema": "zerosis.native_save.envelope.identity.v1", "inputs": inputs, "compiler": compiler})
    parent = g.ordinary(PROJECT / "Build/NativeSaveEnvelope")
    parent.mkdir(parents=True, exist_ok=True)
    root, evidence = g.ordinary(parent / fingerprint), g.ordinary(STAGE / ("compile_" + fingerprint))
    result_path, started_path, failed_path = [STAGE / name for name in ("result.json", "started.json", "failed_attempt.json")]
    require(not any(path.exists() for path in (root, evidence, result_path, started_path, failed_path)),
            "Inspect the retained previous envelope attempt before retrying")
    env_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    compile_command = (str(h.COMPILER), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
        "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    self_command = (str(root / "RetailPublicProbe.exe"), "--self-test")
    native_command = (str(root / "RetailPublicProbe.exe"), "--stdin-native", str(len(native_bytes)))
    sdk_command = (str(h.COMPILER), "@" + str(root / "sdk_compile.rsp"))
    commands = [env_command, compile_command, self_command, native_command, sdk_command]
    writable = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp", "dependencies.json",
        "read_build_environment.cmd", "sdk_compile.rsp", "sdk_dependencies.json", "sdk_native_save_archive.obj")]
    writable += [evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    writable += [result_path, started_path, failed_path]
    for prefix in ("self", "native_stdin", "sdk_compile_only"):
        writable += [STAGE / (prefix + suffix) for suffix in (".stdout.log", ".stderr.log", ".process.json")]
    require(not any(path.exists() for path in writable), "An unreviewed output already exists")
    g.unchanged(inputs + [compiler])
    guard = g.OfflineGuard(commands=commands, directory=root,
        readable=[Path(row["path"]) for row in inputs + [compiler]], writable=writable, directories=[root, evidence])

    def checked_environment_for(vs, architecture, directory):
        environment, selected_compiler = n.environment_for(vs, architecture, directory)
        require(not any(environment.get(name) for name in ("CL", "_CL_", "LINK")), "Unreviewed inherited compiler options")
        return environment, selected_compiler

    sys.addaudithook(guard.audit)
    try:
        g.write_json(started_path, {"schema": "zerosis.native_save.envelope.started.v1", "fingerprint": fingerprint,
            "inputs": inputs, "commands": commands, "sdk_consumer_execution_authorized_by_this_runner": False})
        build, environment = g.ensure_build(project=PROJECT, root=root, evidence=evidence, source=SOURCE,
            headers=headers, inputs=inputs, compiler=compiler, compiler_path=h.COMPILER, vs=h.VS,
            command=compile_command, environment_for=checked_environment_for, pe_imports=h.pe_imports, guard=guard, fingerprint=fingerprint)
        require(not any(environment.get(name) for name in ("CL", "_CL_", "LINK")), "Unreviewed inherited compiler options")
        stdout, _, self_logs = capture(g, self_command, root, environment, "self", "utf-8-sig", 64 * 1024, 60)
        sample = native_v1_sample()
        observation = check_native(base, stdout, sample)
        native_stdout, _, native_logs = capture(g, native_command, root, environment, "native_stdin", "utf-8-sig",
            64 * 1024, 60, native_bytes)
        native_observation = check_native(base, native_stdout, native_expected, "stdin-native")
        response_path, dependencies_path, object_path = [root / name for name in
            ("sdk_compile.rsp", "sdk_dependencies.json", "sdk_native_save_archive.obj")]
        g.write_text(response_path, sdk_response(root), g.MAX_JSON)
        sdk_stdout, sdk_stderr, sdk_logs = capture(g, sdk_command, root, environment, "sdk_compile_only", "mbcs", 512 * 1024, 180)
        require(not re.search(r"\bwarning\s+[A-Z]+\d+",
            (sdk_stdout + sdk_stderr).decode("mbcs", errors="replace"), re.I), "Inspect the preserved SDK compile-only warning log")
        data = g.read_json(dependencies_path)["Data"]
        require(type(data.get("Includes")) is list and all(type(value) is str for value in data["Includes"]) and
            g.key(data["Source"]) == g.key(SDK_SOURCE), "SDK compiler consumed an unexpected source")
        actual = {g.key(value) for value in [data["Source"], *data["Includes"]]}
        expected = {g.key(row["path"]) for row in sdk_rows} | {g.key(ENVELOPE)}
        require(actual == expected, "Actual SDK compile-only dependency graph differs from its current pinned graph")
        coff = object_proof(g, object_path)
        sdk_artifacts = {"response": g.artifact(response_path), "dependencies": g.artifact(dependencies_path), **sdk_logs}
        retired_sdk_object = g.retire(object_path, root, guard)
        require({path.name for path in root.iterdir()} == {"RetailPublicProbe.exe", "compile.rsp", "dependencies.json",
            "sdk_compile.rsp", "sdk_dependencies.json"}, "Unexpected build output or SDK executable exists")
        g.unchanged(inputs + [compiler] + list(build["artifacts"].values()) + list(sdk_artifacts.values()) +
            list(self_logs.values()) + list(native_logs.values()))
        require(all(not Path(row["path"]).exists() for row in retired), "A retired previous input reappeared")
        require(not guard.denied and guard.calls == [list(command) for command in commands], "Offline command or access scope differs")
        retired_now = [*build["retired_intermediates"], retired_sdk_object]
        report = {"schema": "zerosis.native_save.envelope.component.v1", "status": "PASS_PORTABLE_NATIVE_SAVE_ENVELOPE_COMPONENT",
            "utc": datetime.now(timezone.utc).isoformat(), "inputs": inputs, "previous_publication": fixed["publication"],
            "frozen_previous_counts": {"protected": 45, "source_contracts": 17, "source_and_proof": 27},
            "unchanged_previous_rows": len(frozen), "authorized_source_revisions": revisions,
            "source_change_receipt": fixed["source_change"], "static_production_source_proof": static_proof,
            "portable_build_report": g.artifact(evidence / "build_result.json"), "self_test": observation, "self_logs": self_logs,
            "portable_compile_language_standard": "c++17", "sdk_compile_only_language_standard": "c++14",
            "production_codec_cxx14_validated_by_sdk_compile_only": True,
            "independent_python_v1_sample": sample, "independent_full_wire_and_sha256_match": True,
            "retained_native_input": {"input": fixed["retained_native_input"], "request": fixed["retained_runtime_request"],
                "bundle_manifest": fixed["retained_bundle_manifest"], "protected_runtime_input_count": len(runtime_keys),
                "runtime_input_manifest_matches_request": True, "bundle_section_matches_manifest_bytes": True,
                "independent_python_expected_observation": native_expected, "observation": native_observation,
                "logs": native_logs, "input_bytes_saved_or_copied_to_new_file": False,
                "sdk_producer_executed_by_this_runner": False, "native_restore_approved": False},
            "sdk_compile_only": {"recipe_source": fixed["sdk_recipe"], "historical_graph": fixed["historical_graph"],
                "historical_input_occurrence_count": 421, "historical_duplicate_occurrence_count": 31,
                "historical_unique_input_count": 390, "current_snapshot_count": len(sdk_rows), "historical_revisions": historical_revisions,
                "actual_input_occurrence_count": 1 + len(data["Includes"]), "actual_unique_input_count": len(actual),
                "actual_duplicate_occurrence_count": 1 + len(data["Includes"]) - len(actual),
                "actual_current_dependency_pinset_matches": True,
                "existing_archive_test_source_unchanged": True, "coff": coff, "artifacts": sdk_artifacts,
                "sdk_consumer_executed": False, "sdk_executable_created": False},
            "previous_retired_files_still_absent_count": 5, "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            "retired_intermediates": retired_now, "retired_logical_bytes": sum(row["bytes"] for row in retired_now),
            "source_shared_with_production_archive": True, "native_v1_schema_changed": False,
            "production_cng_executed": False, "file_transactions_executed": False, "network_used": False,
            "public_retail_inputs_used": False, "sdk_host_hwnd_or_original_game_executed_by_this_runner": False,
            "user_game_files_accessed": False, "runtime_hold_state_assessed": False,
            "actual_import_entrypoint_implemented": False, "bundle_identity_verified": False,
            "producer_contract_verified": False, "ruleset_compatibility_verified": False,
            "sdk_restore_verified": False, "native_restore_approved": False, "full_engine_goal_complete": False}
        g.write_json(result_path, report)
        print(json.dumps({"status": report["status"], "report": g.artifact(result_path),
            "retired_logical_bytes": report["retired_logical_bytes"]}))
        return 0
    except BaseException as error:
        if not failed_path.exists():
            g.write_json(failed_path, {"status": "FAILED_PORTABLE_NATIVE_SAVE_ENVELOPE_COMPONENT", "error": type(error).__name__ + ": " + str(error),
                "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
                "sdk_consumer_executed": False, "production_cng_executed": False, "file_transactions_executed": False,
                "network_used": False, "user_game_files_accessed": False, "sdk_restore_verified": False,
                "native_restore_approved": False, "full_engine_goal_complete": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())

