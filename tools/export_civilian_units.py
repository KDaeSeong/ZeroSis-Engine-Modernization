"""Export only the original initial European Settler/Worker inputs with a sealed x86 asset CLI.

No compiler, Host, GameCore, window, user settings or game-process access. The
existing private helper/DLL cache and shared GSD are reused without copying.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
from prepare_unit_models import DEFAULT_GAME, Fpk, require, resolve_pack_name, text

PROJECT = Path(__file__).absolute().parents[1]
SCOPE = PROJECT / "evidence/unit_models/civilian_start/scope.json"
SCOPE_SHA = "943746d6cc04cd175bc5f63d95bbf94d7bc0efd6a186bfabd2578a1444853785"
HELPER_DIR = PROJECT / "Build/UnitModelTools/stock_e473bff5e7a5185057d5"
HELPER_MANIFEST = HELPER_DIR / "tool-manifest.json"
HELPER_MANIFEST_SHA = "448bbc60e04ebb88de6fd83c1b8a443f59ab4a566adf561bdc2cc9a3dfec109a"
HELPER_SHA = "2dec7239b15eaecfec63727a0c4232ae8c1653cb9f5c8e45050a959e7aa76812"
SHARED_GSD = PROJECT / "Build/StockUnitExports/20261005T072135Z/unitmodels_stringdatabase.gsd"
GSD_SHA = "f063955e71728fc76fdc097b9759e291f203c895d32f5f6eeaf5e4f78f73a959"
XML_SHA = ("e59a7903010df3f7173b4fb00068d308a2c34e5dad8f94de5f433bb8d9d23514",
           "ff5c170c2da2282b94871a7de3253f922430616160d76b8f1a50e88f7afbc129",
           "bb831c2f39ea69ce553103d2f88922eae3034a42c185d306b81570f5b82312ec")
PRIVATE_NAMES = frozenset(("StockUnitExporter.cs", "StockUnitExporter.exe", "StockUnitExporter.exe.config",
                          "Firaxis.Framework.dll", "Firaxis.Framework.Granny.dll", "Firaxis.Framework.FirePlace.dll",
                          "Firaxis.Framework.Granny.ImplWin32.dll", "CSScriptLibrary.dll", "GrannyBridge.exe"))
DLL_NAMES = frozenset(name for name in PRIVATE_NAMES if name.endswith(".dll"))
MAX_XML = 2 * 1024 * 1024
MAX_INDEX = 2 * 1024 * 1024
MAX_SELECTED_TOTAL = 32 * 1024 * 1024
MAX_SELECTED_ENTRY = 16 * 1024 * 1024
MAX_JSON = 32 * 1024 * 1024
MAX_JSON_TOTAL = 128 * 1024 * 1024
MAX_LOG = 64 * 1024
SETTLER_MEMBERS = tuple("ART_DEF_UNIT_MEMBER_" + name for name in (
    "EURODONKEY", "EUROFEMALE18", "EUROFEMALE25", "EUROFEMALE35", "EUROFEMALE40",
    "EUROMALE20", "EUROMALE25", "EUROMALE35", "EUROMALE45"))
UNIT_SPEC = (("ART_DEF_UNIT__SETTLER", SETTLER_MEMBERS, 1, 0.12),
             ("ART_DEF_UNIT__WORKER", ("ART_DEF_UNIT_MEMBER_WORKER_EURO",), 8, 0.14))


def checked_path(path, *, root=None, exists=True):
    path = Path(os.path.abspath(path))
    if root is not None:
        require(path.is_relative_to(root) and path != root, "Path crosses its allowed root: " + str(path))
    for parent in (path, *path.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            require(not exists or parent != path, "Required input is absent: " + str(path))
            continue
        require(not getattr(info, "st_file_attributes", 0) & 0x400 and not stat.S_ISLNK(info.st_mode),
                "Reparse/symlink path is forbidden: " + str(parent))
    require(path.resolve(strict=exists) == path, "Noncanonical input/output path: " + str(path))
    return path


def identity(info):
    require(stat.S_ISREG(info.st_mode), "Expected a regular file")
    return {"device": info.st_dev, "file_id": info.st_ino, "bytes": info.st_size, "mtime_ns": info.st_mtime_ns}


def metadata(path):
    path = checked_path(path)
    return {"path": str(path), **identity(path.lstat())}


def file_identity(record):
    return {key: record[key] for key in ("device", "file_id", "bytes", "mtime_ns")}


def read_small(path, maximum, *, allow_empty=False):
    path = checked_path(path)
    before = metadata(path)
    require((0 if allow_empty else 1) <= before["bytes"] <= maximum, "Input exceeds its size bound: " + str(path))
    with path.open("rb") as stream:
        require(identity(os.fstat(stream.fileno())) == file_identity(before),
                "Input identity changed before read: " + str(path))
        data = stream.read(maximum + 1)
        require(identity(os.fstat(stream.fileno())) == file_identity(before),
                "Input changed during read: " + str(path))
    require(len(data) == before["bytes"] and metadata(path) == before, "Input changed while reading: " + str(path))
    return data, {**before, "sha256": hashlib.sha256(data).hexdigest()}


def artifact(path, maximum=MAX_JSON):
    return read_small(path, maximum, allow_empty=True)[1]


def json_small(path, maximum):
    data, record = read_small(path, maximum)
    return json.loads(data.decode("utf-8-sig")), record


def basename(reference):
    require(isinstance(reference, str) and reference and "\0" not in reference, "Empty/invalid virtual asset name")
    normalized = reference.replace("\\", "/")
    virtual = PurePosixPath(normalized)
    require(not virtual.is_absolute() and ":" not in normalized and all(part not in ("", ".", "..") for part in normalized.split("/")),
            "Unsafe virtual asset name: " + reference)
    require(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", virtual.name), "Unsafe input basename: " + reference)
    return virtual.name


def material_reference_basename(reference, declared_reference):
    # GR2 material strings can retain a workstation's old absolute path. This
    # is inert metadata: only compare its final name with the real FXSXML/FPK
    # declaration. Never resolve/open the authoring path or use it as argv.
    require(isinstance(reference, str) and reference and "\0" not in reference,
            "Empty/invalid material reference metadata")
    name = reference.replace("\\", "/").rsplit("/", 1)[-1]
    require(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) and name not in (".", ".."),
            "Unsafe final material metadata component")
    declared = basename(declared_reference)
    require(name.casefold() == declared.casefold(), "Material metadata differs from its exact original FXSXML declaration")
    return name


def check_material_reference_metadata():
    expected = "Euro_Donkey_DIFF.dds"
    absolute = r"D:\projects\ArtDev\Civilization5\Units\Settler\Settler_EURO\NewModelWork\EuroDonkey\Euro_Donkey_DIFF.dds"
    positive = (absolute, "textures/Euro_Donkey_DIFF.dds", "EURO_DONKEY_DIFF.DDS", "../Euro_Donkey_DIFF.dds")
    negative = ("../Different_DIFF.dds", "../..", "textures/", "Euro_Donkey_DIFF.dds:other",
                "textures/한글.dds", "textures/Euro_Donkey_DIFF.dds\0other", "bad\0/Euro_Donkey_DIFF.dds", "NUL")
    for value in positive:
        require(material_reference_basename(value, expected).casefold() == expected.casefold(), "Valid material metadata regression")
    for value in negative:
        try:
            material_reference_basename(value, expected)
        except ValueError:
            pass
        else:
            raise RuntimeError("Unsafe/mismatched material metadata regression")
    try:
        basename(absolute)
    except ValueError:
        pass
    else:
        raise RuntimeError("Filesystem reference guard was weakened by material normalization")
    return {"cases": len(positive) + len(negative) + 1, "passed": True,
            "scope": "PURE_STRING_COMPARISONS_ONLY; NO_METADATA_PATH_OPEN_RESOLVE_OR_EXECUTION"}


def write_new(path, data, output):
    path = checked_path(path, root=output, exists=False)
    require(path.parent == output and not path.exists(), "Refusing to replace an extracted input/output")
    with path.open("xb") as stream:
        stream.write(data)
    return artifact(path, max(len(data), 1))


class SelectedArchive:
    def __init__(self, path):
        self.path = checked_path(path)
        self.before = metadata(self.path)
        self.pack = Fpk(self.path)
        require(metadata(self.path) == self.before and 14 < self.pack.table_end <= MAX_INDEX,
                "Archive changed during bounded index parsing")
        self.initial_index = self.index_digest()
        self.selected = {}

    def index_digest(self):
        require(metadata(self.path) == self.before, "Archive metadata changed before index read")
        with self.path.open("rb") as stream:
            require(identity(os.fstat(stream.fileno())) == file_identity(self.before),
                    "Archive open resolved to another file")
            data = stream.read(self.pack.table_end)
            require(len(data) == self.pack.table_end, "Truncated bounded archive index")
            require(identity(os.fstat(stream.fileno())) == file_identity(self.before),
                    "Archive changed while hashing its index")
        require(metadata(self.path) == self.before, "Archive metadata changed after index read")
        return hashlib.sha256(data).hexdigest()

    def read(self, reference, budget):
        basename(reference)
        name = resolve_pack_name(self.pack, reference)
        key = name.casefold()
        if key in self.selected:
            return self.selected[key]["data"], dict(self.selected[key]["origin"])
        entry = self.pack.entries[key]
        require(0 < entry.size <= MAX_SELECTED_ENTRY and budget[0] + entry.size <= MAX_SELECTED_TOTAL,
                "Selected asset closure exceeds its explicit bound")
        require(metadata(self.path) == self.before, "Archive changed before selected asset read")
        data, origin = self.pack.read(name)
        require(metadata(self.path) == self.before and len(data) == entry.size,
                "Archive changed during selected asset read")
        self.selected[key] = {"data": data, "origin": origin}
        budget[0] += len(data)
        return data, dict(origin)

    def seal(self):
        require(self.index_digest() == self.initial_index, "Archive index changed")
        rows = []
        with self.path.open("rb") as stream:
            require(identity(os.fstat(stream.fileno())) == file_identity(self.before),
                    "Selected seal opened a different archive")
            for key in sorted(self.selected):
                origin = self.selected[key]["origin"]
                stream.seek(origin["offset"])
                data = stream.read(origin["bytes"])
                require(len(data) == origin["bytes"] and hashlib.sha256(data).hexdigest() == origin["sha256"],
                        "Selected archive body changed: " + origin["entry"])
                rows.append({name: origin[name] for name in ("entry", "offset", "bytes", "sha256")})
            require(identity(os.fstat(stream.fileno())) == file_identity(self.before),
                    "Archive changed during selected seal")
        require(metadata(self.path) == self.before, "Archive identity changed after selected seal")
        return {**self.before, "index_bytes": self.pack.table_end,
                "index_sha256": self.initial_index, "selected": rows}


def helper_closure():
    saved, manifest_ref = json_small(HELPER_MANIFEST, MAX_XML)
    require(manifest_ref["sha256"] == HELPER_MANIFEST_SHA and saved.get("status") == "PASS_HELPER_BUILD",
            "Existing helper manifest is not the approved immutable build")
    outputs = saved.get("outputs")
    require(isinstance(outputs, list) and len(outputs) == len(PRIVATE_NAMES)
            and {Path(row["path"]).name for row in outputs} == PRIVATE_NAMES, "Private helper file closure differs")
    actual = []
    for row in outputs:
        path = checked_path(row["path"], root=HELPER_DIR)
        require(path.parent == HELPER_DIR, "Helper file escaped its existing private directory")
        now = artifact(path)
        require(now["sha256"] == row["sha256"] and now["bytes"] == row["bytes"], "Existing helper/cache file changed")
        actual.append(now)
    candidates = {entry.name for entry in checked_path(HELPER_DIR).iterdir()
                  if entry.suffix.casefold() in (".dll", ".exe", ".config")}
    require(candidates == PRIVATE_NAMES - {"StockUnitExporter.cs"}, "Unexpected private DLL/executable/config load candidate")
    executable = next(row for row in actual if Path(row["path"]).name == "StockUnitExporter.exe")
    require(executable["sha256"] == HELPER_SHA, "Existing StockUnitExporter executable changed")
    source_matches = []
    for name in ("StockUnitExporter.cs", "export_stock_units.py"):
        path = checked_path(PROJECT / "tools" / name, root=PROJECT)
        matches = [row for row in saved["inputs"] if Path(row["path"]) == path]
        require(len(matches) == 1, "Helper source provenance is ambiguous: " + name)
        now = artifact(path)
        require(now["sha256"] == matches[0]["sha256"] and now["bytes"] == matches[0]["bytes"],
                "Live helper source differs from the sealed reusable binary")
        source_matches.append(now)
    sdk_rows = [row for row in saved["inputs"] if Path(row["path"]).name in DLL_NAMES]
    require(len(sdk_rows) == len(DLL_NAMES), "Original read-only SDK dependency provenance is incomplete")
    for row in sdk_rows:
        cached = next(value for value in actual if Path(value["path"]).name == Path(row["path"]).name)
        require(cached["sha256"] == row["sha256"] and cached["bytes"] == row["bytes"], "Private SDK bytes differ from original provenance")
    return {"manifest": manifest_ref, "exe": executable, "outputs": actual, "source_matches": source_matches,
            "sdk_source": sdk_rows, "effective_sdk_directory": str(HELPER_DIR),
            "expected_private_load_candidates": sorted(candidates), "private_load_candidate_closure_verified": True,
            "read_set_scope": "EXPECTED_PRIVATE_HELPER_FILES_AND_SEALED_SOURCE; NOT_A_DYNAMIC_OS_FILE_TRACE",
            "argv0_source_review": {"SetDllDirectory": "args[0]", "SetCurrentDirectory": "args[0]",
                                    "AssemblyResolve": "own directory, then args[0]; both are the same sealed private cache",
                                    "GrannyBridge_exe": "wrapper assembly reference only; its Main is not invoked",
                                    "inputs": "args[1..3] GSD/model/idle", "only_output": "args[4] JSON",
                                    "gamecore_or_window_entrypoints_in_export_path": False}}


def bounded_helper(argv, output, name):
    started = time.monotonic()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = threading.Event()
    reader_errors = []
    process = subprocess.Popen(argv, cwd=HELPER_DIR, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)

    def collect(pipe, label):
        try:
            with pipe:
                while True:
                    block = pipe.read(4096)
                    if not block:
                        break
                    room = MAX_LOG - len(buffers[label])
                    buffers[label].extend(block[:room])
                    if len(block) > room:
                        overflow.set()
                        break
        except Exception as error:
            reader_errors.append(type(error).__name__)
            overflow.set()

    readers = [threading.Thread(target=collect, args=(process.stdout, "stdout"), daemon=True),
               threading.Thread(target=collect, args=(process.stderr, "stderr"), daemon=True)]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        while process.poll() is None:
            if overflow.is_set() or time.monotonic() - started >= 45:
                timed_out = not overflow.is_set()
                process.kill()  # Only this explicitly created asset helper child.
                break
            time.sleep(0.025)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
    logs = {label: write_new(output / (name + "." + label + ".txt"), bytes(data), output)
            for label, data in buffers.items()}
    return {"argv": argv, "exit_code": process.returncode, "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - started, 3), "log_limit_bytes_each": MAX_LOG,
            "output_overflow": overflow.is_set(), "reader_errors": reader_errors,
            "reader_threads_finished": all(not reader.is_alive() for reader in readers),
            "creationflags": ["CREATE_NO_WINDOW", "BELOW_NORMAL_PRIORITY_CLASS"], **logs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}", args.run_id), "Invalid private export identity")
    scope, scope_ref = json_small(SCOPE, MAX_XML)
    require(scope_ref["sha256"] == SCOPE_SHA and scope.get("original_game_new_mod_test_hold") is True,
            "Approved civilian scope/retail test hold changed")
    require(all(scope["deployment"].get(name) is False for name in (
        "retail_mods_access_allowed", "default_promotion_allowed", "host_execution_allowed",
        "gamecore_execution_allowed", "native_window_execution_allowed")), "Civilian deployment boundary differs")
    output = checked_path(PROJECT / "Build/CivilianUnitExports" / args.run_id, root=PROJECT / "Build", exists=False)
    require(not output.exists(), "Existing export directory must never be overwritten or replayed")
    output.mkdir(parents=True, exist_ok=False)
    checked_path(output, root=PROJECT / "Build")
    game = checked_path(DEFAULT_GAME)
    xml_paths = [game / "Assets/Units/Civ5ArtDefines_Units.xml",
                 game / "Assets/Units/Civ5ArtDefines_UnitMembers.xml",
                 game / "Assets/Gameplay/XML/Civilizations/CIV5Civilizations.xml"]
    module_paths = [Path(__file__), PROJECT / "tools/prepare_unit_models.py", PROJECT / "tools/civ5_ui_assets.py"]
    report = {"schema": 1, "status": "RUNNING", "run_id": args.run_id, "scope": scope_ref,
              "created_utc": datetime.now(timezone.utc).isoformat(), "units": [], "outputs": [],
              "helper_calls": [], "original_inputs_before": [], "archives_before": [], "selected_artifacts": [],
              "limits": {"members": 10, "selected_total_bytes": MAX_SELECTED_TOTAL, "selected_entry_bytes": MAX_SELECTED_ENTRY,
                         "json_bytes_each": MAX_JSON, "json_bytes_total": MAX_JSON_TOTAL, "helper_seconds_each": 45},
              "gamecore_loaded": False, "host_executed": False, "hwnd_created": False, "gpu_used": False,
              "game_process_accessed": False, "user_settings_or_saves_accessed": False,
              "original_game_new_mod_test_hold": True, "native_screen_acceptance_verified": False,
              "output_directory": str(output)}
    archives = []
    module_before = []
    shared_before = None
    helper_before = None
    failed = False
    try:
        report["material_reference_metadata_regression"] = check_material_reference_metadata()
        module_before = [artifact(path) for path in module_paths]
        report["preparer_inputs_before"] = module_before
        helper_before = helper_closure()
        report["helper"] = helper_before
        report["effective_sdk_directory"] = str(HELPER_DIR)
        report["sdk_source"] = helper_before["sdk_source"]
        shared_before = artifact(SHARED_GSD)
        require(shared_before["sha256"] == GSD_SHA and shared_before["bytes"] == 160004, "Shared original GSD changed")
        xml_data = [read_small(path, MAX_XML) for path in xml_paths]
        report["original_inputs_before"] = [row[1] for row in xml_data]
        require(tuple(row[1]["sha256"] for row in xml_data) == XML_SHA, "Scoped original XML inputs differ from their reviewed hashes")
        unit_root, member_root, civ_root = [ET.fromstring(row[0]) for row in xml_data]
        america = [node for node in civ_root.findall(".//Civilizations/Row") if text(node, "Type") == "CIVILIZATION_AMERICA"]
        require(len(america) == 1 and text(america[0], "ArtStyleType") == "ARTSTYLE_EUROPEAN"
                and text(america[0], "ArtStyleSuffix") == "_EURO", "Initial American European art grounding differs")
        report["civilization_grounding"] = {"civilization": "CIVILIZATION_AMERICA", "art_style": "ARTSTYLE_EUROPEAN",
                                            "art_style_suffix": "_EURO", "era": "ERA_ANCIENT",
                                            "scope": "INITIAL_DEFAULT_ONLY; NO_CULTURE_ERA_OR_EMBARKED_FALLBACK"}
        models = SelectedArchive(game / "Resource/Common/UnitModels.fpk")
        textures = SelectedArchive(game / "Resource/DX9/UnitsTextures.fpk")
        archives = [models, textures]
        budget = [0]
        gsd_data, gsd_origin = models.read("unitmodels_stringdatabase.gsd", budget)
        require(hashlib.sha256(gsd_data).hexdigest() == shared_before["sha256"], "Shared GSD differs from the selected original archive body")
        report["gsd"] = {**shared_before, "reused": True, "origin": gsd_origin}
        names = {}
        plans = []

        def selected(archive, reference, materialize):
            name = basename(reference)
            data, origin = archive.read(reference, budget)
            key = name.casefold()
            identity_key = (origin["pack_path"], origin["entry"].casefold())
            require(key not in names or names[key] == identity_key, "Conflicting selected input basenames: " + name)
            names[key] = identity_key
            if materialize:
                target = output / name
                require(not target.exists(), "Duplicate materialized input basename: " + name)
                origin["extracted"] = write_new(target, data, output)
                report["selected_artifacts"].append(origin)
            return data, origin

        for art_tag, member_names, count, scale in UNIT_SPEC:
            rows = [node for node in unit_root.findall(".//UnitArtInfo") if text(node, "Type") == art_tag]
            require(len(rows) == 1 and text(rows[0], "Formation") == "LooseCivilian", "Original civilian ArtDef/formation differs")
            ordered = [(text(node, "MemberType"), int(text(node, "MemberCount"))) for node in rows[0].findall("UnitMemberArt")]
            require(ordered == [(name, count) for name in member_names], "Original civilian member order/count differs")
            unit = {"art_tag": art_tag, "formation_original": "LooseCivilian", "members": []}
            report["units"].append(unit)
            for member in member_names:
                require(len(plans) < 10, "Civilian member limit exceeded")
                definitions = [node for node in member_root.findall(".//UnitMemberArtInfo") if text(node, "Type") == member]
                require(len(definitions) == 1 and float(text(definitions[0], "fScale")) == scale,
                        "Original civilian scale/member definition differs")
                fxs_data, fxs = selected(models, text(definitions[0], "Granny"), True)
                require(len(fxs_data) <= MAX_XML, "Selected FXSXML exceeds its XML bound")
                fxs_root = ET.fromstring(fxs_data)
                meshes = [node.attrib["file"] for node in fxs_root.findall(".//Mesh") if node.attrib.get("file")]
                idle_nodes = [node for node in fxs_root.findall(".//Animation") if node.attrib.get("ec") == "1000"]
                require(len(meshes) == 1 and len(idle_nodes) == 1
                        and basename(idle_nodes[0].attrib.get("file", "")).casefold().endswith("_idlea.gr2"),
                        "Civilian source must name one mesh and its original IdleA ec1000")
                _, model = selected(models, meshes[0], True)
                _, idle = selected(models, idle_nodes[0].attrib["file"], True)
                texture_refs = [node.attrib["file"] for node in fxs_root.findall(".//Texture") if node.attrib.get("file")]
                diffuse_refs = [value for value in texture_refs if basename(value).casefold().endswith("_diff.dds")]
                sref_refs = [value for value in texture_refs if basename(value).casefold().endswith("_sref.dds")]
                require(len(diffuse_refs) == len(sref_refs) == 1, "Civilian FXSXML diffuse/SREF closure is ambiguous")
                _, diffuse = selected(textures, diffuse_refs[0], False)
                _, sref = selected(textures, sref_refs[0], False)
                row = {"art_tag": art_tag, "member_type": member, "member_count": count, "scale": scale,
                       "fxsxml": fxs, "model": model, "idle": idle, "diffuse": diffuse, "sref": sref, "idle_event_code": 1000}
                plans.append(row)
                unit["members"].append({key: row[key] for key in ("member_type", "member_count", "scale")})
        require(len(plans) == 10, "Expected exactly ten original civilian member inputs")
        report["selected_bytes"] = budget[0]
        report["archives_before"] = [archive.seal() for archive in archives]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetErrorMode.argtypes = [ctypes.c_uint]
        kernel32.SetErrorMode.restype = ctypes.c_uint
        kernel32.WerSetFlags.argtypes = [ctypes.c_ulong]
        kernel32.WerSetFlags.restype = ctypes.c_long
        previous_mode = kernel32.SetErrorMode(32771)
        wer_hresult = kernel32.WerSetFlags(32)
        report["runner_error_ui"] = {"dll": "kernel32", "error_mode": 32771,
                                     "previous_error_mode": previous_mode, "wer_flags": 32, "wer_hresult": wer_hresult}
        require(wer_hresult >= 0, "Runner WER suppression failed before any child launch")
        json_total = 0
        for row in plans:
            target = checked_path(output / (row["member_type"] + ".json"), root=output, exists=False)
            require(not target.exists(), "Refusing to replace a member export")
            argv = [helper_before["exe"]["path"], str(HELPER_DIR), str(SHARED_GSD),
                    row["model"]["extracted"]["path"], row["idle"]["extracted"]["path"], str(target)]
            call = bounded_helper(argv, output, row["member_type"])
            report["helper_calls"].append(call)
            require(call["exit_code"] == 0 and not call["timed_out"] and not call["output_overflow"]
                    and not call["reader_errors"] and call["reader_threads_finished"], "Asset helper failed; no further members launched")
            exported, exported_ref = json_small(target, MAX_JSON)
            json_total += exported_ref["bytes"]
            require(json_total <= MAX_JSON_TOTAL, "Export JSON aggregate exceeds its bound")
            require(exported.get("source_sha256") == row["model"]["sha256"]
                    and exported.get("animation_sha256") == row["idle"]["sha256"] and exported.get("gsd_sha256") == GSD_SHA,
                    "Asset helper JSON does not match the selected exact original inputs")
            require(len(exported.get("models", [])) == len(exported.get("meshes", [])) == 1
                    and exported.get("pose", {}).get("time") == 0
                    and exported.get("pose", {}).get("method") == "original_track_curve_samples", "Unexpected bounded model/mesh/IdleA t0 export")
            materials = exported["meshes"][0].get("materials", [])
            require(len(materials) == 1, "Exported civilian mesh must have one original material")
            material_reference_basename(materials[0].get("diffuse", ""), row["diffuse"]["entry"])
            material_reference_basename(materials[0].get("sref", ""), row["sref"]["entry"])
            row["json"] = exported_ref
            report["outputs"].append(row)
        report["exported_json_bytes"] = json_total
    except Exception as error:
        failed = True
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        try:
            report["original_inputs_after"] = [artifact(path, MAX_XML) for path in xml_paths]
            report["archives_after"] = [archive.seal() for archive in archives]
            report["preparer_inputs_after"] = [artifact(path) for path in module_paths]
            helper_after = helper_closure() if helper_before is not None else None
            shared_after = artifact(SHARED_GSD) if shared_before is not None else None
            report["helper_inputs_unchanged"] = helper_after == helper_before
            report["shared_gsd_unchanged"] = shared_after == shared_before
            require(report["original_inputs_after"] == report["original_inputs_before"]
                    and report["archives_after"] == report["archives_before"]
                    and report["preparer_inputs_after"] == module_before
                    and helper_after == helper_before and shared_after == shared_before
                    and artifact(SCOPE) == scope_ref, "Original/archive/helper/preparer input seal changed")
            report["original_inputs_unchanged"] = True
        except Exception as error:
            failed = True
            report["post_seal_error"] = {"type": type(error).__name__, "message": str(error)}
            report["original_inputs_unchanged"] = False
        report["status"] = "PASS_CIVILIAN_UNIT_EXPORT" if not failed and len(report["outputs"]) == 10 else "FAILED_CIVILIAN_UNIT_EXPORT"
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        destination = output / "export-manifest.json"
        write_new(destination, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), output)
    print(json.dumps({"status": report["status"], "manifest": artifact(destination), "outputs": len(report["outputs"]),
                      "helper_calls": len(report["helper_calls"]), "selected_bytes": report.get("selected_bytes", 0),
                      "gamecore_loaded": False, "hwnd_created": False}, ensure_ascii=False))
    return 0 if report["status"] == "PASS_CIVILIAN_UNIT_EXPORT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
