"""Read-only postlink attestation for the shared V1 native-save Host refactor.

The only write is one fresh bounded JSON receipt chosen below host_relink.
No compiler, historical verifier, PE image, SDK, UI or process query is run.
"""
from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/native_save_archive/host_relink"
DONOR_ID = "20261018T024443Z_23a2e7fdb8ea"
DONOR_REPORT = PROJECT / "evidence/ui_window_host" / DONOR_ID / "build_result.json"
DONOR_SHA = "8e6a2a283d22e042202d98b5e59320de5de73d1f98c44762e409f21f7fea1a02"
PREVIOUS_ATTESTATION = PROJECT / "evidence/goody_hut/owned_fonts/attestation_retry.json"
PREVIOUS_ATTESTATION_SHA = "3781696d52d15ba0104d64d8ff28dd9c2d2da2fd86adc3e7e39b3c5c0e4f9bfb"
HELPER = PROJECT / "evidence/goody_hut/owned_fonts/verify_candidate.py"
HELPER_SHA = "723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f"
ARCHIVE = PROJECT / "Source/Host/NativeSaveArchive.h"
ENVELOPE = PROJECT / "Source/Host/NativeSaveEnvelope.h"
ARCHIVE_SHA = "e3be711d114807d68ac2e965622dd622eb1f36c81e1da1c64f94a3a97b9e36c6"
ENVELOPE_SHA = "f8f343d891e4e9fe7aa9d756e1c467971586125803163edf1e478717c11aa7a8"
GENERATED = PROJECT / "Source/Host/UiPopupAssets.generated.h"
GENERATED_SHA = "333cf40c942e2545c83372084ed276e2aec11ab9fd7cbf4744f8c0c4e7c48da9"
COMPONENT = PROJECT / "evidence/native_save_archive/portable_envelope/result.json"
COMPONENT_SHA = "62acfd495ea42514be16d55cef421fcbb6965a955a362680fa2e650775769f7f"
SOURCE_PROOF = PROJECT / "evidence/native_save_archive/portable_envelope/publication/source_proof.json"
SOURCE_PROOF_SHA = "57b32c30ca0e41f53166d3c6a35df7df13c68620e98802b278d9e4d9318a46ab"
TUS = ("host_main", "window", "renderer", "world_renderer", "terrain_renderer")
TU_SOURCES = dict(zip(TUS, ("HostMain.cpp", "BitmapWindow.cpp", "BitmapRenderer.cpp", "WorldViewRenderer.cpp", "WorldTerrainRenderer.cpp")))
IMPLICIT_LIBS = {"msvcrt.lib", "msvcprt.lib", "bcrypt.lib", "kernel32.lib", "vcruntime.lib", "ucrt.lib"}
PINNED_LIBS = IMPLICIT_LIBS | {"oldnames.lib", "uuid.lib"}
POST = PROJECT / "evidence/native_save_archive/portable_envelope/publication/post_checks.json"
POST_SHA = "c7ff3b7e9f2d8887ee0f8ed2c854c240861eeec6a2b8585df1add82d831e01e1"
BUILDER = PROJECT / "tools/relink_native_save_host.py"
BUILDER_SHA = "d71804ab30e4cd60f41c16e95dbf24b9f134666a0a9d63f56ee68510eaab3ee1"
CONTINUATION = PROJECT / "tools/continue_native_host_link.py"
CONTINUATION_SHA = "ac0f9d12a05397cb9f617d0cf8dd4b3c7c11f0ac5f38bdaff3eb0153b2b83873"
CURRENT_BUILD_ID = "20261024T021245Z_18bbd0dd26e7"
CURRENT_REPORT_SHA = "26edcf537984d5bf6cc74be3a908dcec92fda946ba03a2e5188fb32a22fbf5f2"
CURRENT_RUN_SHA = "a3ebae48edda61d7b527ee8fa3009e41893c3ad9fac557898a5a8f07b09ac642"
FRONTEND_AUTHORIZATION = PROJECT / "evidence/goody_hut/runtime_fonts/isolated_resume_20261024/authorization.json"
FRONTEND_AUTHORIZATION_SHA = "70ceaed2bb2f7246db4e38d0acbfbf8fbf18cee8336c92f56e8f0eacb1df4486"
FRONTEND_RUNTIME_ID = "20261022T001546Z_7fba195072e4"
FRONTEND_REVISIONS = {
    "tools/render_ui_popup.py": (89484, "27ad0784eb202fc348a75d41cacf446658b3bb58ff2058dbcc77856933db64dc",
        90455, "ad7f8752a0d4fa7168d9803788606f8ff75636479f09b96644a3ac60b0957c77"),
    "tools/ui_pixel_scene.py": (386367, "b17f71a637001cce50db59cdc49999db375735afd11a2a184a8e50756641ba90",
        394040, "80b1a85eaa17cee1f01308f09aa8596af249a2d206ab54485646333f7cedd847"),
}
LIBRARY_DONOR = PROJECT / "evidence/found_value_shared_bridge/20261002T152931Z_bbc131426b"
LIBRARY_DONOR_SHA = "da2f1d5d9e759cbff7618ea280a3878177f16dc1f59d945d57e67be4a01d43df"
READ_ROOTS = (PROJECT, Path(r"C:\Program Files\Microsoft Visual Studio"), Path(r"C:\Program Files (x86)\Windows Kits\10"))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def forbidden(path):
    parts = {part.casefold() for part in Path(os.fsdecode(path)).parts}
    return bool(parts & {"my games", "mods", "saves", ".codex"}) or {"steamapps", "common"} <= parts


def ordinary(path, *, file=True):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.abspath(path) and not forbidden(path), "Noncanonical or forbidden input")
    require(any(within(path, root) for root in READ_ROOTS), "Input escaped reviewed project/toolchain roots")
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Reparse input or ancestor")
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode), "Unexpected input kind")
    return info


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, "Duplicate JSON key")
        result[name] = value
    return result


class Inputs:
    def __init__(self, reads):
        self.reads, self.rows = reads, {}

    def ref(self, path, expected=None):
        path = Path(path); before = ordinary(path)
        require(before.st_size <= 128 * 1024 * 1024, "Input exceeds the hash budget")
        self.reads.add(key(path))
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = ordinary(path)
        require(identity(before) == identity(after), "Input changed during hashing")
        row = dict(path=str(path), bytes=before.st_size, sha256=digest,
            file_identity=[before.st_dev, before.st_ino], mtime_ns=before.st_mtime_ns)
        if expected is not None:
            require(type(expected) is dict and key(expected["path"]) == key(path) and expected["sha256"] == digest and
                expected.get("bytes", expected.get("size", before.st_size)) == before.st_size and
                expected.get("size", before.st_size) == before.st_size and
                expected.get("file_identity", row["file_identity"]) == row["file_identity"] and
                expected.get("mtime_ns", row["mtime_ns"]) == row["mtime_ns"], "Sealed input identity differs")
        require(key(path) not in self.rows or self.rows[key(path)] == row, "Input changed between reads")
        self.rows[key(path)] = row
        return row

    def sealed(self, row, expected_path=None):
        require(type(row) is dict and type(row.get("path")) is str and
            re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")), "Malformed artifact reference")
        return self.ref(expected_path or row["path"], row)

    def read(self, path, maximum=4 * 1024 * 1024):
        row = self.ref(path)
        require(row["bytes"] <= maximum, "Input exceeds its read budget")
        raw = Path(path).read_bytes()
        require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], "Input changed during reading")
        return raw

    def document(self, path):
        return json.loads(self.read(path).decode("utf-8-sig"), object_pairs_hook=unique_object,
            parse_constant=lambda value: require(False, "Nonfinite JSON number"))

    def stable(self):
        for row in list(self.rows.values()):
            self.sealed(row)


def install_guard(output):
    reads, denied, published = set(), [], False

    def audit(event, args):
        nonlocal published
        if event == "open":
            if not args or not isinstance(args[0], (str, bytes, os.PathLike)):
                denied.append(event); raise RuntimeError("Unscoped descriptor open denied")
            path = key(args[0]); mode, flags = args[1:3]
            writing = isinstance(mode, str) and any(c in mode for c in "wax+") or isinstance(flags, int) and bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            allowed = not forbidden(path) and (path == key(output) and not published and isinstance(flags, int) and
                flags & os.O_EXCL and flags & os.O_CREAT if writing else path in reads)
            if not allowed:
                denied.append(event); raise RuntimeError("Unapproved verifier file access")
            if writing:
                published = True
        if event.startswith(("subprocess.", "os.exec", "os.spawn", "ctypes.", "socket.", "urllib.", "http.client.")) or event in (
            "os.system", "os.startfile", "os.startfile/2", "os.posix_spawn", "os.posix_spawnp", "os.fork", "os.forkpty",
            "os.kill", "os.killpg", "os.listdir", "os.scandir", "os.chdir", "os.remove", "os.rmdir", "os.rename",
            "os.mkdir", "os.link", "os.symlink", "os.chmod"):
            denied.append(event); raise RuntimeError("Read-only verifier forbids " + event)
    sys.addaudithook(audit)
    return reads, denied


def load_parser():
    # Only pure catalog/PE/COFF functions are used; the old one-shot main is not.
    before = ordinary(HELPER)
    raw = HELPER.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == HELPER_SHA and identity(before) == identity(HELPER.stat()),
        "Reviewed catalog/PE helper differs")
    spec = importlib.util.spec_from_file_location("zerosis_relink_readonly_pe", HELPER)
    require(spec is not None and spec.loader is not None, "Cannot select the reviewed parser helper")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def rows_by_path(rows):
    require(type(rows) is list, "Expected an artifact list")
    result = {}
    for row in rows:
        require(type(row) is dict and type(row.get("path")) is str, "Malformed artifact list")
        require(key(row["path"]) not in result, "Duplicate artifact path")
        result[key(row["path"])] = row
    return result


def text(inputs, path, maximum=8 * 1024 * 1024):
    return inputs.read(path, maximum).decode("utf-8-sig").replace("\r\n", "\n")


def dependencies(inputs, row):
    inputs.sealed(row)
    doc = inputs.document(row["path"])
    require(doc.get("Version") == "1.2" and type(doc.get("Data")) is dict, "Unexpected dependency schema")
    data = doc["Data"]
    require(type(data.get("Source")) is str and type(data.get("Includes")) is list and
        all(type(p) is str for p in data["Includes"]), "Malformed dependency paths")
    require(not data.get("ProvidedModule") and not data.get("ImportedModules") and
        not data.get("ImportedHeaderUnits"), "Unexpected module dependency")
    visits = [data["Source"], *data["Includes"]]
    return data["Source"], {key(p) for p in visits}, len(visits)


def artifact_references(value):
    if type(value) is dict:
        if all(name in value for name in ("path", "sha256")) and ("bytes" in value or "size" in value):
            yield value
        for child in value.values():
            yield from artifact_references(child)
    elif type(value) is list:
        for child in value:
            yield from artifact_references(child)


def verify_sources(inputs, report, baseline, build):
    donor_root = PROJECT / "Build/UiWindowHost" / DONOR_ID
    materialized, original, donors = {}, {}, {}

    def relocate(path):
        require(within(path, donor_root), "Baseline artifact escaped the donor build")
        return build / Path(path).relative_to(donor_root)

    def original_input(path):
        row = inputs.ref(path)
        original[key(path)] = row
        return row

    def pair(old, new):
        require(key(new["path"]) == key(relocate(old["path"])), "Frozen artifact was relocated unexpectedly")
        require(within(old["path"], donor_root / "frozen"), "Donor is outside the frozen closure")
        old_ref, new_ref = inputs.sealed(old), inputs.sealed(new)
        donors[key(old["path"])] = old_ref
        source = old.get("original_path", old.get("original_source"))
        require(type(source) is str and key(new.get("original_path", new.get("original_source", ""))) == key(source),
            "Frozen input lost its original source")
        live = original_input(source)
        changed = key(source) == key(ARCHIVE)
        expected = live if changed else old_ref
        require(new_ref["bytes"] == expected["bytes"] and new_ref["sha256"] == expected["sha256"],
            "Frozen bytes do not match the authorized source")
        if changed:
            require(new.get("materialization") == "copy_changed_live_source", "Changed archive was not copied")
        else:
            require(live["bytes"] == old_ref["bytes"] and live["sha256"] == old_ref["sha256"],
                "Unapproved live source drift")
            require(new.get("materialization") == "hardlink" and
                key(new.get("reused_from_path", "")) == key(old["path"]) and
                new_ref["file_identity"] == old_ref["file_identity"] and new_ref["mtime_ns"] == old_ref["mtime_ns"],
                "Unchanged input is not the exact donor hardlink")
        materialized[key(new["path"])] = new

    for group in ("compiler_inputs", "sources", "provider_inputs", "system_libraries", "build_tools"):
        old_rows, new_rows = rows_by_path(baseline[group]), rows_by_path(report[group])
        expected = {key(relocate(row["path"])) for row in old_rows.values()}
        extras = set(new_rows) - expected
        require(expected <= set(new_rows) and len(extras) == (1 if group in ("compiler_inputs", "sources") else 0),
            "Unexpected frozen input additions or omissions")
        for row in old_rows.values():
            pair(row, new_rows[key(relocate(row["path"]))])
        for path in extras:
            row = new_rows[path]
            source = row.get("original_path", row.get("original_source"))
            require(key(source or "") == key(ENVELOPE) and Path(row["path"]).name == ENVELOPE.name and
                row.get("materialization") == "copy_changed_live_source", "Only the new envelope header may be added")
            live, frozen = original_input(ENVELOPE), inputs.sealed(row)
            require(live["sha256"] == frozen["sha256"] == ENVELOPE_SHA and live["bytes"] == frozen["bytes"],
                "New envelope snapshot differs")
            template = next(r for r in baseline["compiler_inputs"] if key(r["original_path"]) == key(ARCHIVE))
            require(key(row["path"]) == key(relocate(Path(template["path"]).with_name(ENVELOPE.name))),
                "Envelope was added outside the mapped include root")
            materialized[path] = row
    require(len(report["compiler_inputs"]) == 545 and report["compiler_dependency_count"] == 545 and
        len(report["sources"]) == 81, "Current closure sizes differ")
    require(report["libraries"] == report["provider_inputs"] + report["system_libraries"], "Explicit library order differs")
    require(set(report["provider_reports"]) == set(baseline["provider_reports"]), "Provider report set differs")
    for name, old in baseline["provider_reports"].items():
        pair(old, report["provider_reports"][name])
    pair(baseline["ui_assets"], report["ui_assets"])
    require(report["ui_asset_preparation"] == dict(status="UNCHANGED_ATTESTED_67_PAYLOAD_CATALOG_REUSED", executed=False)
        and report["dependency_discovery"].get("executed") is False, "Unexpected asset regeneration/discovery")
    for name in ("compiler", "linker", "dumpbin", "executable", "map", "link_response", "link_log"):
        inputs.sealed(baseline[name]); original_input(baseline[name]["path"])
    original_input(POST)
    declared = rows_by_path(report["current_source_inputs"])
    require(set(declared) == set(original), "Current source seal is incomplete or overbroad")
    for path, row in declared.items():
        require(inputs.sealed(row) == original[path], "Current source snapshot differs")
    require(report["sources_changed_from_baseline"] == [original[key(ARCHIVE)]] and
        report["new_source_inputs"] == [original[key(ENVELOPE)]], "Authorized revision list differs")
    reuse = report["frozen_input_reuse"]
    hard = [r for r in materialized.values() if r["materialization"] == "hardlink"]
    copied = [r for r in materialized.values() if r["materialization"] != "hardlink"]
    require(reuse == dict(hardlinked_files=len(hard), hardlinked_logical_bytes=sum(r["bytes"] for r in hard),
        copied_source_bytes=sum(r["bytes"] for r in copied), donor_content_and_metadata_preserved=True),
        "Frozen reuse accounting differs")
    require({key(r.get("original_path", r.get("original_source", ""))) for r in copied} == {key(ARCHIVE), key(ENVELOPE)},
        "Unapproved frozen copies")
    return original, donors, materialized


def object_directives(raw):
    count = struct.unpack_from("<H", raw, 2)[0]
    directives = []
    for index in range(count):
        at = 20 + index * 40
        if raw[at:at + 8] == b".drectve":
            length, offset = struct.unpack_from("<II", raw, at + 16)
            directives.append(raw[offset:offset + length].decode("ascii"))
    require(directives, "COFF object lacks its linker directives")
    matches = re.findall(r'/DEFAULTLIB:(?:"([^"\s]+)"|([^\s]+))', " ".join(directives), re.I)
    return {(quoted or plain).casefold().removesuffix(".lib") + ".lib" for quoted, plain in matches}


def verify_compilation(inputs, parser, report, baseline, build):
    donor_root = PROJECT / "Build/UiWindowHost" / DONOR_ID
    closure = rows_by_path(report["compiler_inputs"])
    records, old_records = report["final_compilation"]["translation_units"], baseline["final_compilation"]["translation_units"]
    require(type(records) is list and tuple(r["translation_unit"] for r in records) == TUS and
        tuple(r["translation_unit"] for r in old_records) == TUS, "Unexpected final translation-unit order")
    union, results, objects, consumers = set(), [], [], {ARCHIVE.name: [], ENVELOPE.name: []}
    explicit = {Path(r["path"]).name.casefold() for r in report["libraries"]}
    for record, old in zip(records, old_records):
        name = record["translation_unit"]
        require(type(record["returncode"]) is int and record["returncode"] == 0, "Compiler did not succeed")
        for field in ("response", "dependency_report", "object", "log"):
            inputs.sealed(record[field])
        response = Path(record["response"]["path"])
        require(within(response, build / "final") and len(record["command"]) == 2 and
            key(record["command"][0]) == key(report["compiler"]["path"]) and record["command"][1] == "@" + str(response),
            "Compiler command differs from the sealed response")
        before = text(inputs, old["response"]["path"])
        expected = before.replace(str(donor_root), str(build)).replace(donor_root.as_posix(), build.as_posix())
        actual = text(inputs, response)
        require(actual == expected, name + ": compiler response changed beyond path relocation")
        standard = "/std:c++17" if name == "terrain_renderer" else "/std:c++14"
        charset = "/source-charset:utf-8" if name == "world_renderer" else "/source-charset:windows-1252"
        for flag in (standard, charset, "/EHsc", "/W4", "/WX", "/O2", "/MD", "/c"):
            require(flag in actual.splitlines(), name + ": missing required compiler option " + flag)
        require(not re.search(r"\b(?:warning\s+(?:C|LNK)\d+|(?:fatal\s+)?error\s+C\d+)",
            inputs.read(record["log"]["path"]).decode("mbcs", errors="replace"), re.I), "Compiler log contains diagnostics")
        source, actual_deps, visits = dependencies(inputs, record["dependency_report"])
        _, old_deps, _ = dependencies(inputs, old["dependency_report"])
        expected_deps = {key(build / Path(p).relative_to(donor_root)) for p in old_deps}
        if any(Path(p).name.casefold() == ARCHIVE.name.casefold() for p in old_deps):
            envelope = next(r["path"] for r in report["compiler_inputs"] if key(r["original_path"]) == key(ENVELOPE))
            expected_deps.add(key(envelope))
        require(Path(source).name.casefold() == TU_SOURCES[name].casefold() and key(source) in closure and
            actual_deps == expected_deps and actual_deps <= set(closure), "Actual compiler dependency closure differs")
        require(type(record["expected_dependency_count"]) is int and type(record["actual_dependency_count"]) is int and
            record["expected_dependency_count"] == record["actual_dependency_count"] == len(actual_deps),
            "Dependency counts do not mean normalized Source plus Includes")
        union.update(actual_deps)
        for filename in consumers:
            if any(Path(p).name.casefold() == filename.casefold() for p in actual_deps):
                consumers[filename].append(name)
        raw = inputs.read(record["object"]["path"], 128 * 1024 * 1024)
        proof = parser.coff(raw)
        require(proof["machine_hex"] == "0x8664" and Path(record["object"]["path"]).name.casefold() ==
            Path(TU_SOURCES[name]).with_suffix(".obj").name.casefold() and
            key(Path(record["object"]["path"]).parent) == key(response.parent / "obj"), "Actual COFF output path differs")
        defaults = object_directives(raw)
        require(defaults and defaults <= PINNED_LIBS | explicit, "Object requests an unpinned default library")
        objects.append(record["object"])
        results.append(dict(translation_unit=name, dependency_count=len(actual_deps), dependency_visits=visits,
            coff_sections=proof["section_count"], object=record["object"], default_libraries=sorted(defaults)))
    require(union == set(closure) and consumers == {ARCHIVE.name: ["host_main"], ENVELOPE.name: ["host_main"]},
        "The new shared codec was not consumed by the expected actual Host unit")
    require(report["response"] == records[0]["response"] and report["dependency_report"] == records[0]["dependency_report"] and
        report["final_dependency_reports"] == {r["translation_unit"]: r["dependency_report"] for r in records},
        "Top-level dependency aliases differ")
    snapshot = report["link_snapshot"]
    require(snapshot["returncode"] == 0 and type(snapshot["returncode"]) is int and snapshot["response"] == report["link_response"] and
        snapshot["objects_before"] == snapshot["objects_after"] == objects, "Link object snapshot differs")
    for row in snapshot["objects_before"] + snapshot["objects_after"]:
        inputs.sealed(row)
    old_link = text(inputs, baseline["link_response"]["path"])
    expected_link = old_link.replace(str(donor_root), str(build)).replace(donor_root.as_posix(), build.as_posix()) + "/VERBOSE:LIB\n"
    inputs.sealed(report["link_response"])
    require(text(inputs, report["link_response"]["path"]) == expected_link, "Link response changed beyond relocation and library trace")
    linked = re.findall(r'^"([^"\n]+\.obj)"$', expected_link, re.I | re.M)
    require([key(p) for p in linked] == [key(r["path"]) for r in objects], "Link response did not consume the actual five objects")
    return results, consumers


def verify_libraries(inputs, report, build):
    before, after, snapshots = report["implicit_libraries_before"], report["implicit_libraries_after"], report["implicit_libraries"]
    require(before == after and len(before) == len(snapshots) == 8 and
        {r["name"].casefold() for r in before} == PINNED_LIBS and
        {r["name"].casefold() for r in snapshots} == PINNED_LIBS, "Implicit library inventory differs")
    donor_report = LIBRARY_DONOR / "conformance.json"
    donor_ref = inputs.ref(donor_report, dict(path=str(donor_report), sha256=LIBRARY_DONOR_SHA))
    attested = {key(r["path"]): r for r in artifact_references(inputs.document(donor_report))}
    donor_paths = {name: LIBRARY_DONOR / "frozen_inputs/libraries" / sub / filename for name, sub, filename in (
        ("msvcprt.lib", "lib_001", "msvcprt.lib"), ("msvcrt.lib", "lib_002", "msvcrt.lib"),
        ("oldnames.lib", "lib_003", "oldnames.lib"), ("kernel32.lib", "lib_005", "kernel32.Lib"),
        ("vcruntime.lib", "lib_006", "vcruntime.lib"), ("ucrt.lib", "lib_007", "ucrt.lib"),
        ("uuid.lib", "lib_004", "Uuid.Lib"))}
    protected = {key(donor_report): donor_ref}
    for row in inputs.document(donor_report)["configurations"][0]["selected_link_libraries"]:
        protected[key(row["path"])] = inputs.sealed(row)
    by_name = {r["name"].casefold(): r for r in before}
    for row in before + after:
        inputs.sealed(row)
    for row in snapshots:
        name = row["name"].casefold()
        actual, original = inputs.sealed(row), by_name[name]
        require(key(row["path"]) == key(build / "frozen/implicit_libraries" / name) and
            key(row["original_path"]) == key(original["path"]) and
            actual["sha256"] == original["sha256"] and actual["bytes"] == original["bytes"], "Implicit library snapshot differs")
        if name in donor_paths:
            path = donor_paths[name]; old = inputs.sealed(attested[key(path)])
            require(row["materialization"] == "attested_snapshot_hardlink" and
                actual["file_identity"] == old["file_identity"] and actual["mtime_ns"] == old["mtime_ns"] and
                actual["sha256"] == old["sha256"], "Implicit library does not reuse its attested donor")
            protected[key(path)] = old
        else:
            require(name == "bcrypt.lib" and row["materialization"] == "copied_system_input", "Unexpected copied implicit library")
    environment = report["final_environment"]
    expected_environment = dict(INCLUDE=";".join(str(build / "frozen/include_roots" / ("system_%02d" % i)) for i in range(8)),
        LIB=str(build / "frozen/implicit_libraries"), TMP=str(build / "tmp"), TEMP=str(build / "tmp"),
        VSLANG="1033", CL="", _CL_="", LINK="")
    require(environment == expected_environment, "Final compiler/linker environment differs")
    inputs.sealed(report["map"]); inputs.sealed(report["link_log"])
    map_text = inputs.read(report["map"]["path"], 16 * 1024 * 1024).decode("mbcs", errors="replace")
    contributions = set()
    for line in map_text.splitlines():
        tokens = line.split()
        if tokens and re.fullmatch(r"[\w.-]+:[^\s]+\.(?:obj|dll)", tokens[-1], re.I):
            contributions.add(tokens[-1].split(":", 1)[0].casefold().removesuffix(".lib") + ".lib")
    actual_names = sorted(contributions & PINNED_LIBS)
    require(set(actual_names) == IMPLICIT_LIBS and report["actual_implicit_library_namesfrommap"] == actual_names,
        "MAP library contributions differ from the six expected libraries")
    for filename in TU_SOURCES.values():
        require(any(line.split() and line.split()[-1].casefold() == Path(filename).with_suffix(".obj").name.casefold()
            for line in map_text.splitlines()), "MAP lacks an actual Host object contribution")
    log = inputs.read(report["link_log"]["path"], 16 * 1024 * 1024).decode("mbcs", errors="replace")
    require(not re.search(r"\b(?:warning|fatal error|error)\s+LNK\d+", log, re.I), "Link log contains diagnostics")
    normalized = log.casefold().replace("/", "\\")
    for name in IMPLICIT_LIBS:
        path = build / "frozen/implicit_libraries" / name
        require(str(path).casefold().replace("/", "\\") in normalized, "Verbose link did not resolve a pinned implicit library")
    return protected, actual_names


def retry_input(inputs, report):
    compile_failure = inputs.sealed(report["compile_producer"]["failure"])
    attempt = Path(compile_failure["path"]).parent
    require(within(attempt, STAGE) and attempt.parent == STAGE and re.fullmatch(r"[0-9a-f]{20}", attempt.name),
        "Compile attempt escaped its signature directory")
    authority = inputs.document(attempt / "retry_authority.json")
    require(authority["prior_compiler_commands_started"] == 0 and authority["unchanged_user_authorized_scope"] is True,
        "Compile attempt does not have its explicit precompile retry authority")
    row = inputs.sealed(authority["prior_terminal_failure"]); failure = inputs.document(row["path"])
    path = Path(row["path"])
    require(re.fullmatch(r"[0-9a-f]{20}", path.parent.name) and path.parent.parent == STAGE and
        failure["status"] == "FAILED_DO_NOT_REPLAY" and failure["forbidden_access_attempts"] == [] and
        failure["full_engine_goal_complete"] is False, "Retry does not refer to an ordinary terminal failure")
    commands = failure["commands"]
    require(type(commands) is list and len(commands) <= 1, "Retry authority already started compiler commands")
    if commands:
        command = commands[0]
        cwd = Path(command["cwd"])
        require(within(cwd, PROJECT / "Build/UiWindowHost") and
            re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", cwd.name) and Path(command["executable"]).name.casefold() == "cmd.exe" and
            command["command"] == ["cmd.exe", "/d", "/c", str(cwd / "read_build_environment.cmd")],
            "Prior attempt exceeded an environment-only precompile failure")
    return row


def historical_frontends(inputs, report, baseline, seal):
    # These Python frontends are historical context, outside both Host closures.
    closure = {key(row.get("original_path", row.get("original_source", row["path"])))
        for doc in (baseline, report) for group in ("compiler_inputs", "sources") for row in doc[group]}
    require(all(key(PROJECT / name) not in closure for name in FRONTEND_REVISIONS),
        "Historical frontend revision unexpectedly entered a compiler/source closure")
    auth_ref = inputs.ref(FRONTEND_AUTHORIZATION, dict(path=str(FRONTEND_AUTHORIZATION), sha256=FRONTEND_AUTHORIZATION_SHA))
    auth = inputs.document(FRONTEND_AUTHORIZATION)
    runtime = PROJECT / "Build/InteractiveGameRuntime" / FRONTEND_RUNTIME_ID
    require(auth["schema"] == "zerosis.isolated_runtime.authorized_resume.v1" and key(auth["runtime"]) == key(runtime),
        "Historical frontend authorization names another retained runtime")
    request_ref = inputs.sealed(auth["runtime_request"], PROJECT / "evidence/interactive_game" / FRONTEND_RUNTIME_ID / "request.json")
    request = inputs.document(request_ref["path"])
    manifest_path = runtime / "interactive_ui_support/support_manifest.json"
    manifest_ref = inputs.sealed(request["launcher_control_metadata"]["found_value_worker_policy_manifest"], manifest_path)
    manifest = inputs.document(manifest_path)
    launcher_ref = inputs.sealed(request["launcher_control_metadata"]["selected"], runtime / "Play.ps1")
    launcher = text(inputs, launcher_ref["path"])
    quoted_manifest = "'" + str(manifest_path).replace("'", "''") + "'"
    require("--support-manifest " + quoted_manifest in launcher and
        "--support-manifest-sha256 " + manifest_ref["sha256"] in launcher,
        "Historical launcher does not pin its frontend support manifest")
    revisions = []
    for name, (old_bytes, old_sha, new_bytes, new_sha) in FRONTEND_REVISIONS.items():
        old = seal["production_sources"][name]
        require(key(old["path"]) == key(PROJECT / name) and old["bytes"] == old_bytes and old["sha256"] == old_sha,
            "Unexpected historical frontend source revision")
        current = inputs.ref(PROJECT / name, dict(path=str(PROJECT / name), bytes=new_bytes, sha256=new_sha))
        inventory = request["interactive_ui_support_inventory"]["tools"][Path(name).name]
        require(key(inventory["source"]["original_path"]) == key(PROJECT / name) and
            inventory["source"]["bytes"] == new_bytes and inventory["source"]["sha256"] == new_sha,
            "Current frontend is not bound by the historical runtime inventory")
        frozen = inputs.sealed(manifest["tools"][Path(name).name], runtime / "interactive_ui_support/tools" / Path(name).name)
        require(inputs.sealed(inventory["frozen"]) == frozen and frozen["bytes"] == new_bytes and frozen["sha256"] == new_sha,
            "Historical runtime frontend copy differs from the current frontend")
        revisions.append(dict(historical=old, current=current, historical_runtime_copy=frozen,
            outside_both_host_compiler_and_source_closures=True))
    return revisions, dict(authorization=auth_ref, runtime_request=request_ref, support_manifest=manifest_ref,
        launcher=launcher_ref, used_only_as_historical_source_provenance=True)


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--build-id", required=True)
    arguments.add_argument("--output", required=True, type=Path)
    args = arguments.parse_args()
    require(os.name == "nt" and args.build_id == CURRENT_BUILD_ID, "Expected the one reviewed Windows Host build identifier")
    output = args.output
    require(output.is_absolute() and str(output) == os.path.abspath(output) and output.suffix == ".json" and
        within(output.parent, STAGE) and len(output.name) <= 128, "Output must be a new JSON receipt under host_relink")
    ordinary(output.parent, file=False)
    try:
        output.lstat()
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError("The output receipt already exists")
    parser = load_parser()
    # Empty-string conversion may bypass lookup and leave a codec import lazy.
    # Resolve and exercise both directions before installing the read-only hook.
    for encoding in ("utf-8", "utf-8-sig", "mbcs", "ascii", "cp1252"):
        codecs.lookup(encoding)
        b"warm".decode(encoding)
        "warm".encode(encoding)
    reads, denied = install_guard(output)
    inputs = Inputs(reads)
    verifier = inputs.ref(Path(__file__).absolute())
    inputs.ref(HELPER, dict(path=str(HELPER), sha256=HELPER_SHA))
    build = PROJECT / "Build/UiWindowHost" / args.build_id
    report_path = PROJECT / "evidence/ui_window_host" / args.build_id / "build_result.json"
    report_ref = inputs.ref(report_path, dict(path=str(report_path), sha256=CURRENT_REPORT_SHA))
    report = inputs.document(report_path)
    baseline_ref = inputs.sealed(report["baseline_build"], DONOR_REPORT)
    component_ref = inputs.sealed(report["native_save_component"], COMPONENT)
    builder_ref = inputs.sealed(report["relink_builder"], BUILDER)
    require((baseline_ref["sha256"], component_ref["sha256"], builder_ref["sha256"]) ==
        (DONOR_SHA, COMPONENT_SHA, BUILDER_SHA), "Build lineage is not the reviewed frozen lineage")
    baseline, component = inputs.document(DONOR_REPORT), inputs.document(COMPONENT)
    require(report["schema"] == baseline["schema"] == "zerosis.ui_window_host_build.v1" and
        report["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and report["build_id"] == args.build_id and
        baseline["build_id"] == DONOR_ID, "Unexpected Host build result")
    for name in ("compiler", "linker", "dumpbin"):
        require(inputs.sealed(report[name]) == inputs.sealed(baseline[name]), "Toolchain executable seal differs")
    for name in ("toolchain", "definitions", "system_include_roots"):
        require(report[name] == baseline[name], "Host compilation policy changed")
    for name in ("source_inputs_unchanged", "provider_inputs_unchanged"):
        require(report[name] is True, "Builder reports input drift")
    for name in ("host_runtime_executed", "gamecore_loaded", "sdk_linked", "mods_updated", "stage_updated",
                 "default_promoted", "full_engine_goal_complete"):
        require(report[name] is False, "Builder scope exceeds a private static Host link")
    require(report["forbidden_access_attempts"] == [], "Builder reports forbidden accesses")
    current_rows = [*report["compiler_inputs"], *report["sources"], *report["libraries"], *report["build_tools"],
        *report["provider_reports"].values(), report["ui_assets"], *report["current_source_inputs"],
        *report["protected_artifacts"], *report["implicit_libraries_before"], *report["implicit_libraries_after"],
        *report["implicit_libraries"], *(report[n] for n in ("compiler", "linker", "dumpbin", "executable", "map", "link_response", "link_log"))]
    for record in report["final_compilation"]["translation_units"]:
        current_rows.extend(record[name] for name in ("response", "log", "dependency_report", "object"))
    current_rows.extend(report["compile_producer"][name] for name in ("source_gzip", "failure"))
    current_rows.extend(report["link_continuation"][name] for name in
        ("tool", "authority", "failed_link_response", "failed_link_log", "environment_response"))
    for row in current_rows:
        require(all(k in row for k in ("path", "bytes", "sha256", "file_identity", "mtime_ns")) and
            type(row["bytes"]) is int and row["bytes"] >= 0 and type(row["mtime_ns"]) is int and
            type(row["file_identity"]) is list and len(row["file_identity"]) == 2 and
            all(type(n) is int for n in row["file_identity"]), "Current artifact lacks its complete identity seal")
    originals, donors, materialized = verify_sources(inputs, report, baseline, build)
    require(inputs.ref(ARCHIVE)["sha256"] == ARCHIVE_SHA and inputs.ref(ENVELOPE)["sha256"] == ENVELOPE_SHA,
        "Current native-save codec source differs")
    compilation, consumers = verify_compilation(inputs, parser, report, baseline, build)
    library_protected, library_names = verify_libraries(inputs, report, build)

    retry_ref = retry_input(inputs, report)
    signature = hashlib.sha256((DONOR_SHA + COMPONENT_SHA + BUILDER_SHA + (retry_ref["sha256"] if retry_ref else "")).encode("ascii")).hexdigest()[:20]
    require(args.build_id.endswith("_" + signature[:12]), "Build identifier is not bound to its source fingerprint")
    attempt = STAGE / signature
    run_path = attempt / "run.json"
    run_ref, run = inputs.ref(run_path, dict(path=str(run_path), sha256=CURRENT_RUN_SHA)), inputs.document(run_path)
    require(run["schema"] == "zerosis.native_save.host_relink_run.v1" and
        run["status"] == "PASS_CURRENT_NATIVE_SAVE_HOST_LINK_ONLY" and run["build_id"] == args.build_id and
        inputs.sealed(run["build_result"]) == report_ref and run["actual_objects"] == report["link_snapshot"]["objects_before"] and
        run["link_snapshot"] == report["link_snapshot"], "Actual build transcript does not bind this result and objects")
    require(run["protected_unchanged"] is True and run["current_inputs_unchanged"] is True and
        run["forbidden_access_attempts"] == [], "Actual build transcript reports drift or forbidden accesses")
    for name in ("host_runtime_executed", "gamecore_loaded", "hwnd_created", "default_promoted", "full_engine_goal_complete"):
        require(run[name] is False, "Actual build transcript exceeds the static scope")
    continuation = report["link_continuation"]
    continuation_ref = inputs.sealed(continuation["tool"], CONTINUATION)
    require(continuation_ref["sha256"] == CONTINUATION_SHA and run["link_continuation"] == continuation,
        "Link continuation is not the reviewed source and transcript")
    retry_directory = attempt / "link_retry01"
    producer = report["compile_producer"]
    inputs.sealed(producer["source_gzip"], retry_directory / "compile_producer.py.gz")
    require(producer["source_sha256"] == BUILDER_SHA and
        gzip.decompress(inputs.read(producer["source_gzip"]["path"], 64 * 1024)) == inputs.read(BUILDER, 64 * 1024),
        "Preserved compile-producer bytes differ from the actual sealed producer")
    failed_ref = inputs.sealed(producer["failure"], attempt / "failure.json")
    failed = inputs.document(failed_ref["path"])
    require(failed["status"] == "FAILED_DO_NOT_REPLAY" and failed["error_type"] == "AssertionError" and
        "uuid.lib" in failed["error"].casefold() and failed["forbidden_access_attempts"] == [] and
        failed["full_engine_goal_complete"] is False, "Continuation does not follow the terminal UUID link failure")
    failed_response = inputs.sealed(continuation["failed_link_response"], build / "final/link.rsp")
    failed_log = inputs.sealed(continuation["failed_link_log"], attempt / "link.log")
    require(failed_response["bytes"] == report["link_response"]["bytes"] and
        failed_response["sha256"] == report["link_response"]["sha256"] and
        key(report["link_response"]["path"]) == key(build / "final/link_retry01.rsp"),
        "Continuation did not preserve and reuse the failed link response bytes")
    failed_log_text = inputs.read(failed_log["path"]).decode("mbcs", errors="replace").casefold()
    require("lnk1104" in failed_log_text and "uuid.lib" in failed_log_text, "Original link failure log differs")
    expected_commands = [dict(executable="cmd.exe", command=["cmd.exe", "/d", "/c", str(build / "read_build_environment.cmd")],
        cwd=str(build), returncode=0)]
    for record in report["final_compilation"]["translation_units"]:
        expected_commands.append(dict(executable=record["command"][0], command=record["command"],
            cwd=str(Path(record["response"]["path"]).parent), returncode=0))
        require(inputs.document(attempt / ("compiled_" + record["translation_unit"] + ".json")) == record,
            "Per-unit compile receipt differs")
    expected_commands.append(dict(executable=report["linker"]["path"], command=[report["linker"]["path"], "@" + failed_response["path"]],
        cwd=str(build / "final"), returncode=1104))
    require(failed["commands"] == continuation["commands_before"] == expected_commands and len(expected_commands) == 7,
        "Original compile and failed-link commands differ")
    expected_commands.extend((dict(executable="cmd.exe", command=["cmd.exe", "/d", "/c", str(retry_directory / "read_build_environment.cmd")],
        cwd=str(retry_directory), returncode=0),
        dict(executable=report["linker"]["path"], command=[report["linker"]["path"], "@" + report["link_response"]["path"]],
        cwd=str(Path(report["link_response"]["path"]).parent), returncode=0),
        dict(executable=report["dumpbin"]["path"], command=[report["dumpbin"]["path"], "/dependents", report["executable"]["path"]],
        cwd=str(Path(report["executable"]["path"]).parent), returncode=0)))
    require(run["commands"] == expected_commands and continuation["commands_after"] == expected_commands[7:] and
        len(expected_commands) == 10, "Actual child command allowlist differs or a compiler was rerun")
    environment_script = text(inputs, build / "read_build_environment.cmd")
    require(environment_script == '@echo off\ncall "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat" >nul\nif errorlevel 1 exit /b 1\nset\n',
        "Toolchain environment command differs")
    inputs.sealed(continuation["environment_response"], retry_directory / "read_build_environment.cmd")
    require(text(inputs, continuation["environment_response"]["path"]) == environment_script,
        "Link-only environment command changed")
    inputs.sealed(continuation["authority"], retry_directory / "authority.json")
    authority = inputs.document(continuation["authority"]["path"])
    uuid_row = next(r for r in report["implicit_libraries"] if r["name"] == "uuid.lib")
    require(authority["schema"] == "zerosis.native_save.link_continuation.v1" and
        inputs.sealed(authority["failure"]) == failed_ref and inputs.sealed(authority["baseline"]) == baseline_ref and
        authority["objects_before"] == report["link_snapshot"]["objects_before"] and
        inputs.sealed(authority["failed_link_response"]) == failed_response and inputs.sealed(authority["failed_link_log"]) == failed_log and
        authority["added_implicit_library"] == next(r for r in report["implicit_libraries_before"] if r["name"] == "uuid.lib") and
        inputs.sealed(authority["uuid_donor"])["file_identity"] == uuid_row["file_identity"] and
        continuation["added_implicit_libraries"] == [uuid_row] and authority["recompile_allowed"] is False and
        authority["host_gamecore_hwnd_execution_allowed"] is False and authority["full_engine_goal_complete"] is False,
        "Continuation exceeded the explicit UUID-only, link-only authority")
    started = inputs.document(attempt / "started.json")
    require(started["build_id"] == args.build_id and started["signature"] == signature and
        inputs.sealed(started["baseline_build"]) == baseline_ref and inputs.sealed(started["component"]) == component_ref and
        started["full_engine_goal_complete"] is False, "Attempt preflight does not bind the reviewed lineage")
    inputs.sealed(started["prior_cleanup_audit"])
    if retry_ref:
        authority = inputs.document(attempt / "retry_authority.json")
        require(inputs.sealed(authority["prior_terminal_failure"]) == retry_ref and
            authority["prior_compiler_commands_started"] == 0 and authority["unchanged_user_authorized_scope"] is True,
            "Distinct retry authority differs")

    post_ref = inputs.ref(POST, dict(path=str(POST), sha256=POST_SHA))
    post = inputs.document(POST)
    expected_protected = {}
    for group in ("protected_files", "source_contract_inputs", "source_and_proof_files"):
        for row in post[group]:
            expected_protected[key(row["path"])] = inputs.sealed(row)
    for revision in post["component_input_revisions"]:
        row = revision["after"]; expected_protected[key(row["path"])] = inputs.sealed(row)
    for row in (baseline_ref, component_ref, builder_ref, post_ref, *donors.values(), *originals.values(), *library_protected.values()):
        expected_protected[key(row["path"])] = row
    for row in (continuation_ref, failed_ref, inputs.ref(attempt / "started.json")):
        expected_protected[key(row["path"])] = row
    storage_path = STAGE / "storage_before.json"
    expected_protected[key(storage_path)] = inputs.ref(storage_path)
    storage = inputs.document(storage_path)
    require(storage["errors"] == 0 and storage["disposable_allocation_exceeding_10_GiB_established"] is False,
        "Storage preflight reports an unresolved retention limit")
    protected = rows_by_path(report["protected_artifacts"])
    require(set(protected) == set(expected_protected), "Protected-artifact coverage differs")
    for path, row in protected.items():
        require(inputs.sealed(row) == expected_protected[path], "Protected artifact identity changed")

    inputs.ref(PREVIOUS_ATTESTATION, dict(path=str(PREVIOUS_ATTESTATION), sha256=PREVIOUS_ATTESTATION_SHA))
    prior = inputs.document(PREVIOUS_ATTESTATION)
    inputs.sealed(prior["verifier"], HELPER)
    seal = inputs.document(inputs.sealed(prior["source_seal"])["path"])
    frontend_revisions, frontend_provenance = historical_frontends(inputs, report, baseline, seal)
    revised_paths = {key(PROJECT / name) for name in FRONTEND_REVISIONS}
    for group in ("production_sources", "new_assets_and_tests"):
        for row in seal[group].values():
            if key(row["path"]) not in revised_paths:
                inputs.sealed(row)
    header_ref = inputs.ref(GENERATED, dict(path=str(GENERATED), sha256=GENERATED_SHA))
    frozen_header = next(r for r in report["compiler_inputs"] if key(r["original_path"]) == key(GENERATED))
    require(inputs.sealed(frozen_header)["sha256"] == header_ref["sha256"], "Generated header snapshot differs")
    arrays, order = parser.parse_catalog(inputs.read(GENERATED, 32 * 1024 * 1024))
    executable = inputs.sealed(report["executable"])
    require(key(executable["path"]) == key(build / "final/ZeroSisHost_x64.exe"), "Host executable escaped its private build")
    pe = parser.PE(inputs.read(executable["path"], 32 * 1024 * 1024))
    imports = pe.imports()
    require(len(imports) == len(set(imports)) and set(imports) == set(prior["pe"]["imports"]) ==
        {name.casefold() for name in report["imports"]["dependencies"]}, "Actual PE import allowlist differs")
    inputs.sealed(report["imports"]["log"])
    logged_imports = re.findall(r"^\s+([\w.-]+\.dll)\s*$", text(inputs, report["imports"]["log"]["path"]), re.M | re.I)
    require([v.casefold() for v in logged_imports] == [v.casefold() for v in report["imports"]["dependencies"]],
        "Dumpbin transcript differs from the actual PE imports")
    actual_catalog = pe.catalog(arrays, order)
    catalog_rows = [{k: row[k] for k in ("name", "index", "bytes", "sha256")} for row in actual_catalog["exact_payloads"]]
    previous_rows = [{k: row[k] for k in ("name", "index", "bytes", "sha256")} for row in prior["catalog"]["exact_payloads"]]
    require(len(catalog_rows) == 67 and catalog_rows == previous_rows, "Actual 67-payload catalog differs from the attested source catalog")
    require(report["executable"]["pe"]["architecture"] == "x64" and report["executable"]["pe"]["pe_format"] == "PE32+",
        "Builder PE observations differ")
    inputs.ref(SOURCE_PROOF, dict(path=str(SOURCE_PROOF), sha256=SOURCE_PROOF_SHA))
    proof = inputs.document(SOURCE_PROOF)
    static = proof["static_production_source_proof"]
    require(component["status"] == "PASS_PORTABLE_NATIVE_SAVE_ENVELOPE_COMPONENT" and
        component["native_v1_schema_changed"] is False and proof["save_schema_changed"] is False and
        proof["production_cng_changed"] is False and static["codec_reverse_substitutions_match_original_bytes"] is True and
        static["production_wrapper_delegates_to_shared_codec"] is True and
        all(row["before_after_identical"] is True for row in static["platform_regions"].values()),
        "Existing source proof no longer establishes the unchanged native V1 contract")
    require(proof["actual_native_roundtrip_exact"] is True and proof["sdk_restore_verified"] is False and
        proof["retail_import_implemented"] is False and proof["full_engine_goal_complete"] is False,
        "Existing component proof exceeds its codec-only scope")
    inputs.stable()
    require(not denied, "Verifier attempted a forbidden operation")
    result = dict(schema="zerosis.native_save.relinked_host_attestation.v1", status="PASS_RELINKED_NATIVE_HOST_STATIC_ATTESTATION",
        utc=datetime.now(timezone.utc).isoformat(), build_id=args.build_id, verifier=verifier, build_result=report_ref,
        actual_build_run=run_ref, previous_attestation=inputs.rows[key(PREVIOUS_ATTESTATION)],
        historical_frontend_source_revisions=frontend_revisions, historical_frontend_source_provenance=frontend_provenance,
        source_proof=inputs.rows[key(SOURCE_PROOF)], executable=executable,
        verified_unique_inputs=len(inputs.rows), compiler_dependency_count=545, current_source_count=len(originals),
        donor_snapshot_count=len(donors), protected_artifact_count=len(protected), source_manifest_count=81,
        actual_compile_commands=5, exact_child_commands=10, failed_link_commands=1, successful_link_commands=1,
        link_only_continuation_verified=True, compile_producer_gzip_verified=True,
        actual_coff_objects=compilation, codec_consumers=consumers,
        implicit_libraries_pinned=8, implicit_library_names_from_map=library_names,
        pe=dict(machine_hex="0x8664", format="PE32+", large_address_aware=True, is_dll=False,
            section_count=len(pe.sections), imports=imports),
        catalog=dict(entry_count=67, table_rva=actual_catalog["table_rva"], table_section=actual_catalog["table_section"],
            stride=24, total_payload_bytes=sum(row["bytes"] for row in catalog_rows),
            ordered_payload_manifest_sha256=hashlib.sha256(json.dumps(catalog_rows, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()),
        current_host_source_closure_matches_linked_candidate=True, generated_catalog_regenerated=False,
        current_native_save_codec_linked=True, native_v1_schema_changed=False, production_cng_source_changed=False,
        protected_inputs_unchanged=True, input_files_unchanged=True, previous_native_v1_roundtrip_verified=True,
        candidate_native_code_loaded_or_executed=False, sdk_executed=False, gamecore_loaded=False, window_created=False,
        ui_acceptance_verified=False,
        game_process_queries=0, network_used=False, retail_user_state_accessed=False, sdk_runtime_rebuilt=False,
        retail_import_entrypoint_implemented=False, new_host_native_save_runtime_verified=False, sdk_restore_verified=False,
        native_restore_approved=False, default_promoted=False, full_engine_goal_complete=False, forbidden_access_attempts=denied)
    encoded = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    require(len(encoded) <= 24 * 1024, "Summary receipt exceeded its bounded size")
    ordinary(output.parent, file=False)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
    print(json.dumps(dict(status=result["status"], build_id=args.build_id, output=str(output), bytes=len(encoded.encode("ascii")),
        sha256=hashlib.sha256(encoded.encode("ascii")).hexdigest())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
