"""Statically attest the one current hover-repaint Host link.

Read sealed source, response, COFF, dependency and PE files only. The sole
write is a fresh attestation.json beside the explicitly pinned successful run.
No compiler, linked image, SDK, DLL, window, process query or network is used.
"""
from __future__ import annotations

import argparse
import ast
import codecs
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import types

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
BASE_ID = "20261024T055841Z_974a5be57533"
BASE_ROOT = PROJECT / "Build/UiWindowHost" / BASE_ID
BASE_SHA = "6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302"
AUDIT_SHA = "80f806d06fc519005579ae421ebfcbbe8377173d2a11d4057f674e0f60e170de"
REQUIREMENTS_SHA = "a642bc220023884a1fe26aad9055a9672c043fa926614f747434c01dd69e4fde"
CLEANUP_SHA = "e408298ba15ba4e5559753db1c8d1a431fabe26f0573a830aed4d610c7be67fc"
BUILDER_SHA = "b1a18dcfedddeb851a0c1d236725d47a3a6dece9657e0d290af7627a64190043"
PARSER = PROJECT / "evidence/goody_hut/owned_fonts/verify_candidate.py"
PARSER_SHA = "723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f"
GENERATED = PROJECT / "Source/Host/UiPopupAssets.generated.h"
GENERATED_SHA = "333cf40c942e2545c83372084ed276e2aec11ab9fd7cbf4744f8c0c4e7c48da9"
CATALOG_SHA = "db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c"
MARKER = b"NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|"
TUS = ("host_main", "window", "renderer", "world_renderer", "terrain_renderer")
STEMS = ("HostMain", "BitmapWindow", "BitmapRenderer", "WorldViewRenderer", "WorldTerrainRenderer")
COUNTS = (466, 266, 270, 279, 301)
LIBRARIES = {"msvcrt.lib", "msvcprt.lib", "vcruntime.lib", "oldnames.lib", "bcrypt.lib",
             "kernel32.lib", "ucrt.lib", "uuid.lib"}
MAP_LIBRARIES = LIBRARIES - {"oldnames.lib", "uuid.lib"}
SOURCES = {
    "UiPanelRepaint.h": (921, "15fcd95d0f076bb085a2ab58862c21b42834ef33452edfa2875c0759e8f4ec37"),
    "InteractiveUiSession.h": (48380, "b94d8817b64ad2afc596d78c76a64e9382aef30eafdd1da68f9c04ad716f4bbf"),
    "InteractiveGameSession.h": (112647, "6c8476c36db750da6a4af64bcf02cf01e913dea6fa02e72a15307dc92f73fc65"),
    "InteractiveGameLoop.h": (258117, "23b35a033f1d0ab9b93c4f5a9aaa2df2d73411d6a4d16742397cdd2f2aa5a5d8"),
}
METADATA = {
    "evidence/save_menu/20261013_original_screen/current_progress.json": "4663a1c628911d8a530d04a620bc0a849713ece41c4cc1b8c12622fe32ee0441",
    "docs/ORIGINAL_WORLD_HUD.md": "6b4e39786f6916ca2179a07e4f6780d8f25e59417502662ebb498be23c3a4bb0",
    "evidence/original_world_hud/pair_preparation/execution/screen_verification_deferred.json": "8751696cbd8c3728f5a465b9556ad0e0e71a7418d89bc20cfa036da698ac1523",
}
GROUPS = ("compiler_inputs", "sources", "provider_inputs", "system_libraries", "build_tools", "implicit_libraries")
RUNTIME = PROJECT / "Build/InteractiveGameRuntime/20261024T070230Z_cbbd79f1cbb6"
READ_ROOTS = (PROJECT, Path(r"C:\Program Files\Microsoft Visual Studio"),
              Path(r"C:\Program Files (x86)\Windows Kits\10"), Path(r"C:\Windows\System32\cmd.exe"))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def ordinary(path, file=True):
    path = Path(path)
    parts = {part.casefold() for part in path.parts}
    require(path.is_absolute() and str(path) == os.path.abspath(path) and
            not parts & {"my games", "mods", "saves", ".codex"} and
            not {"steamapps", "common"} <= parts and any(within(path, root) for root in READ_ROOTS),
            "Noncanonical or out-of-scope file path")
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not info.st_file_attributes & 0x400, "Reparse path")
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode), "Unexpected file kind")
    return info


def content(row):
    require(type(row) is dict and type(row.get("path")) is str and type(row.get("bytes")) is int and
            0 <= row["bytes"] <= 128 * 1024 * 1024 and type(row.get("sha256")) is str and
            re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "Malformed bounded artifact")
    return key(row["path"]), row["bytes"], row["sha256"]


def same(left, right):
    return content(left) == content(right)


def same_bytes(left, right):
    return content(left)[1:] == content(right)[1:]


def indexed(rows):
    require(type(rows) is list, "Artifact inventory is not a list")
    result = {}
    for row in rows:
        name = content(row)[0]
        require(name not in result, "Duplicate artifact path")
        result[name] = row
    return result


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, "Duplicate JSON key")
        result[name] = value
    return result


def install_guard(output):
    reads, denied, published = set(), [], False

    def audit(event, args):
        nonlocal published
        if event == "open":
            require(args and isinstance(args[0], (str, bytes, os.PathLike)), "Descriptor open denied")
            name, mode, flags = key(args[0]), args[1], args[2]
            writing = isinstance(mode, str) and any(c in mode for c in "wax+") or isinstance(flags, int) and bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            allowed = (name == key(output) and not published and isinstance(flags, int) and
                       flags & os.O_EXCL and flags & os.O_CREAT) if writing else name in reads
            if not allowed:
                denied.append(event)
                raise RuntimeError("Unregistered attestor file access")
            if writing:
                published = True
        if event.startswith(("subprocess.", "os.exec", "os.spawn", "ctypes.", "socket.", "urllib.", "http.client.")) or event in (
            "os.system", "os.startfile", "os.startfile/2", "os.posix_spawn", "os.posix_spawnp", "os.fork", "os.forkpty",
            "os.kill", "os.killpg", "os.listdir", "os.scandir", "os.chdir", "os.remove", "os.rmdir", "os.rename",
            "os.mkdir", "os.link", "os.symlink", "os.chmod", "os.truncate", "os.utime"):
            denied.append(event)
            raise RuntimeError("Static attestor forbids " + event)

    sys.addaudithook(audit)
    return reads, denied


class Files:
    def __init__(self, reads):
        self.reads, self.rows, self.physical = reads, {}, {}

    @staticmethod
    def snapshot(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes

    def ref(self, path, expected=None, rehash=False):
        path = Path(path)
        before = ordinary(path)
        signature = self.snapshot(before)
        require(before.st_size <= 128 * 1024 * 1024, "File exceeds hash limit")
        self.reads.add(key(path))
        if not rehash and signature in self.physical:
            row = dict(self.physical[signature], path=str(path))
        else:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            require(signature == self.snapshot(ordinary(path)), "File changed during hashing")
            row = dict(path=str(path), bytes=before.st_size, sha256=digest,
                       file_identity=[before.st_dev, before.st_ino], mtime_ns=before.st_mtime_ns,
                       file_attributes=before.st_file_attributes)
            self.physical[signature] = row
        if expected is not None:
            require(same(row, expected), "Artifact content differs: " + str(path))
            for name in ("file_identity", "mtime_ns", "file_attributes"):
                require(name not in expected or type(expected[name]) is type(row[name]) and expected[name] == row[name],
                        "Artifact metadata differs: " + str(path))
        require(key(path) not in self.rows or self.rows[key(path)] == row, "Artifact changed between reads")
        self.rows[key(path)] = row
        return row

    def sealed(self, row):
        content(row)
        return self.ref(row["path"], row)

    def pin(self, path, sha):
        row = self.ref(path)
        require(row["sha256"] == sha, "Fixed source/proof digest differs: " + str(path))
        return row

    def read(self, path, maximum=4 * 1024 * 1024):
        row = self.ref(path)
        require(row["bytes"] <= maximum, "File exceeds read limit")
        raw = Path(path).read_bytes()
        require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], "File changed while reading")
        self.ref(path, row)
        return raw

    def document(self, path):
        return json.loads(self.read(path).decode("utf-8-sig"), object_pairs_hook=unique_object,
                          parse_constant=lambda value: require(False, "Nonfinite JSON number"))

    def stable(self):
        for row in list(self.rows.values()):
            self.ref(row["path"], row)
        for row in list(self.physical.values()):
            self.ref(row["path"], row, rehash=True)


def text(files, path, maximum=8 * 1024 * 1024):
    return files.read(path, maximum).decode("utf-8-sig").replace("\r\n", "\n")


def frozen_rows(report):
    result = {}
    rows = [row for group in GROUPS for row in report[group]]
    rows += [*report["provider_reports"].values(), report["shared_lua_build"], report["ui_assets"]]
    source_paths = set(indexed(report["sources"]))
    for row in rows:
        name = content(row)[0]
        if "original_path" not in row:
            require(name in source_paths and type(row.get("original_source")) is str and
                    Path(row["original_source"]).suffix.casefold() == ".lua", "Unapproved original-source alias")
            row = dict(row, original_path=row["original_source"])
        require(type(row["original_path"]) is str and ("original_source" not in row or
                key(row["original_source"]) == key(row["original_path"])), "Frozen original aliases differ")
        if name in result:
            old = result[name]
            require(same(old, row) and key(old["original_path"]) == key(row["original_path"]) and
                    all(old.get(field) == row.get(field) for field in
                        ("file_identity", "mtime_ns", "file_attributes", "materialization")), "Conflicting frozen alias")
        else:
            result[name] = row
    return result


def dependencies(files, row):
    data = files.document(files.sealed(row)["path"])["Data"]
    require(type(data["Source"]) is str and type(data["Includes"]) is list and len(data["Includes"]) < 2000 and
            all(type(item) is str for item in data["Includes"]) and data["ProvidedModule"] == "" and
            data["ImportedModules"] == data["ImportedHeaderUnits"] == [], "Unexpected compiler dependency schema")
    paths = [data["Source"], *data["Includes"]]
    return data["Source"], {key(path) for path in paths}, len(paths)


def defaults(raw):
    directives = []
    for index in range(struct.unpack_from("<H", raw, 2)[0]):
        at = 20 + index * 40
        if raw[at:at + 8] == b".drectve":
            length, offset = struct.unpack_from("<II", raw, at + 16)
            directives.append(raw[offset:offset + length].decode("ascii"))
    require(directives, "COFF object lacks linker directives")
    matches = re.findall(r'/DEFAULTLIB:(?:"([^"\s]+)"|([^\s]+))', " ".join(directives), re.I)
    return sorted({(quoted or plain).casefold().removesuffix(".lib") + ".lib" for quoted, plain in matches})


def verify_inputs(files, run, started, report, base, audit, requirements, build):
    changed = {key(PROJECT / "Source/Host" / name): (size, sha) for name, (size, sha) in SOURCES.items()}
    added = key(PROJECT / "Source/Host/UiPanelRepaint.h")
    production = indexed(audit["production_sources"])
    require(set(production) == set(changed) and all(content(production[path])[1:] == value for path, value in changed.items()),
            "Component production input contract differs")
    old_current, current = indexed(base["current_source_inputs"]), indexed(report["current_source_inputs"])
    require(len(old_current) == 592 and len(current) == 593 and set(current) == set(old_current) | {added} and
            indexed(run["current_inputs"]) == indexed(started["current_inputs"]) == current,
            "Current input manifest is not exact parent592 plus one header")
    for path, row in current.items():
        actual = files.sealed(row)
        expected = production[path] if path in changed else old_current[path]
        require(same(actual, expected), "Unapproved current input change")
    revisions = []
    for item in requirements["baseline_sources"][:3]:
        before, backup = item["before"], item["backup"]
        path = key(before["path"])
        require(path in changed and path != added and same(before, old_current[path]), "Source before does not bind the parent")
        files.sealed(backup)
        require(within(backup["path"], STAGE / "source_backups") and before["bytes"] <= 1024 * 1024,
                "Source backup escaped its fixed scope")
        with gzip.open(backup["path"], "rb") as stream:
            raw = stream.read(before["bytes"] + 1)
        require((len(raw), hashlib.sha256(raw).hexdigest()) == content(before)[1:], "Source backup roundtrip differs")
        annotation = dict(original_path=before["path"], bytes=before["bytes"], sha256=before["sha256"])
        revisions.append(dict(before=annotation, backup=backup, after=current[path]))
    require({key(row["before"]["original_path"]) for row in revisions} == set(changed) - {added} and
            report["source_revision_provenance"] == started["source_revisions"] == revisions and
            same(started["added_source"], current[added]), "Exact three source revisions differ")
    require(indexed(report["sources_changed_from_baseline"]) == {path: current[path] for path in sorted(set(changed) - {added})} and
            report["new_source_inputs"] == [current[added]], "Declared source changes differ")
    previous, frozen = frozen_rows(base), frozen_rows(report)
    relocate = lambda path: build / Path(path).relative_to(BASE_ROOT)
    require(len(previous) == 592 and len(frozen) == 593 and indexed(run["frozen_donors"]) == indexed(started["frozen_donors"]) and
            set(indexed(run["frozen_donors"])) == set(previous), "Donor manifest differs")
    for path, row in indexed(run["frozen_donors"]).items():
        files.sealed(row)
        require(same(row, previous[path]) and all(row[field] == previous[path][field] for field in
                ("file_identity", "mtime_ns", "file_attributes")), "Parent frozen donor differs")
    new_header = build / "frozen/include_roots/project/Source/Host/UiPanelRepaint.h"
    require(set(frozen) == {key(relocate(row["path"])) for row in previous.values()} | {key(new_header)},
            "Frozen paths changed beyond root relocation plus the new header")
    materialized = indexed(run["materialized"])
    require(set(materialized) == set(frozen), "Actual materialization inventory differs")
    implicit = indexed(base["implicit_libraries"])
    require(len(implicit) == 8 and {row["name"].casefold() for row in implicit.values()} == LIBRARIES,
            "Parent implicit library inventory differs")
    missing, copies, links, copied_bytes = set(), 0, 0, 0
    origins = set()
    old_by_target = {key(relocate(row["path"])): row for row in previous.values()}
    for path, row in frozen.items():
        actual = files.sealed(row)
        material = materialized[path]
        material_origin = material.get("original_path", material.get("original_source"))
        require(type(material_origin) is str and
                ("original_source" not in material or key(material["original_source"]) == key(material_origin)),
                "Materialization original aliases differ")
        require(same(actual, material) and key(row["original_path"]) == key(material_origin) and
                all(row.get(field) == material.get(field) for field in ("file_identity", "mtime_ns", "file_attributes", "materialization")),
                "Materialization does not bind the actual frozen row")
        require(within(row["path"], build / "frozen"), "Frozen input escaped the private snapshot")
        origin = key(row["original_path"])
        origins.add(origin)
        old = old_by_target.get(path)
        require(old is not None or path == key(new_header) and origin == added, "Unexpected new frozen origin")
        if old is not None:
            require(origin == key(old["original_path"]), "Frozen source identity changed")
            files.sealed(old)
        original = current.get(origin)
        if original is None:
            require(old is not None and key(old["path"]) in implicit and same(old, implicit[key(old["path"])]) and
                    row.get("name") == old.get("name") and same_bytes(row, old), "Unapproved missing current original")
            missing.add(key(old["path"]))
        else:
            require(same_bytes(actual, original), "Frozen bytes differ from the actual current input")
        if origin in changed:
            copies += 1
            copied_bytes += row["bytes"]
            require(row["materialization"] == "owned_changed_source_copy" and "reused_from_path" not in material and
                    actual["file_identity"] != original["file_identity"] and actual["file_attributes"] & 1 and
                    ordinary(row["path"]).st_nlink == 1 and
                    (old is None or actual["file_identity"] != old["file_identity"]), "Changed source is not a private readonly copy")
        else:
            links += 1
            require(row["materialization"] == "attested_snapshot_hardlink" and same_bytes(actual, old) and
                    key(material["reused_from_path"]) == key(old["path"]) and
                    all(actual[field] == old[field] for field in ("file_identity", "mtime_ns", "file_attributes")),
                    "Unchanged frozen input is not the exact donor hardlink")
    require(missing == set(implicit) and (copies, links, copied_bytes) == (4, 589, 420065), "Frozen scope/counts differ")
    require(set(old_current) - {key(row["original_path"]) for row in previous.values()} == set(current) - origins and
            len(set(current) - origins) == 8, "Current extra inputs were confused with the eight implicit libraries")
    for group in GROUPS:
        expected = [key(relocate(row["path"])) for row in base[group]]
        if group in ("compiler_inputs", "sources"):
            expected.append(key(new_header))
        require([key(row["path"]) for row in report[group]] == expected, "Ordered frozen group differs: " + group)
    require(len(report["compiler_inputs"]) == report["compiler_dependency_count"] == 550 and len(report["sources"]) == 86 and
            report["libraries"] == report["provider_inputs"] + report["system_libraries"], "Compiler/source/library aliases differ")
    for group in ("provider_reports",):
        require(set(report[group]) == set(base[group]) and all(key(report[group][name]["path"]) == key(relocate(row["path"]))
                for name, row in base[group].items()), "Provider report aliases differ")
    for field in ("shared_lua_build", "ui_assets"):
        require(key(report[field]["path"]) == key(relocate(base[field]["path"])), "Retained payload/provider alias differs")
    require(report["frozen_input_reuse"] == dict(hardlinked_files=589, copied_files=4, copied_source_bytes=420065,
            donor_content_and_metadata_preserved=True), "Frozen reuse summary differs")
    return current, frozen, revisions


def verify_compilation(files, parser, run, report, base, build, stage, frozen):
    relocate = lambda path: build / Path(path).relative_to(BASE_ROOT)
    rewrite = lambda value: value.replace(str(BASE_ROOT), str(build)).replace(BASE_ROOT.as_posix(), build.as_posix())
    records, old_records = report["final_compilation"]["translation_units"], base["final_compilation"]["translation_units"]
    require(tuple(row["translation_unit"] for row in records) == tuple(row["translation_unit"] for row in old_records) == TUS and
            run["compilation"] == records and run["actual_dependency_counts"] == list(COUNTS), "Five compilation records differ")
    closure = set(indexed(report["compiler_inputs"]))
    added = key(build / "frozen/include_roots/project/Source/Host/UiPanelRepaint.h")
    explicit = {Path(row["path"]).name.casefold() for row in report["libraries"]}
    union, old_union, objects, summaries = set(), set(), [], []
    for index, (row, old) in enumerate(zip(records, old_records)):
        unit, stem = TUS[index], STEMS[index]
        require(type(row["returncode"]) is int and row["returncode"] == 0, unit + ": compiler did not succeed")
        for field in ("response", "object", "dependency_report", "log"):
            files.sealed(row[field])
        files.sealed(old["response"])
        response = Path(row["response"]["path"])
        actual = text(files, response)
        require(response == relocate(old["response"]["path"]) and actual == rewrite(text(files, old["response"]["path"])),
                unit + ": response changed beyond the exact build-root relocation")
        standard = "/std:c++17" if unit == "terrain_renderer" else "/std:c++14"
        charset = "/source-charset:utf-8" if unit == "world_renderer" else "/source-charset:windows-1252"
        require(all(flag in actual.splitlines() for flag in (standard, charset, "/O2", "/W4", "/WX", "/MD", "/EHsc", "/c")),
                unit + ": retained compiler flags differ")
        log = files.read(row["log"]["path"], 16 * 1024 * 1024).decode("mbcs", errors="replace")
        require(not re.search(r"\b(?:warning\s+(?:C|LNK)\d+|(?:fatal\s+)?error\s+C\d+)", log, re.I), unit + ": compiler diagnostics")
        source, actual_deps, visits = dependencies(files, row["dependency_report"])
        old_source, old_deps, _ = dependencies(files, old["dependency_report"])
        expected = {key(relocate(path)) for path in old_deps} | ({added} if index == 0 else set())
        require(key(source) == key(relocate(old_source)) and actual_deps == expected and actual_deps <= closure and
                row["actual_dependency_count"] == row["expected_dependency_count"] == len(actual_deps) == COUNTS[index] and
                row["dependency_visits"] == visits, unit + ": actual dependency set/count differs")
        consumed = {Path(frozen[path]["original_path"]).name for path in actual_deps} & set(SOURCES)
        require(consumed == (set(SOURCES) if index == 0 else set()), unit + ": hover-source consumption differs")
        old_union.update(old_deps)
        union.update(actual_deps)
        raw = files.read(row["object"]["path"], 128 * 1024 * 1024)
        coff, libraries = parser.coff(raw), defaults(raw)
        require(Path(row["object"]["path"]) == response.parent / "obj" / (stem + ".obj") and
                row["coff_machine"] == coff["machine_hex"] == "0x8664" and libraries == row["default_libraries"] and
                set(libraries) <= LIBRARIES | explicit, unit + ": COFF/directives/object path differs")
        require(key(row["log"]["path"]) == key(stage / ("compile_" + unit + ".log")), "Compile log escaped the stage")
        objects.append(row["object"])
        summaries.append(dict(translation_unit=unit, dependencies=len(actual_deps), dependency_visits=visits,
                              object_bytes=len(raw), coff_machine=coff["machine_hex"], coff_sections=coff["section_count"],
                              changed_inputs_consumed=sorted(consumed), returncode=0))
    require(old_union == set(indexed(base["compiler_inputs"])) and union == closure and len(union) == 550,
            "Actual compilation union does not cover exact parent549 plus one header")
    require(report["response"] == records[0]["response"] and report["dependency_report"] == records[0]["dependency_report"] and
            report["final_dependency_reports"] == {row["translation_unit"]: row["dependency_report"] for row in records},
            "Compiler/dependency aliases differ")
    files.sealed(report["link_response"])
    files.sealed(base["link_response"])
    require(Path(report["link_response"]["path"]) == relocate(base["link_response"]["path"]) and
            text(files, report["link_response"]["path"]) == rewrite(text(files, base["link_response"]["path"])),
            "Link response changed beyond the exact build-root relocation")
    linked = re.findall(r'^"([^"\n]+\.obj)"$', text(files, report["link_response"]["path"]), re.I | re.M)
    require([key(path) for path in linked] == [key(row["path"]) for row in objects], "Link did not consume exactly five current objects")
    return summaries


def verify_libraries_and_commands(files, run, started, report, base, build, stage):
    for field in ("compiler", "linker", "dumpbin"):
        require(same(report[field], base[field]), "A compiler/linker tool changed")
        files.sealed(report[field])
    for field in ("definitions", "system_include_roots", "toolchain", "system_library_names", "compiler_version"):
        require(report[field] == base[field], "Toolchain contract changed: " + field)
    environment = dict(INCLUDE=";".join(str(build / "frozen/include_roots" / ("system_%02d" % index)) for index in range(8)),
                       LIB=str(build / "frozen/implicit_libraries"), LIBPATH="", TMP=str(build / "tmp"), TEMP=str(build / "tmp"),
                       VSLANG="1033", CL="", _CL_="", LINK="")
    require(len(report["system_include_roots"]) == 8 and report["final_environment"] == environment,
            "Compiler/linker option environment differs")
    old_libs = {row["name"].casefold(): row for row in base["implicit_libraries"]}
    libs = {row["name"].casefold(): row for row in report["implicit_libraries"]}
    before = {row["name"].casefold(): row for row in report["implicit_libraries_before"]}
    after = {row["name"].casefold(): row for row in report["implicit_libraries_after"]}
    require(all(len(rows) == 8 and set(rows) == LIBRARIES for rows in (old_libs, libs, before, after)),
            "Exact eight implicit libraries differ")
    for name, row in libs.items():
        current, previous = files.sealed(row), files.sealed(old_libs[name])
        require(same(before[name], old_libs[name]) and same(after[name], row) and same_bytes(current, previous) and
                key(row["path"]) == key(build / "frozen/implicit_libraries" / name) and
                all(current[field] == previous[field] for field in ("file_identity", "mtime_ns", "file_attributes")),
                "Implicit library is not the exact unchanged frozen donor")
    files.sealed(report["map"])
    files.sealed(report["link_log"])
    require(Path(report["map"]["path"]) == build / Path(base["map"]["path"]).relative_to(BASE_ROOT) and
            key(report["link_log"]["path"]) == key(stage / "link.log"), "Link artifacts escaped the expected paths")
    mapping = files.read(report["map"]["path"], 32 * 1024 * 1024).decode("mbcs")
    names = {name.casefold().removesuffix(".lib") + ".lib" for name in re.findall(
        r"\s([\w.-]+):\S+\.(?:obj|dll)\s*$", mapping, re.I | re.M)}
    explicit = {Path(row["path"]).name.casefold() for row in report["libraries"]}
    require(names <= LIBRARIES | explicit and names & LIBRARIES == MAP_LIBRARIES and
            report["actual_implicit_library_namesfrommap"] == sorted(MAP_LIBRARIES), "Actual MAP library contributors differ")
    for stem in STEMS:
        require(any(line.split() and line.split()[-1].casefold() == stem.casefold() + ".obj" for line in mapping.splitlines()),
                "MAP lacks a current Host object contribution: " + stem)
    log = files.read(report["link_log"]["path"], 16 * 1024 * 1024).decode("mbcs", errors="replace")
    require(not re.search(r"\b(?:warning|fatal error|error)\s+LNK\d+", log, re.I), "Link diagnostics are present")
    normalized = log.casefold().replace("/", "\\")
    for name in MAP_LIBRARIES:
        require(str(build / "frozen/implicit_libraries" / name).casefold().replace("/", "\\") in normalized,
                "Verbose link did not resolve the exact frozen library: " + name)
    tools = {Path(row["path"]).name.casefold(): row for row in base["protected_artifacts"]
             if Path(row["path"]).name.casefold() in ("c1xx.dll", "c2.dll", "cmd.exe", "vcvars64.bat")}
    require(set(tools) == {"c1xx.dll", "c2.dll", "cmd.exe", "vcvars64.bat"} and
            indexed(started["toolchain_inputs"]) == indexed([tools[name] for name in ("c1xx.dll", "c2.dll", "cmd.exe")]),
            "Compiler backend/environment inputs differ")
    for row in tools.values():
        files.sealed(row)
    script = build / "read_build_environment.cmd"
    expected_script = '@echo off\ncall "' + tools["vcvars64.bat"]["path"] + '" >nul\nif errorlevel 1 exit /b %errorlevel%\nset\n'
    require(text(files, script) == expected_script, "Environment setup script differs from its fixed literal")
    records = report["final_compilation"]["translation_units"]
    planned = [([str(Path(r"C:\Windows\System32\cmd.exe")), "/d", "/c", str(script)], build, "environment")]
    planned += [([report["compiler"]["path"], "@" + row["response"]["path"]],
                 Path(row["response"]["path"]).parent, "compile_" + row["translation_unit"]) for row in records]
    planned += [([report["linker"]["path"], "@" + report["link_response"]["path"]],
                 Path(report["link_response"]["path"]).parent, "link")]
    require(len(run["commands"]) == len(planned) == 7, "Exactly seven child commands are required")
    require(key(planned[0][0][0]) == key(tools["cmd.exe"]["path"]), "Environment interpreter is not the sealed parent tool")
    for index, (row, (words, cwd, phase)) in enumerate(zip(run["commands"], planned)):
        require(row["command"] == words and key(row["cwd"]) == key(cwd) and row["phase"] == phase and
                type(row["returncode"]) is int and row["returncode"] == 0 and
                not row.get("timed_out", False) and "error_type" not in row, "Child command differs from its exact recipe")
        files.sealed(row["log"])
        expected_log = stage / ("environment.stderr.log" if index == 0 else "link.log" if index == 6 else
                                "compile_" + TUS[index - 1] + ".log")
        require(key(row["log"]["path"]) == key(expected_log), "Command log escaped the exact stage path")
        if 1 <= index <= 5:
            require(same(row["log"], records[index - 1]["log"]), "Compile command/log aliases differ")
        elif index == 6:
            require(same(row["log"], report["link_log"]), "Link command/log aliases differ")
    return sorted(MAP_LIBRARIES)


def verify_pe(files, run, report, base, build, frozen):
    parser_ref = files.pin(PARSER, PARSER_SHA)
    raw = files.read(PARSER, 64 * 1024)
    module = types.ModuleType("zerosis_hover_static_pe")
    module.__file__ = str(PARSER)
    # Authenticate source and execute definitions only. The historical main,
    # verifier, importlib cache and all native functionality remain unused.
    exec(compile(raw, str(PARSER), "exec"), module.__dict__)
    generated = files.pin(GENERATED, GENERATED_SHA)
    copies = [row for row in frozen.values() if key(row["original_path"]) == key(GENERATED)]
    require(len(copies) == 1 and same_bytes(copies[0], generated), "The actual compiler payload header differs")
    arrays, order = module.parse_catalog(files.read(GENERATED, 32 * 1024 * 1024))
    files.sealed(base["executable"])
    before = module.PE(files.read(base["executable"]["path"], 32 * 1024 * 1024))
    executable = files.sealed(report["executable"])
    require(Path(executable["path"]) == build / "final/ZeroSisHost_x64.exe", "Executable escaped its exact private path")
    pe = module.PE(files.read(executable["path"], 32 * 1024 * 1024))
    imports = pe.imports()
    require(len(imports) == len(set(imports)) == 24 and set(imports) == set(before.imports()) ==
            set(report["imports"]["dependencies"]) == set(base["imports"]["dependencies"]), "Actual 24-import allowlist differs")
    transcript = files.document(files.sealed(report["imports"]["log"])["path"])
    require(key(report["imports"]["log"]["path"]) == key(Path(run["started"]["path"]).parent / "imports.static.json") and
            report["imports"]["source"] == "PURE_PYTHON_STATIC_PE" and
            transcript["source"] == "PURE_FILE_BACKED_PE_IMPORT_DIRECTORY" and transcript["dependencies"] == imports and
            same(transcript["image"], report["executable"]), "Actual import transcript differs")
    catalog, old_catalog = pe.catalog(arrays, order), before.catalog(arrays, order)
    rows = [{name: row[name] for name in ("name", "index", "bytes", "sha256")} for row in catalog["exact_payloads"]]
    old_rows = [{name: row[name] for name in ("name", "index", "bytes", "sha256")} for row in old_catalog["exact_payloads"]]
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    summary = dict(entry_count=len(rows), table_rva=catalog["table_rva"], table_section=catalog["table_section"], stride=24,
                   total_payload_bytes=sum(row["bytes"] for row in rows), ordered_payload_manifest_sha256=digest)
    require(len(order) == len(rows) == 67 and rows == old_rows and digest == CATALOG_SHA and summary == report["catalog"] and
            all(summary[name] == base["catalog"][name] for name in
                ("entry_count", "stride", "total_payload_bytes", "ordered_payload_manifest_sha256")),
            "The exact source-ordered 67-payload catalog changed")
    markers = pe.occurrences(MARKER)
    require(len(markers) == len(before.occurrences(MARKER)) == 1 and report["restore_contract_marker"] ==
            dict(ascii=MARKER.decode("ascii"), rva=markers[0], inclusion_evidence_only=True) and
            report["executable"]["pe"] == dict(architecture="x64", pe_format="PE32+", is_dll=False),
            "Unique native-restore inclusion marker or actual PE type differs")
    return module, parser_ref, executable, summary, imports


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--run", required=True, type=Path)
    arguments.add_argument("--run-sha256", required=True)
    options = arguments.parse_args()
    require(os.name == "nt" and sys.dont_write_bytecode and len(sys.argv) == 5 and
            sys.argv[1:].count("--run") == sys.argv[1:].count("--run-sha256") == 1 and
            re.fullmatch(r"[0-9a-f]{64}", options.run_sha256), "Use Windows Python -B with one explicit run/digest pair")
    signature = hashlib.sha256((BASE_SHA + "|" + AUDIT_SHA + "|" + REQUIREMENTS_SHA).encode("ascii")).hexdigest()[:20]
    run_path = options.run
    require(run_path.is_absolute() and str(run_path) == os.path.abspath(run_path) and
            key(run_path) == key(STAGE / "host_build" / signature / "run.json"), "Run escaped its fixed semantic attempt")
    output = run_path.parent / "attestation.json"
    require(not os.path.lexists(output), "An attestation already exists; never overwrite or replay it")
    ordinary(run_path)
    ordinary(output.parent, file=False)
    for encoding in ("utf-8", "utf-8-sig", "ascii", "mbcs", "cp1252"):
        codecs.lookup(encoding)
        b"safe".decode(encoding)
        "safe".encode(encoding)
    reads, denied = install_guard(output)
    files = Files(reads)
    verifier = files.ref(Path(__file__).absolute())
    run_ref = files.pin(run_path, options.run_sha256)
    run = files.document(run_path)
    require(run["schema"] == "zerosis.hover_host.run.v1" and run["status"] == "PASS_CURRENT_HOVER_HOST_BUILD_ONLY" and
            run["signature"] == signature and re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_" + signature[:12], run["build_id"]) and
            run["host_sdk_or_window_executed"] is False and run["no_automatic_retry"] is True and
            run["full_engine_goal_complete"] is False, "Pinned run identity/status/execution boundary differs")
    base_ref = files.pin(PROJECT / "evidence/ui_window_host" / BASE_ID / "build_result.json", BASE_SHA)
    audit_ref = files.pin(STAGE / "component_audit.json", AUDIT_SHA)
    requirements_ref = files.pin(STAGE / "requirements.json", REQUIREMENTS_SHA)
    cleanup_ref = files.pin(STAGE / "cleanup_plan.json", CLEANUP_SHA)
    builder = files.pin(PROJECT / "tools/build_hud_hover_repaint_host.py", BUILDER_SHA)
    require(same(run["builder"], builder) and same(run["baseline_build"], base_ref) and same(run["component_audit"], audit_ref),
            "Run does not bind the fixed builder, parent and component")
    base, audit = files.document(base_ref["path"]), files.document(audit_ref["path"])
    requirements, cleanup = files.document(requirements_ref["path"]), files.document(cleanup_ref["path"])
    require(base["schema"] == "zerosis.ui_window_host_build.v1" and base["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            base["build_id"] == BASE_ID and audit["status"] == "PASS_CURRENT_SOURCE_COMPONENTS_AND_HOSTMAIN_SYNTAX_LINK_PENDING",
            "Fixed parent/component status differs")
    build, stage = PROJECT / "Build/UiWindowHost" / run["build_id"], run_path.parent
    require(key(run["started"]["path"]) == key(stage / "started.json") and key(run["build_result"]["path"]) ==
            key(PROJECT / "evidence/ui_window_host" / run["build_id"] / "build_result.json"), "Started/report paths escaped their exact output")
    started_ref, report_ref = files.sealed(run["started"]), files.sealed(run["build_result"])
    started, report = files.document(started_ref["path"]), files.document(report_ref["path"])
    require(started["schema"] == "zerosis.hover_host.started.v1" and started["signature"] == signature and
            started["build_id"] == report["build_id"] == run["build_id"] and same(started["builder"], builder) and
            same(started["baseline_build"], base_ref) and same(started["component_audit"], audit_ref) and
            same(started["requirements"], requirements_ref) and started["no_automatic_retry"] is True and
            started["host_sdk_or_window_execution_allowed"] is False, "Started receipt differs from the successful run")
    require(report["schema"] == base["schema"] and report["status"] == base["status"] and
            same(report["baseline_build"], base_ref) and same(report["hover_repaint_builder"], builder) and
            same(report["profile"], audit_ref) and same(report["hover_repaint_component"], audit_ref) and
            same(report["started"], started_ref) and report["native_restore_contract_component"] == base["native_restore_contract_component"] and
            report["source_inputs_unchanged"] is True and report["provider_inputs_unchanged"] is True and
            report["ui_asset_preparation"] == dict(executed=False, status="UNCHANGED_ATTESTED_67_PAYLOAD_CATALOG_REUSED") and
            report["dependency_discovery"]["executed"] is False, "Build report aliases or unchanged-input claims differ")
    for name in ("host_runtime_executed", "gamecore_loaded", "sdk_linked", "mods_updated", "stage_updated", "default_promoted",
                 "sdk_restore_verified", "native_restore_approved", "full_engine_goal_complete"):
        require(report[name] is False, "A build-only boundary flag is not false: " + name)
    protected = indexed(cleanup["protected"])
    require(len(protected) == 38, "Cleanup protection inventory differs")
    expected_protected = dict(protected)
    for relative, sha in METADATA.items():
        row = files.pin(PROJECT / relative, sha)
        require(key(row["path"]) not in expected_protected, "Duplicate metadata protection")
        expected_protected[key(row["path"])] = row
    for rows in (run["protected_runtime_inputs"], started["protected_runtime_inputs"], report["protected_artifacts"]):
        require(set(indexed(rows)) == set(expected_protected) and len(rows) == 41 and
                all(same(row, expected_protected[key(row["path"])]) for row in rows), "Protected runtime/save/metadata inventory differs")
        for row in rows:
            files.sealed(row)
    runtime = {name: row for name, row in protected.items() if Path(row["path"]).parent == RUNTIME}
    native = [row for row in protected.values() if Path(row["path"]).suffix == ".zssave"]
    require(len(runtime) == 24 and len(native) == 6 and set(indexed(report["prepared_runtime_inputs"])) == set(runtime) and
            all(same(row, runtime[key(row["path"])]) for row in report["prepared_runtime_inputs"]),
            "Protected cbbd runtime24 or retained native6 differ")
    current, frozen, revisions = verify_inputs(files, run, started, report, base, audit, requirements, build)
    parser, parser_ref, executable, catalog, imports = verify_pe(files, run, report, base, build, frozen)
    compilation = verify_compilation(files, parser, run, report, base, build, stage, frozen)
    mapped = verify_libraries_and_commands(files, run, started, report, base, build, stage)
    require(not denied, "A prohibited verifier operation was attempted")
    files.stable()
    result = dict(schema="zerosis.hover_host.independent_attestation.v1", status="PASS_CURRENT_HOVER_HOST_STATIC_ATTESTATION",
        utc=datetime.now(timezone.utc).isoformat(), verifier=verifier, run=run_ref, builder=builder,
        baseline_build=base_ref, component_audit=audit_ref, requirements=requirements_ref, cleanup_plan=cleanup_ref,
        static_pe_parser=parser_ref, build_result=report_ref, build_id=run["build_id"], executable=executable,
        actual_commands=7, command_returncodes=[row["returncode"] for row in run["commands"]], compilation=compilation,
        compiler_dependency_union=550, source_manifest_count=86, current_input_count=len(current), frozen_input_count=len(frozen),
        frozen_reuse=dict(donor_hardlinks=589, private_source_copies=4, copied_source_bytes=420065,
                          donor_content_and_metadata_preserved=True),
        current_extra_inputs=8, separate_implicit_libraries=sorted(LIBRARIES), actual_map_implicit_libraries=mapped,
        source_revisions=revisions, generated_catalog=catalog, imports=imports, restore_contract_marker_count=1,
        marker_inclusion_evidence_only=True, protected_artifact_count=41, protected_runtime_inputs=24, protected_native_saves=6,
        independently_hashed_physical_inputs=len(files.physical), independently_checked_paths=len(files.rows),
        compiler_or_linker_executed_by_attestor=False, host_executed=False, sdk_loaded=False, dll_loaded=False,
        window_created=False, game_accessed=False, user_saves_accessed=False, compatibility_approved=False,
        live_ui_verified=False, native_restore_approved=False, screen_verification_deferred=True,
        full_engine_goal_complete=False, forbidden_access_attempts=denied)
    encoded = (json.dumps(result, indent=2) + "\n").encode("utf-8")
    require(len(encoded) <= 32 * 1024, "Attestation exceeds its narrow receipt bound")
    with output.open("xb") as stream:
        stream.write(encoded)
    print(json.dumps(dict(status=result["status"], path=str(output), bytes=len(encoded),
                          sha256=hashlib.sha256(encoded).hexdigest(), native_executed=False)))


if __name__ == "__main__":
    main()
