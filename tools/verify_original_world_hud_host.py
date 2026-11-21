"""Independently attest a fixed full-HUD/wheel Host build without executing it.

The only permitted write is one fresh attestation.json beside the pinned run.
No compiler, linked image, SDK, window, subprocess, network, or DLL is run.
"""
from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import types

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/original_world_hud/host_build"
AUTHORITY = STAGE / "inputs.json"
AUTHORITY_SHA = "db8dbd4d0c3e854dda26cf6786f4d34de3fb0b0750a8f8fe2d9b8d764c3ad594"
READ_HELPER = PROJECT / "tools/verify_relinked_native_host.py"
READ_HELPER_SHA = "fd218b51b7ce321d861575a5314886390f30d378958830d38a06fa998b34f0d5"
PE_HELPER = PROJECT / "evidence/goody_hut/owned_fonts/verify_candidate.py"
PE_HELPER_SHA = "723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f"
BUILDER = PROJECT / "tools/build_original_world_hud_host.py"
BUILDER_SHA = "24d5ba1ce99e542556fd1b9123895aa5c5394c9092a8d7175677878abed22e36"
BASE_ID = "20261024T042219Z_e6399c82ee5c"
TUS = ("host_main", "window", "renderer", "world_renderer", "terrain_renderer")
STEMS = ("HostMain", "BitmapWindow", "BitmapRenderer", "WorldViewRenderer", "WorldTerrainRenderer")
COUNTS = (465, 266, 270, 279, 301)
GENERATED = PROJECT / "Source/Host/UiPopupAssets.generated.h"
GENERATED_SHA = "333cf40c942e2545c83372084ed276e2aec11ab9fd7cbf4744f8c0c4e7c48da9"
CATALOG_SHA = "db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c"
MARKER = b"NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|"
CHANGES = (
    "Source/Presentation/WorldViewRenderer.cpp", "Source/Presentation/BitmapWindow.h",
    "Source/Presentation/BitmapWindow.cpp", "Source/Presentation/WorldCameraControls.h",
    "Source/Host/InteractiveGameLoop.h",
)
CONSUMERS = (
    {"BitmapWindow.h", "WorldCameraControls.h", "InteractiveGameLoop.h"},
    {"BitmapWindow.cpp", "BitmapWindow.h"}, set(),
    {"WorldViewRenderer.cpp", "WorldCameraControls.h"}, {"WorldCameraControls.h"},
)
LIBRARIES = {"msvcrt.lib", "msvcprt.lib", "vcruntime.lib", "oldnames.lib", "bcrypt.lib",
             "kernel32.lib", "ucrt.lib", "uuid.lib"}
MAP_LIBRARIES = LIBRARIES - {"oldnames.lib", "uuid.lib"}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def content(row):
    require(type(row) is dict and type(row.get("path")) is str and
            type(row.get("bytes")) is int and 0 <= row["bytes"] <= 128 * 1024 * 1024 and
            type(row.get("sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
            "Malformed bounded content reference")
    return key(row["path"]), row["bytes"], row["sha256"]


def same_content(left, right):
    return content(left) == content(right)


def same_bytes(left, right):
    return content(left)[1:] == content(right)[1:]


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, "Duplicate JSON key")
        result[name] = value
    return result


def warm_codecs():
    # These decoders otherwise import lazily after the file-access guard.
    for encoding in ("utf-8", "utf-8-sig", "ascii", "mbcs", "cp1252"):
        codecs.lookup(encoding)
        b"safe".decode(encoding)
        "safe".encode(encoding)


def load_pure(path, sha, name, maximum):
    require(within(path, PROJECT), "Pure helper escaped the project")
    for ancestor in (path, *path.parents):
        require(not ancestor.lstat().st_file_attributes & 0x400, "Reparse pure helper path")
    before = path.stat()
    require(before.st_size <= maximum and not before.st_file_attributes & 0x400,
            "Pure helper exceeds its bound or is a reparse point")
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and
            hashlib.sha256(raw).hexdigest() == sha, "Authenticated pure helper changed")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    # Execute authenticated Python source only; never consult a .pyc cache or
    # invoke either historical verifier's main/verify/compilation entrypoint.
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


class Files:
    """Reuse the sealed reader, hashing each physical content identity once.

    Every alias still has its exact path/identity/size/mtime/attributes checked;
    stable() independently rehashes every physical identity before publishing.
    """
    def __init__(self, helper, reads):
        self.helper, self.reads = helper, reads
        self.reader = helper.Inputs(reads)
        self.rows, self.physical = {}, {}

    def stat(self, path):
        info = self.helper.ordinary(path)
        return info, (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes)

    def ref(self, path, expected=None):
        path = Path(path)
        info, snapshot = self.stat(path)
        self.reads.add(key(path))
        require(info.st_size <= 128 * 1024 * 1024, "Input exceeds its hash budget")
        if key(path) in self.rows:
            row = self.rows[key(path)]
            require(snapshot == (row["file_identity"][0], row["file_identity"][1], row["bytes"],
                                 row["mtime_ns"], row["file_attributes"]), "Input metadata changed")
        elif snapshot in self.physical:
            row = dict(self.physical[snapshot], path=str(path))
        else:
            row = dict(self.reader.ref(path), file_attributes=info.st_file_attributes)
            self.physical[snapshot] = row
        if expected is not None:
            require(same_content(row, expected), "Sealed content differs: " + str(path))
            for field in ("file_identity", "mtime_ns", "file_attributes"):
                if field in expected:
                    require(type(expected[field]) is type(row[field]) and expected[field] == row[field],
                            "Sealed " + field + " differs: " + str(path))
        self.rows[key(path)] = row
        return row

    def sealed(self, row):
        content(row)
        return self.ref(row["path"], row)

    def read(self, path, maximum=4 * 1024 * 1024):
        row = self.ref(path)
        require(row["bytes"] <= maximum, "Input exceeds its read bound")
        raw = Path(path).read_bytes()
        require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
                "Input changed while reading")
        self.ref(path, row)
        return raw

    def document(self, path):
        return json.loads(self.read(path).decode("utf-8-sig"), object_pairs_hook=unique_object,
                          parse_constant=lambda value: require(False, "Nonfinite JSON number"))

    def stable(self):
        for row in list(self.rows.values()):
            self.ref(row["path"], row)
        for row in self.physical.values():
            # The original Inputs reader checks the digest and metadata again.
            self.reader.ref(row["path"], row)


def by_path(rows, label):
    require(type(rows) is list, label + " is not an artifact list")
    output = {}
    for row in rows:
        path, _, _ = content(row)
        require(path not in output, "Duplicate " + label + " path")
        output[path] = row
    return output


def by_original(rows, field, label):
    output = {}
    for row in rows:
        require(type(row.get(field)) is str, "Missing " + label + " original path")
        path = key(row[field])
        require(path not in output, "Duplicate " + label + " original path")
        output[path] = row
    return output


def text(files, path, maximum=8 * 1024 * 1024):
    return files.read(path, maximum).decode("utf-8-sig").replace("\r\n", "\n")


def recover(files, annotation):
    require(type(annotation) is dict and "path" not in annotation and
            type(annotation.get("original_path")) is str and type(annotation.get("bytes")) is int and
            0 <= annotation["bytes"] <= 8 * 1024 * 1024 and
            re.fullmatch(r"[0-9a-f]{64}", annotation.get("sha256", "")),
            "Historical bytes must use a bounded original_path annotation, not a live artifact")
    files.sealed(annotation["backup"])
    require(within(annotation["backup"]["path"], PROJECT / "evidence"), "Historical backup escaped project evidence")
    with gzip.open(annotation["backup"]["path"], "rb") as stream:
        raw = stream.read(annotation["bytes"] + 1)
    require(len(raw) == annotation["bytes"] and hashlib.sha256(raw).hexdigest() == annotation["sha256"],
            "Historical gzip does not recover its exact declared bytes")
    return key(annotation["original_path"]), annotation["bytes"], annotation["sha256"]


def walk(value):
    if type(value) is dict:
        if "path" in value and "sha256" in value and "bytes" in value:
            yield value
        for child in value.values():
            yield from walk(child)
    elif type(value) is list:
        for child in value:
            yield from walk(child)


def frozen_rows(report):
    rows = []
    for group in ("compiler_inputs", "sources", "provider_inputs", "system_libraries", "build_tools", "implicit_libraries"):
        for row in report[group]:
            if group == "sources" and "original_path" not in row:
                # Lua source-manifest entries use original_source as their sole
                # origin. Normalize a local copy, never the authenticated report.
                require(type(row.get("original_source")) is str and
                        Path(row["original_source"]).suffix.casefold() == ".lua",
                        "Only Lua source-manifest rows may use the sole source alias")
                row = dict(row, original_path=row["original_source"])
            rows.append(row)
    rows.extend(report["provider_reports"].values())
    rows.append(report["ui_assets"])
    result = {}
    for row in rows:
        path, _, _ = content(row)
        require(type(row.get("original_path")) is str, "Frozen row lacks its original path")
        if "original_source" in row:
            require(key(row["original_source"]) == key(row["original_path"]), "Source aliases identify different originals")
        if path in result:
            previous = result[path]
            require(same_content(previous, row) and key(previous["original_path"]) == key(row["original_path"]) and
                    all(previous.get(name) == row.get(name) for name in
                        ("file_identity", "mtime_ns", "file_attributes", "materialization")), "Conflicting frozen aliases")
        else:
            result[path] = row
    return result


def verify_history(files, report, baseline, proofs):
    changed = {key(PROJECT / name) for name in CHANGES}
    source_changes = proofs["source_audit"]["changes"]
    source_expected = {key(row["before"]["path"]): row for row in source_changes}
    require(len(source_changes) == len(source_expected) == 5 and set(source_expected) == changed,
            "Authority does not identify the exact five production changes")
    operational = proofs["operational_revisions"]["revisions"]
    operations_expected = {key(row["before"]["path"]): row for row in operational}
    require(len(operational) == len(operations_expected) == 3 and
            proofs["operational_revisions"]["compiled_host_sources_changed"] is False and
            proofs["operational_revisions"]["host_or_sdk_executed"] is False,
            "Operational revision scope differs")
    metadata = proofs["metadata_publication"]["changed_metadata"]
    metadata_expected = {key(row["before"]["path"]): row for row in metadata}
    require(len(metadata) == len(metadata_expected) == 2 and not (changed & set(operations_expected)) and
            not (changed & set(metadata_expected)) and not (set(operations_expected) & set(metadata_expected)),
            "Historical exception groups overlap or have unexpected counts")
    allowed = {}
    for field, expected, count in (
        ("source_revision_provenance", source_expected, 5),
        ("historical_operational_recovery", operations_expected, 3),
        ("historical_metadata_recovery", metadata_expected, 2),
    ):
        rows = report[field]
        require(type(rows) is list and len(rows) == count, "Historical group count differs: " + field)
        seen = set()
        for entry in rows:
            before = entry.get("before", entry)
            path, size, sha = recover(files, before)
            require(path in expected and path not in seen, "Unapproved or duplicate historical exception")
            authority = expected[path]
            require((size, sha) == content(authority["before"])[1:] and
                    same_content(before["backup"], authority["backup"]), "Historical bytes are not authority-bound")
            seen.add(path); allowed[path] = (size, sha)
            if "after" in entry:
                require(key(entry["after"]["path"]) == path, "Historical after row names another live path")
                files.sealed(entry["after"])
                if field != "historical_metadata_recovery":
                    require(same_bytes(entry["after"], authority["after"]), "Current source differs from its authorized revision")
        require(seen == set(expected), "Historical exception inventory is incomplete")
    require(len(allowed) == 10, "Historical waiver scope must contain exactly ten named paths")
    inherited = report["inherited_historical_metadata_recovery"]
    require(len(inherited) == len(baseline["historical_metadata_recovery"]) == 2,
            "Inherited historical metadata annotation count differs")
    for row, old in zip(inherited, baseline["historical_metadata_recovery"]):
        require(recover(files, row) == recover(files, old) and same_content(row["backup"], old["backup"]),
                "Inherited history does not exactly preserve its original annotation and gzip")
    return allowed, source_expected


def verify_sources(files, report, baseline, build, allowed, source_expected):
    old_root = PROJECT / "Build/UiWindowHost" / BASE_ID
    relocate = lambda path: build / Path(path).relative_to(old_root)
    current = by_path(report["current_source_inputs"], "current input")
    old_current = by_path(baseline["current_source_inputs"], "baseline current input")
    require(set(current) == set(old_current) and len(current) == 592, "Current input inventory differs")
    changed = set(source_expected)
    for path, row in current.items():
        files.sealed(row)
        expected = source_expected[path]["after"] if path in changed else old_current[path]
        require(same_bytes(row, expected), "Current input is neither unchanged nor an authorized source revision")
        if path in changed:
            require(same_bytes(old_current[path], source_expected[path]["before"]), "Source revision before does not match parent inputs")
    old_frozen, new_frozen = frozen_rows(baseline), frozen_rows(report)
    require(len(old_frozen) == len(new_frozen) == 592 and
            {key(relocate(row["path"])) for row in old_frozen.values()} == set(new_frozen),
            "Frozen snapshot path inventory differs from root-only relocation")
    implicit_donors = by_path(baseline["implicit_libraries"], "parent implicit library")
    require(len(implicit_donors) == 8 and
            {row["name"] for row in implicit_donors.values()} == LIBRARIES,
            "Parent implicit library exceptions differ")
    missing_implicit = set()
    copies = links = copied_bytes = 0
    for old in old_frozen.values():
        files.sealed(old)
        row = new_frozen[key(relocate(old["path"]))]
        require(within(row["path"], build / "frozen") and key(row["original_path"]) == key(old["original_path"]),
                "Frozen input changed its source identity")
        actual = files.sealed(row)
        original = current.get(key(row["original_path"]))
        if original is None:
            # These eight retained library donors are deliberately outside the
            # current-source manifest. Their exact origin/name/content still
            # binds to the parent, and the hardlink identity check below applies.
            donor = implicit_donors.get(key(old["path"]))
            require(donor is not None and same_content(old, donor) and
                    key(old["original_path"]) == key(donor["original_path"]) and
                    old.get("name") == row.get("name") == donor["name"] and
                    key(row["original_path"]) not in changed and same_bytes(actual, donor),
                    "Only exact unchanged parent implicit libraries may lack a current source row")
            missing_implicit.add(key(old["path"]))
        else:
            require(same_bytes(actual, original), "Frozen input differs from the actual current original")
        if key(row["original_path"]) in changed:
            copies += 1; copied_bytes += row["bytes"]
            require(row["materialization"] == "owned_changed_source_copy" and
                    actual["file_identity"] != old["file_identity"] and
                    actual["file_identity"] != original["file_identity"] and
                    actual["file_attributes"] & 1 and
                    Path(row["path"]).stat().st_nlink == 1,
                    "Changed source is not an owned single-link frozen copy")
        else:
            links += 1
            require(row["materialization"] == "attested_snapshot_hardlink" and same_bytes(row, old) and
                    all(actual[name] == old[name] for name in ("file_identity", "mtime_ns", "file_attributes")),
                    "Unchanged input is not the exact retained donor hardlink")
    require(missing_implicit == set(implicit_donors), "Missing current originals are not exactly the eight implicit libraries")
    require(copies == 5 and links == 587 and copied_bytes <= 512 * 1024, "Frozen copy/hardlink scope differs")
    require(len(report["compiler_inputs"]) == report["compiler_dependency_count"] == 549 and
            len(report["sources"]) == 85 and len(report["sources"]) == len(baseline["sources"]),
            "Compiler or source-manifest count differs")
    for group in ("compiler_inputs", "sources", "provider_inputs", "system_libraries", "build_tools", "implicit_libraries"):
        require(len(report[group]) == len(baseline[group]) and
                [key(row["path"]) for row in report[group]] == [key(relocate(row["path"])) for row in baseline[group]],
                "Ordered frozen group changed beyond relocation: " + group)
    require(report["libraries"] == report["provider_inputs"] + report["system_libraries"], "Explicit library aliases differ")
    source_origins = by_original(report["sources"], "original_source", "source manifest")
    require(set(source_origins) == set(by_original(baseline["sources"], "original_source", "baseline source manifest")),
            "A source manifest entry was added, removed, or rebound")
    protected, old_protected = by_path(report["protected_artifacts"], "protected artifact"), by_path(baseline["protected_artifacts"], "parent protected artifact")
    require(len(protected) == 1961 and set(protected) == set(old_protected), "Protected artifact path inventory differs")
    for path, row in protected.items():
        before = old_protected[path]
        if path in allowed:
            require(content(before)[1:] == allowed[path], "Historical exception does not bind this parent protected row")
        else:
            require(same_content(row, before), "An unapproved protected artifact changed")
        files.sealed(row)
    return current, new_frozen, dict(private_source_copies=copies, donor_hardlinks=links, copied_source_bytes=copied_bytes)


def verify_compilation(files, helper, parser, report, baseline, build):
    old_root = PROJECT / "Build/UiWindowHost" / BASE_ID
    relocate = lambda path: build / Path(path).relative_to(old_root)
    records = report["final_compilation"]["translation_units"]
    old_records = baseline["final_compilation"]["translation_units"]
    require(tuple(row["translation_unit"] for row in records) == tuple(row["translation_unit"] for row in old_records) == TUS,
            "Five translation-unit order differs")
    closure = by_path(report["compiler_inputs"], "compiler input")
    explicit = {Path(row["path"]).name.casefold() for row in report["libraries"]}
    union, objects, results = set(), [], []
    for index, (row, old) in enumerate(zip(records, old_records)):
        name, stem = TUS[index], STEMS[index]
        require(type(row["returncode"]) is int and row["returncode"] == 0, name + ": compile failed")
        for field in ("response", "log", "dependency_report", "object"):
            files.sealed(row[field])
        files.sealed(old["response"])
        response = Path(row["response"]["path"])
        require(response == relocate(old["response"]["path"]) and row["command"] ==
                [report["compiler"]["path"], "@" + str(response)], name + ": command/response binding differs")
        expected = text(files, old["response"]["path"]).replace(str(old_root), str(build)).replace(old_root.as_posix(), build.as_posix())
        actual = text(files, response)
        require(actual == expected, name + ": compiler response changed beyond root relocation")
        standard = "/std:c++17" if name == "terrain_renderer" else "/std:c++14"
        charset = "/source-charset:utf-8" if name == "world_renderer" else "/source-charset:windows-1252"
        require(all(flag in actual.splitlines() for flag in (standard, charset, "/O2", "/W4", "/WX", "/MD", "/EHsc", "/c")),
                name + ": retained compiler options differ")
        log = files.read(row["log"]["path"], 16 * 1024 * 1024).decode("mbcs", errors="replace")
        require(not re.search(r"\b(?:warning\s+(?:C|LNK)\d+|(?:fatal\s+)?error\s+C\d+)", log, re.I), name + ": compiler diagnostic present")
        source, actual_deps, visits = helper.dependencies(files, row["dependency_report"])
        old_source, old_deps, _ = helper.dependencies(files, old["dependency_report"])
        require(key(source) == key(relocate(old_source)) and actual_deps == {key(relocate(path)) for path in old_deps} and
                actual_deps <= set(closure), name + ": actual dependency paths differ")
        require(type(row["expected_dependency_count"]) is int and type(row["actual_dependency_count"]) is int and
                row["expected_dependency_count"] == row["actual_dependency_count"] == len(actual_deps) == COUNTS[index],
                name + ": normalized dependency count differs")
        consumed = {Path(closure[path]["original_path"]).name for path in actual_deps} & {Path(path).name for path in CHANGES}
        require(consumed == CONSUMERS[index], name + ": changed-source consumption differs")
        union.update(actual_deps)
        raw = files.read(row["object"]["path"], 128 * 1024 * 1024)
        coff = parser.coff(raw)
        defaults = helper.object_directives(raw)
        require(coff["machine_hex"] == "0x8664" and Path(row["object"]["path"]) == response.parent / "obj" / (stem + ".obj") and
                defaults and defaults <= LIBRARIES | explicit, name + ": COFF identity/default libraries differ")
        objects.append(row["object"])
        results.append(dict(translation_unit=name, dependencies=len(actual_deps), dependency_visits=visits,
                            object_bytes=len(raw), coff_machine=coff["machine_hex"], coff_sections=coff["section_count"],
                            changed_inputs_consumed=sorted(consumed), returncode=0))
    require(union == set(closure) and len(union) == 549, "Actual dependency union does not cover the entire frozen compiler closure")
    require(report["response"] == records[0]["response"] and report["dependency_report"] == records[0]["dependency_report"] and
            report["final_dependency_reports"] == {row["translation_unit"]: row["dependency_report"] for row in records},
            "Top-level compile/dependency aliases differ")
    response = files.sealed(report["link_response"])
    files.sealed(baseline["link_response"])
    expected = text(files, baseline["link_response"]["path"]).replace(str(old_root), str(build)).replace(old_root.as_posix(), build.as_posix())
    require(text(files, response["path"]) == expected, "Link response changed beyond root relocation")
    linked = re.findall(r'^"([^"\n]+\.obj)"$', expected, re.I | re.M)
    require([key(path) for path in linked] == [key(row["path"]) for row in objects], "Link did not consume exactly the five current objects")
    snapshot = report["link_snapshot"]
    require(type(snapshot["returncode"]) is int and snapshot["returncode"] == 0 and
            snapshot["response"] == report["link_response"] and snapshot["objects_before"] == snapshot["objects_after"] == objects,
            "Link object before/after snapshot differs")
    for row in snapshot["objects_before"] + snapshot["objects_after"]:
        files.sealed(row)
    return results, objects


def verify_parent_retirement(files, baseline, attestation, retirement):
    require(attestation["status"] == "PASS_CURRENT_NATIVE_RESTORE_HOST_STATIC_ATTESTATION" and
            attestation["build_id"] == BASE_ID and attestation["host_or_sdk_or_window_executed"] is False and
            attestation["native_restore_approved"] is False and attestation["full_engine_goal_complete"] is False,
            "Parent attestation identity or scope differs")
    require(retirement["status"] == "PASS_VERIFIED_CURRENT_HOST_INTERMEDIATES_RETIRED" and
            retirement["all_targets_absent"] is True and retirement["host_sdk_or_ui_executed"] is False and
            retirement["deleted_files"] == 6, "Parent intermediate retirement is incomplete")
    files.sealed(retirement["plan"])
    plan = files.document(retirement["plan"]["path"])
    targets = by_path(plan["targets"], "parent retirement target")
    old_root = PROJECT / "Build/UiWindowHost" / BASE_ID
    expected = {key(old_root / "read_build_environment.cmd")}
    for index, (name, stem) in enumerate(zip(TUS, STEMS)):
        row = baseline["final_compilation"]["translation_units"][index]["object"]
        path = old_root / ("final/tu_%02d_%s/obj/%s.obj" % (index, name, stem))
        expected.add(key(path))
        require(key(row["path"]) == key(path) and key(path) in targets and same_content(targets[key(path)], row),
                "Parent retired object inventory differs")
    require(set(targets) == expected == {key(path) for path in retirement["deleted_paths"]} and
            not any(os.path.lexists(path) for path in expected), "A retired parent object or environment command reappeared")
    return 5


def verify_libraries(files, report, baseline, build):
    for field in ("compiler", "linker", "dumpbin"):
        require(same_content(report[field], baseline[field]), "A compiler/linker tool changed")
        files.sealed(report[field])
    for field in ("definitions", "system_include_roots", "toolchain", "system_library_names"):
        require(report[field] == baseline[field], "Toolchain contract changed: " + field)
    require(len(report["system_include_roots"]) == 8, "System include-root inventory differs")
    expected_environment = dict(INCLUDE=";".join(str(build / "frozen/include_roots" / ("system_%02d" % index)) for index in range(8)),
        LIB=str(build / "frozen/implicit_libraries"), LIBPATH="", TMP=str(build / "tmp"), TEMP=str(build / "tmp"),
        VSLANG="1033", CL="", _CL_="", LINK="")
    require(report["final_environment"] == expected_environment, "Compiler/linker environment or option injection differs")
    previous = {row["name"].casefold(): row for row in baseline["implicit_libraries"]}
    frozen = {row["name"].casefold(): row for row in report["implicit_libraries"]}
    before = {row["name"].casefold(): row for row in report["implicit_libraries_before"]}
    after = {row["name"].casefold(): row for row in report["implicit_libraries_after"]}
    require(all(len(rows) == 8 for rows in (previous, frozen, before, after)) and
            set(previous) == set(frozen) == set(before) == set(after) == LIBRARIES,
            "Implicit library inventory differs")
    for name in LIBRARIES:
        old, current = files.sealed(before[name]), files.sealed(after[name])
        require(same_content(old, previous[name]) and same_content(current, frozen[name]) and same_bytes(old, current) and
                all(old[field] == current[field] for field in ("file_identity", "mtime_ns", "file_attributes")),
                "Implicit library is not the unchanged attested donor")
        require(key(current["path"]) == key(build / "frozen/implicit_libraries" / name), "Implicit library escaped the private frozen directory")
    files.sealed(report["map"]); files.sealed(report["link_log"])
    map_text = files.read(report["map"]["path"], 16 * 1024 * 1024).decode("mbcs", errors="strict")
    mapped = {name.casefold().removesuffix(".lib") + ".lib" for name in
              re.findall(r"\s([\w.-]+):\S+\.(?:obj|dll)\s*$", map_text, re.I | re.M)}
    explicit = {Path(row["path"]).name.casefold() for row in report["libraries"]}
    require(mapped <= LIBRARIES | explicit and mapped & LIBRARIES == MAP_LIBRARIES and
            report["actual_implicit_library_namesfrommap"] == sorted(MAP_LIBRARIES), "Actual MAP library contribution differs")
    for stem in STEMS:
        require(any(line.split() and line.split()[-1].casefold() == stem.casefold() + ".obj" for line in map_text.splitlines()),
                "The link MAP lacks an actual Host object contribution: " + stem)
    log = files.read(report["link_log"]["path"], 16 * 1024 * 1024).decode("mbcs", errors="replace")
    require(not re.search(r"\b(?:warning|fatal error|error)\s+LNK\d+", log, re.I), "Link diagnostics are present")
    normalized_log = log.casefold().replace("/", "\\")
    for name in MAP_LIBRARIES:
        require(str(build / "frozen/implicit_libraries" / name).casefold().replace("/", "\\") in normalized_log,
                "Verbose link did not resolve the exact frozen library: " + name)
    return sorted(MAP_LIBRARIES)


def verify_commands(files, run, started, report, baseline, build, stage):
    records = report["final_compilation"]["translation_units"]
    command_rows = run["commands"]
    cmd_rows = [row for row in baseline["protected_artifacts"] if
                key(row["path"]) == key(r"C:\Windows\System32\cmd.exe")]
    require(len(cmd_rows) == 1, "Parent lacks one exact sealed environment interpreter")
    interpreter = files.sealed(cmd_rows[0])
    planned = [([interpreter["path"], "/d", "/c", str(build / "read_build_environment.cmd")], build)]
    planned += [(row["command"], Path(row["response"]["path"]).parent) for row in records]
    planned += [([report["linker"]["path"], "@" + report["link_response"]["path"]], Path(report["link_response"]["path"]).parent)]
    require(len(command_rows) == len(started["planned_commands"]) == len(planned) == 7, "Exactly seven child commands are required")
    for index, (row, preflight, (words, cwd)) in enumerate(zip(command_rows, started["planned_commands"], planned)):
        phase = "environment" if index == 0 else "link" if index == 6 else "compile"
        require(type(row["returncode"]) is int and row["returncode"] == 0 and row["phase"] == phase and
                key(row["executable"]) == key(words[0]) and row["command"] == words and key(row["cwd"]) == key(cwd) and
                preflight["command"] == words and key(preflight["cwd"]) == key(cwd) and not row.get("timed_out", False),
                "Recorded child command is not its exact planned recipe at index " + str(index))
        files.sealed(row["log"])
        log_path = stage / ("environment.stderr.log" if index == 0 else "link.log" if index == 6 else "compile_" + TUS[index - 1] + ".log")
        require(key(row["log"]["path"]) == key(log_path), "Recorded command log escaped the exact stage log")
        if 1 <= index <= 5:
            require(same_content(row["log"], records[index - 1]["log"]), "Compile log alias differs")
        elif index == 6:
            require(same_content(row["log"], report["link_log"]), "Link log alias differs")
    setup = files.ref(build / "read_build_environment.cmd")
    require(setup["bytes"] == 140 and setup["sha256"] == "fbea552a6bb1afe675455702d2bcb52b666cb58115922a59f508f1cefc0e55bf",
            "The one environment command differs from the attested literal script")
    return ["environment", *(["compile"] * 5), "link"]


def verify_pe(files, parser, report, baseline, build):
    source = files.ref(GENERATED, dict(path=str(GENERATED), bytes=GENERATED.stat().st_size, sha256=GENERATED_SHA))
    frozen = next(row for row in report["compiler_inputs"] if key(row["original_path"]) == key(GENERATED))
    require(same_bytes(source, files.sealed(frozen)), "Frozen original UI payload header differs")
    arrays, order = parser.parse_catalog(files.read(GENERATED, 32 * 1024 * 1024))
    require(len(order) == 67, "Original UI payload count differs")
    files.sealed(baseline["executable"])
    previous = parser.PE(files.read(baseline["executable"]["path"], 32 * 1024 * 1024))
    executable = files.sealed(report["executable"])
    require(key(executable["path"]) == key(build / "final/ZeroSisHost_x64.exe"), "The executable escaped the exact private output path")
    pe = parser.PE(files.read(executable["path"], 32 * 1024 * 1024))
    imports = pe.imports()
    require(len(imports) == len(set(imports)) == 24 and set(imports) == set(previous.imports()) ==
            set(baseline["imports"]["dependencies"]) == set(report["imports"]["dependencies"]), "Actual 24-import allowlist differs")
    observed = files.document(files.sealed(report["imports"]["log"])["path"])
    require(observed["source"] == "PURE_FILE_BACKED_PE_IMPORT_DIRECTORY" and observed["dependencies"] == imports and
            same_content(observed["image"], report["executable"]), "Static imports transcript differs from the actual PE")
    catalog, old_catalog = pe.catalog(arrays, order), previous.catalog(arrays, order)
    rows = [{name: row[name] for name in ("name", "index", "bytes", "sha256")} for row in catalog["exact_payloads"]]
    old_rows = [{name: row[name] for name in ("name", "index", "bytes", "sha256")} for row in old_catalog["exact_payloads"]]
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    summary = dict(entry_count=len(rows), table_rva=catalog["table_rva"], table_section=catalog["table_section"], stride=24,
                   total_payload_bytes=sum(row["bytes"] for row in rows), ordered_payload_manifest_sha256=digest)
    require(rows == old_rows and digest == CATALOG_SHA and summary == report["catalog"] and
            all(summary[field] == baseline["catalog"][field] for field in
                ("entry_count", "stride", "total_payload_bytes", "ordered_payload_manifest_sha256")),
            "The exact ordered 67-payload catalog changed")
    marker = pe.occurrences(MARKER)
    require(len(marker) == len(previous.occurrences(MARKER)) == 1 and report["restore_contract_marker"] ==
            dict(ascii=MARKER.decode("ascii"), rva=marker[0], inclusion_evidence_only=True),
            "The unique read-only native-restore inclusion marker differs")
    require(report["executable"]["pe"] == dict(architecture="x64", pe_format="PE32+", is_dll=False), "Builder PE observations differ")
    for relative, sha in (
        ("Source/Host/NativeSaveArchive.h", "e3be711d114807d68ac2e965622dd622eb1f36c81e1da1c64f94a3a97b9e36c6"),
        ("Source/Host/NativeSaveEnvelope.h", "f8f343d891e4e9fe7aa9d756e1c467971586125803163edf1e478717c11aa7a8"),
        ("Source/Host/NativeRestoreContract.h", "74bafe17ed8548e59acaaa7facc2dba30ae9454e5613d81d218c3b2080524a36"),
    ):
        row = files.ref(PROJECT / relative)
        require(row["sha256"] == sha, "An unchanged native V1/restore source changed")
        copy = next(item for item in report["compiler_inputs"] if key(item["original_path"]) == key(row["path"]))
        require(same_bytes(copy, row), "The actual compiler did not consume the unchanged native contract source")
    return executable, summary, imports, report["restore_contract_marker"]


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--run", required=True, type=Path)
    arguments.add_argument("--run-sha256", required=True)
    options = arguments.parse_args()
    require(sys.argv[1:].count("--run") == sys.argv[1:].count("--run-sha256") == 1 and len(sys.argv) == 5,
            "Use exactly one explicit --run and --run-sha256 pair")
    require(re.fullmatch(r"[0-9a-f]{64}", options.run_sha256), "Run digest must be an exact lowercase SHA256")
    run_path = options.run
    require(run_path.is_absolute() and str(run_path) == os.path.abspath(run_path) and
            run_path.name == "run.json" and key(run_path.parent.parent) == key(STAGE) and
            re.fullmatch(r"[0-9a-f]{20}", run_path.parent.name), "Run escaped the single semantic build stage")
    output = run_path.parent / "attestation.json"
    require(not os.path.lexists(output), "An attestation already exists; do not overwrite or replay it")
    warm_codecs()
    helper = load_pure(READ_HELPER, READ_HELPER_SHA, "zerosis_original_hud_readonly_helpers", 128 * 1024)
    parser = load_pure(PE_HELPER, PE_HELPER_SHA, "zerosis_original_hud_pure_pe", 64 * 1024)
    # The parent pin graph includes this exact environment interpreter file.
    # This permits reading its bytes, never launching it or reading Windows
    # generally. All actual opens still require the per-file guard allowlist.
    helper.READ_ROOTS = (*helper.READ_ROOTS, Path(r"C:\Windows\System32\cmd.exe"))
    helper.ordinary(run_path); helper.ordinary(output.parent, file=False)
    reads, denied = helper.install_guard(output)
    files = Files(helper, reads)
    verifier = files.ref(Path(__file__).absolute())
    read_helper = files.ref(READ_HELPER)
    pe_helper = files.ref(PE_HELPER)
    require(read_helper["sha256"] == READ_HELPER_SHA and pe_helper["sha256"] == PE_HELPER_SHA,
            "Loaded helper bytes differ from their guarded current bytes")
    authority_ref = files.ref(AUTHORITY, dict(path=str(AUTHORITY), bytes=4795, sha256=AUTHORITY_SHA))
    authority = files.document(AUTHORITY)
    require(authority["schema"] == "zerosis.original_world_hud.host_build_inputs.v1" and
            authority["baseline_build_id"] == BASE_ID and tuple(authority["changed_production_paths"]) == CHANGES and
            (authority["current_source_count"], authority["compiler_dependency_count"], authority["source_manifest_count"],
             authority["protected_artifact_count"] ) == (592, 549, 85, 1961) and tuple(authority["dependency_counts"]) == COUNTS and
            authority["historical_exception_counts"] == dict(production_sources=5, operational_sources=3, metadata=2) and
            authority["planned_direct_children"] == 7 and authority["host_sdk_or_window_execution_allowed"] is False and
            authority["library_or_import_or_ui_payload_changes_allowed"] is False and authority["full_engine_goal_complete"] is False,
            "Authority layout, counts, or scope differs")
    # The builder records full freshly sealed identities, while inputs.json
    # intentionally carries only path/bytes/SHA. Reconstruct those exact full
    # references independently rather than weakening the later graph equality.
    refs = {name: files.sealed(row) for name, row in authority["references"].items()}
    expected_ref_names = {"baseline_build", "baseline_attestation", "baseline_retirement", "source_audit", "component",
                          "final_source_audit", "operational_revisions", "metadata_publication", "prepared_request",
                          "prior_pair_final_audit", "build_helpers", "static_pe_parser"}
    require(set(refs) == expected_ref_names and key(refs["static_pe_parser"]["path"]) == key(PE_HELPER) and
            refs["static_pe_parser"]["sha256"] == PE_HELPER_SHA, "Authority proof inventory differs")
    proofs = {}
    for name, row in refs.items():
        files.sealed(row)
        if name not in ("build_helpers", "static_pe_parser"):
            proofs[name] = files.document(row["path"])
    baseline = proofs["baseline_build"]
    require(baseline["build_id"] == BASE_ID and baseline["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            same_content(proofs["baseline_attestation"]["build_result"], refs["baseline_build"]) and
            same_content(proofs["baseline_attestation"]["executable"], baseline["executable"]),
            "Authority baseline report and independent proof are not one graph")
    retired_objects = verify_parent_retirement(files, baseline, proofs["baseline_attestation"], proofs["baseline_retirement"])
    run_ref = files.ref(run_path)
    require(run_ref["sha256"] == options.run_sha256, "Run bytes differ from the caller's explicit pin")
    run = files.document(run_path)
    signature = hashlib.sha256((AUTHORITY_SHA + "|" + "|".join(refs[name]["sha256"] for name in
        ("source_audit", "component", "final_source_audit"))).encode("ascii")).hexdigest()[:20]
    require(run["schema"] == "zerosis.original_world_hud.host_build_run.v1" and
            run["status"] == "PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_BUILD_ONLY" and
            run["signature"] == signature == run_path.parent.name and
            re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_" + signature[:12], run["build_id"]), "Pinned run identity or successful status differs")
    build = PROJECT / "Build/UiWindowHost" / run["build_id"]
    stage = run_path.parent
    require(same_content(run["profile"], authority_ref) and same_content(run["baseline_build"], refs["baseline_build"]) and
            run["proofs"] == refs and key(run["builder"]["path"]) == key(BUILDER) and run["builder"]["sha256"] == BUILDER_SHA,
            "Run authority/builder/proof binding differs")
    files.sealed(run["builder"])
    require(key(run["started"]["path"]) == key(stage / "started.json") and
            key(run["build_result"]["path"]) == key(PROJECT / "evidence/ui_window_host" / run["build_id"] / "build_result.json"),
            "Run report/started references escaped their exact output paths")
    started_ref, report_ref = files.sealed(run["started"]), files.sealed(run["build_result"])
    started, report = files.document(started_ref["path"]), files.document(report_ref["path"])
    require(started["schema"] == "zerosis.original_world_hud.host_build_started.v1" and
            started["signature"] == signature and started["build_id"] == report["build_id"] == run["build_id"] and
            same_content(started["builder"], run["builder"]) and same_content(started["profile"], authority_ref) and
            same_content(started["baseline_build"], refs["baseline_build"]) and started["proofs"] == refs and
            started["no_automatic_retry"] is True and started["host_or_sdk_or_window_execution_allowed"] is False,
            "Started receipt differs from the completed run")
    require(report["schema"] == "zerosis.ui_window_host_build.v1" and report["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            same_content(report["profile"], authority_ref) and same_content(report["original_world_hud_profile"], authority_ref) and
            same_content(report["original_world_hud_builder"], run["builder"]) and same_content(report["started"], started_ref) and
            same_content(report["baseline_build"], refs["baseline_build"]) and
            same_content(report["original_world_hud_component"], refs["component"]) and
            same_content(report["original_world_hud_source_audit"], refs["source_audit"]) and
            same_content(report["original_world_hud_final_source_audit"], refs["final_source_audit"]),
            "Normal build report is not the authority-bound current build")
    for field in ("host_or_sdk_or_window_executed", "original_game_or_user_state_accessed", "network_used", "sdk_restore_verified",
                  "native_restore_approved", "default_promoted", "actual_window_wheel_routing_verified", "full_engine_goal_complete"):
        require(run[field] is False, "Run exceeds build-only scope: " + field)
    for field in ("host_runtime_executed", "gamecore_loaded", "sdk_linked", "mods_updated", "stage_updated", "default_promoted",
                  "sdk_restore_verified", "native_restore_approved", "actual_window_wheel_routing_verified", "full_engine_goal_complete"):
        require(report[field] is False, "Report exceeds build-only scope: " + field)
    require(run["input_files_unchanged"] is True and run["no_automatic_retry"] is True and
            run["objects_retained_for_separate_cleanup"] is True and report["source_inputs_unchanged"] is True and
            report["provider_inputs_unchanged"] is True and run["forbidden_access_attempts"] == report["forbidden_access_attempts"] == [],
            "Input stability or build guard observations differ")
    allowed, source_expected = verify_history(files, report, baseline, proofs)
    current, frozen, materialization = verify_sources(files, report, baseline, build, allowed, source_expected)
    require(by_path(started["current_inputs"], "started current input") == current,
            "Current inputs differ from the pre-compile started receipt")
    require(len(started["frozen_donors"]) == 592 and
            set(by_path(started["frozen_donors"], "started donor")) == set(frozen_rows(baseline)), "Started donor inventory differs")
    preflight = by_path(started["protected_artifacts"], "preflight protected artifact")
    require(report["preflight_protected_artifact_count"] == len(preflight), "Preflight protected count differs")
    for row in preflight.values():
        files.sealed(row)
    component = proofs["component"]
    require(component["status"] == "PASS_ORIGINAL_WORLD_HUD_SOFTWARE_COMPONENT_O2_OD" and
            {row["mode"] for row in component["modes"]} == {"O2", "Od"} and component["host_or_sdk_or_window_executed"] is False and
            proofs["final_source_audit"]["status"] == "PASS_ORIGINAL_WORLD_HUD_SOURCE_COMPONENT_PUBLICATION_AND_CLEANUP_AUDIT" and
            proofs["final_source_audit"]["production_sources_rehashed"] == proofs["final_source_audit"]["changed_source_backup_roundtrips_verified"] == 5,
            "The prior offscreen/source proof differs")
    for row in component["protected_inputs_unchanged"]:
        files.sealed(row)
    compilation, objects = verify_compilation(files, helper, parser, report, baseline, build)
    require(run["actual_objects"] == objects and run["compiler_dependency_count"] == 549 and
            run["actual_dependency_counts"] == list(COUNTS) and run["current_source_count"] == 592 and run["source_manifest_count"] == 85 and
            run["historical_exception_counts"] == authority["historical_exception_counts"], "Run compiler/source aliases differ")
    command_roles = verify_commands(files, run, started, report, baseline, build, stage)
    library_names = verify_libraries(files, report, baseline, build)
    executable, catalog, imports, marker = verify_pe(files, parser, report, baseline, build)
    require(run["catalog"] == catalog and run["restore_contract_marker"] == marker and report["new_source_inputs"] == [] and
            {key(row["path"]) for row in report["sources_changed_from_baseline"]} == set(source_expected) and
            report["ui_asset_preparation"]["executed"] is False and report["dependency_discovery"]["executed"] is False,
            "Run PE/source/preparation observations differ")
    reuse = report["frozen_input_reuse"]
    require(reuse["hardlinked_files"] == 587 and reuse["copied_files"] == 5 and
            reuse["copied_source_bytes"] == materialization["copied_source_bytes"] and
            reuse["hardlinked_logical_bytes"] == sum(row["bytes"] for row in frozen.values() if row["materialization"] == "attested_snapshot_hardlink") and
            reuse["donor_content_and_metadata_preserved"] is True, "Frozen reuse observations differ")
    request = proofs["prepared_request"]
    require(request["run_id"] == "20261024T050152Z_fd0465b26387" and
            type(request["runtime_inputs"]) is list and len(request["runtime_inputs"]) == 24 and
            run["protected_runtime_inputs_unchanged"] == 24, "Retained prepared runtime inventory differs")
    # The pinned request has three exact reference shapes. Obtain bounded current
    # sizes and identities independently, checking every declared size and hash
    # before comparing the builder's full artifact references.
    expected_shapes = {frozenset(("source", "path", "sha256")): 11,
                       frozenset(("source", "path", "sha256", "bytes")): 12,
                       frozenset(("path", "sha256")): 1}
    observed_shapes = dict.fromkeys(expected_shapes, 0)
    runtime_rows = []
    for row in request["runtime_inputs"]:
        require(type(row) is dict and frozenset(row) in expected_shapes and
                ("source" not in row or type(row["source"]) is str) and type(row["path"]) is str and
                type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
                "Malformed prepared runtime input reference")
        observed_shapes[frozenset(row)] += 1
        require(within(row["path"], Path(request["cwd"])), "A retained input escaped its prepared runtime")
        require("source" in row or key(row["path"]) == key(Path(request["cwd"]) / "bundle.manifest"),
                "Only the exact prepared bundle manifest may omit its source")
        actual = files.ref(row["path"])
        require(actual["sha256"] == row["sha256"], "A prepared runtime input differs from its requested hash")
        if "bytes" in row:
            require(type(row["bytes"]) is int and row["bytes"] == actual["bytes"],
                    "A prepared runtime input differs from its declared byte count")
        runtime_rows.append(actual)
    require(observed_shapes == expected_shapes, "Prepared runtime reference shape counts differ from 11/12/1")
    runtime = by_path(runtime_rows, "prepared runtime input")
    for rows in (run["retained_runtime_inputs"], report["prepared_runtime_inputs"]):
        actual = by_path(rows, "reported retained runtime input")
        require(set(actual) == set(runtime) and all(same_content(actual[path], runtime[path]) for path in runtime),
                "The build did not preserve exactly the 24 retained runtime inputs")
    # Annotation originals are never opened with their historical hashes. Only
    # actual artifact references in the new graph are checked here.
    for value in (report, started, run):
        for row in walk(value):
            files.sealed(row)
    files.stable()
    require(not denied, "Read-only attestation attempted a forbidden operation")
    result = dict(schema="zerosis.original_world_hud.host_build.independent_attestation.v1",
        status="PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_STATIC_ATTESTATION", utc=datetime.now(timezone.utc).isoformat(),
        build_id=run["build_id"], verifier=verifier, authority=authority_ref, run=run_ref, started=started_ref,
        builder=run["builder"], build_result=report_ref, baseline_build=refs["baseline_build"], baseline_attestation=refs["baseline_attestation"],
        authenticated_read_helper=read_helper, authenticated_pe_helper=pe_helper,
        seven_recorded_commands_verified=True, command_roles=command_roles, returncodes=[0] * 7,
        exact_response_relocation_verified=True, units=compilation, actual_objects=objects,
        compiler_dependency_union=549, current_inputs_verified=592, source_manifest_verified=85,
        protected_artifacts_verified=1961, preflight_protected_artifacts_verified=len(preflight),
        unique_artifact_paths_verified=len(files.rows), unique_content_identities_hashed=len(files.physical),
        materialization=materialization, parent_retired_coff_objects_absent=retired_objects,
        historical_exception_counts=authority["historical_exception_counts"], inherited_metadata_annotations_verified=2,
        implicit_libraries_verified=8, implicit_libraries_from_map=library_names, imports_verified=len(imports),
        imports=imports, catalog=catalog, restore_contract_marker=marker, executable=executable,
        original_ui_payloads_regenerated=False, native_v1_schema_changed=False, native_contract_source_hashes_unchanged=True,
        retained_prepared_runtime_inputs_unchanged=24, input_files_unchanged=True, objects_retained_for_separate_cleanup=True,
        attestation_wrote_only_this_receipt=True, source_edited=False, host_or_sdk_or_window_executed=False,
        sdk_or_host_module_loaded=False, child_process_started=False, process_query_performed=False, network_used=False,
        actual_window_wheel_routing_verified=False, full_campaign_ui_verified=False, sdk_restore_verified=False,
        native_restore_approved=False, default_promoted=False, full_engine_goal_complete=False, forbidden_access_attempts=denied)
    encoded = (json.dumps(result, ensure_ascii=True, indent=2) + "\n").encode("ascii")
    require(len(encoded) <= 24 * 1024, "Bounded attestation exceeded 24 KiB")
    with output.open("xb") as stream:
        stream.write(encoded)
    print(json.dumps(dict(status=result["status"], build_id=run["build_id"], output=str(output), bytes=len(encoded),
                         sha256=hashlib.sha256(encoded).hexdigest()), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps(dict(status="FAIL_ORIGINAL_WORLD_HUD_HOST_ATTESTATION", error_type=type(error).__name__,
                              error=str(error)[:4000], attestation_written=False, host_or_sdk_or_window_executed=False)), file=sys.stderr)
        raise SystemExit(1)
