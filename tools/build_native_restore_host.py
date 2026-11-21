"""Build one private current-restore Host; never execute the Host or the SDK.

The read-only --preflight creates nothing. A build is single use: five old TU
recipes are relocated unchanged, then linked once using retained frozen inputs.
Completed-unit receipts preserve work if a later step needs a separate review.
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
import shutil
import stat
import struct
import subprocess
import sys
import types

PROJECT = Path(__file__).absolute().parents[1]
BASE_ID = "20261024T021245Z_18bbd0dd26e7"
BASE_ROOT = PROJECT / "Build/UiWindowHost" / BASE_ID
BASE = PROJECT / "evidence/ui_window_host" / BASE_ID / "build_result.json"
BASE_SHA = "26edcf537984d5bf6cc74be3a908dcec92fda946ba03a2e5188fb32a22fbf5f2"
STAGE_ROOT = PROJECT / "evidence/native_restore_contract/host_build"
UNITS = ("host_main", "window", "renderer", "world_renderer", "terrain_renderer")
STEMS = ("HostMain", "BitmapWindow", "BitmapRenderer", "WorldViewRenderer", "WorldTerrainRenderer")
COUNTS = (465, 266, 270, 279, 301)
CHANGED = {
    "SdkGameRestore.h": (9763, "294d809a752f642c0a46679d2fd9763918458edbc1e84553987c3cdb16fb3ea0"),
    "HostRun.h": (41801, "78da76d2e986c7c064b0f559d207ec0f301277ae18d66ecaa1d61840e3284578"),
    "InteractiveGameSession.h": (111812, "5f1fde7a60d365f94b327f3b8a62a85bae41da6c7ab8c25f18d4b69cb8429bbc"),
}
ADDED = {
    "NativeRestoreContract.h": (11496, "74bafe17ed8548e59acaaa7facc2dba30ae9454e5613d81d218c3b2080524a36"),
    "RetailSaveGameFront.h": (8902, "8e1316874fbf8f1c726f39a250128a475399b8916ce89a3b9822c0656bb0215c"),
    "RetailSaveGameTail.h": (11145, "30ae2705dd5e358cf7bf8a56061d8ecb865f9cc7a3fc73290b07c8599c82d140"),
    "RetailSaveStateWire.h": (7064, "10bfd0244fe20289b2c72cb98a5402b88795a36395c217c768035fb24741fdda"),
}
PROOFS = {
    "component": ("evidence/native_restore_contract/component_retry01/result.json", "25bb2ba3dc2ab2af6eff87edbce2d6f8b6c6c628ce1e9fc1be1831531b14232c"),
    "syntax": ("evidence/native_restore_contract/host_syntax_retry01/result.json", "1b4dcad9c032ed3b761ccd1a9c55d28f6915d7dda317e5d7ef484fe293304fd8"),
    "source_change": ("evidence/native_restore_contract/source_backups/integration.source_change.json", "611ab664e3afa18ee13969d78dd9ec775c894ded00625736e0e3b4dfb8fb5fef"),
    "pair_audit": ("evidence/sdk_runtime_play/latest_pair_preparation/publication/final_audit.json", "730c6a91e5e0e975502559c1952008200cf85181885e0385c62d3f7f1a2c4eaf"),
    "pair_publication": ("evidence/sdk_runtime_play/latest_pair_preparation/publication/result.json", "594dbe5eef2028fc4989a7f1550dac68a353714ce13aa768776c86f6c11f7d0b"),
    "old_host_audit": ("evidence/native_save_archive/host_relink/18bbd0dd26e70e623276/publication/final_audit.json", "633586ca57bbf9343113e364e8b35bea8c16934e01a99719c065bdd9c0222aba"),
    "saved_game_observations": ("evidence/native_restore_contract/latest_pair_saved_game_retry01/result.json", "c26f42eac201c36a75d236f43199c2d8e065f07b2605c76327873da0fe2ab41d"),
    "publication_before": ("evidence/native_restore_contract/publication/pre_edit.json", "435543ec412350b744805bfe251854c00b807a2a52664c4bb9272a0ddd172605"),
}
PARSER = PROJECT / "evidence/goody_hut/owned_fonts/verify_candidate.py"
PARSER_SHA = "723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f"
MARKER = b"NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|"
HISTORICAL_METADATA = (
    ("evidence/save_menu/20261013_original_screen/current_progress.json", 272401,
     "e0abfc1beee7867eb0da93a8c46a029bd84cd2fe91723a0b7cbd6d8d9cd1dd81",
     "current_progress.json.before.gz", 62907, "2cf1ca125ab314dcb6292e86e53cad735e83144f2962e66654eb946b42d140cd"),
    ("docs/M7_RETAIL_SAVE_BOUNDARY.md", 92653,
     "62c4878dd63006526f75e7efaf050d7b79617df889027ffadaad64c9bf3f83d7",
     "M7_RETAIL_SAVE_BOUNDARY.md.before.gz", 32385, "72470bfa81990016923ae2fda88d2f052b100c1dc72987f92ba5488204a0548f"),
)
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
VCVARS = VS / "VC/Auxiliary/Build/vcvars64.bat"
REQUEST = PROJECT / "evidence/interactive_game/20261024T031412Z_e06aeb61ed6a/request.json"
REQUEST_SHA = "e5fc7eac31221508a40423e6ac5be15e2c0cbc7ca4cb2abb50c2dd3e285b17f6"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def ordinary(path, *, file=True):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.abspath(path), "Noncanonical path")
    folded = key(path)
    require(not any(word in folded for word in ("\\my games\\", "\\steamapps\\common\\", "\\.codex\\")) and
            not str(path).startswith("\\\\"), "Original game, user state or remote path is forbidden")
    for ancestor in (path, *path.parents):
        if os.path.lexists(ancestor):
            require(not ancestor.lstat().st_file_attributes & 0x400, "Reparse path: " + str(ancestor))
    if file:
        require(stat.S_ISREG(path.stat().st_mode), "Not an ordinary file: " + str(path))
    return path


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes


def unique_object(pairs):
    output = {}
    for name, value in pairs:
        require(name not in output, "Duplicate JSON key")
        output[name] = value
    return output


class Scope:
    def __init__(self):
        self.reads, self.rows, self.commands, self.denied = set(), {}, [], []
        self.roots, self.parents, self.copies, self.links = (), set(), set(), {}
        self.allowed_commands = set()
        self.pending = None
        sys.addaudithook(self.audit)

    def audit(self, event, values):
        def deny():
            self.denied.append(dict(event=event, target=str(values[0])[:240] if values else ""))
            raise PermissionError("Private restore Host build forbids " + event)

        def owned(path):
            return any(within(path, root) for root in self.roots)

        if event == "open" and values and isinstance(values[0], (str, bytes, os.PathLike)):
            target, mode, flags = values
            target = key(os.fsdecode(target))
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if (writing and (not owned(target) or target in self.links)) or (not writing and target not in self.reads and not owned(target)):
                deny()
        elif event == "subprocess.Popen":
            executable, words, cwd, _ = values
            if not self.pending or key(cwd) != key(self.pending["cwd"]):
                deny()
            expected = self.pending["command"]
            if (list(words) != expected if isinstance(words, (tuple, list)) else words != subprocess.list2cmdline(expected)):
                deny()
            if executable is not None and key(executable) != key(expected[0]):
                deny()
            signature = (tuple(expected), key(cwd))
            if signature not in self.allowed_commands:
                deny()
            self.allowed_commands.remove(signature)
            self.commands.append(dict(executable=expected[0], command=expected, cwd=str(cwd), returncode=None))
        elif event == "os.mkdir":
            if not owned(values[0]) and key(values[0]) not in self.parents:
                deny()
        elif event == "os.link":
            source, destination = map(key, values[:2])
            if self.links.get(destination) != source or not owned(destination):
                deny()
        elif event == "os.chmod":
            if key(values[0]) not in self.copies:
                deny()
        elif event.startswith(("socket.", "ctypes.", "urllib.", "http.client.", "os.exec", "os.spawn")) or event in (
                "os.system", "os.startfile", "os.startfile/2", "os.posix_spawn", "os.posix_spawnp", "os.kill", "os.killpg",
                "os.remove", "os.rmdir", "os.rename", "os.symlink", "os.truncate", "os.utime", "os.chdir", "os.fork"):
            deny()

    def ref(self, path, expected=None):
        path = ordinary(path)
        before = path.stat()
        self.reads.add(key(path))
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        require(identity(before) == identity(path.stat()), "Input changed while hashing: " + str(path))
        row = dict(path=str(path), bytes=before.st_size, sha256=digest,
                   file_identity=[before.st_dev, before.st_ino], mtime_ns=before.st_mtime_ns,
                   file_attributes=before.st_file_attributes)
        if expected is not None:
            require(key(path) == key(expected["path"]), "Artifact path differs")
            for name in ("bytes", "sha256", "file_identity", "mtime_ns", "file_attributes"):
                if name in expected:
                    require(row[name] == expected[name], "Artifact " + name + " differs: " + str(path))
        require(key(path) not in self.rows or self.rows[key(path)] == row, "Input changed between reads")
        self.rows[key(path)] = row
        return row

    def sealed(self, row):
        require(type(row) is dict and type(row.get("path")) is str and
                re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")), "Malformed artifact")
        return self.ref(row["path"], row)

    def read(self, path, maximum=16 * 1024 * 1024):
        row = self.ref(path)
        require(row["bytes"] <= maximum, "Input exceeds bound: " + str(path))
        raw = Path(path).read_bytes()
        require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], "Input changed while reading")
        return raw

    def json(self, path):
        return json.loads(self.read(path).decode("utf-8-sig"), object_pairs_hook=unique_object,
                          parse_constant=lambda value: require(False, "Nonfinite JSON number"))

    def stable(self):
        for row in list(self.rows.values()):
            self.sealed(row)
        require(not self.denied, "A forbidden operation was attempted")


def pin(scope, path, sha, size=None):
    return scope.ref(path, dict(path=str(path), sha256=sha, **({"bytes": size} if size is not None else {})))


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def historical(scope, backup, expected):
    scope.sealed(backup)
    with gzip.open(backup["path"], "rb") as stream:
        raw = stream.read(expected["bytes"] + 1)
    require(len(raw) == expected["bytes"] and hashlib.sha256(raw).hexdigest() == expected["sha256"],
            "Historical gzip does not recover the declared source bytes")
    return dict(original_path=expected["path"], bytes=expected["bytes"], sha256=expected["sha256"], backup=scope.sealed(backup))


def dependencies(scope, row):
    scope.sealed(row)
    value = scope.json(row["path"])
    require(value.get("Version") == "1.2" and type(value.get("Data")) is dict, "Unexpected dependency schema")
    data = value["Data"]
    require(type(data.get("Source")) is str and type(data.get("Includes")) is list and
            all(type(path) is str for path in data["Includes"]) and not data.get("ProvidedModule") and
            not data.get("ImportedModules") and not data.get("ImportedHeaderUnits"), "Malformed dependency paths")
    visits = [data["Source"], *data["Includes"]]
    return {key(path) for path in visits}, len(visits)


def parser_module(scope):
    pin(scope, PARSER, PARSER_SHA)
    # Execute exactly the authenticated source, bypassing unpinned .pyc caches.
    module = types.ModuleType("zerosis_restore_host_static_pe")
    module.__file__ = str(PARSER)
    exec(compile(scope.read(PARSER, 64 * 1024), str(PARSER), "exec"), module.__dict__)
    require(key(module.__file__) == key(PARSER), "Parser module origin differs")
    return module


def catalog_summary(value):
    rows = [{name: row[name] for name in ("name", "index", "bytes", "sha256")} for row in value["exact_payloads"]]
    return dict(entry_count=len(rows), table_rva=value["table_rva"], table_section=value["table_section"], stride=24,
                total_payload_bytes=sum(row["bytes"] for row in rows), ordered_payload_manifest_sha256=hashlib.sha256(
                    json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest())


def object_defaults(raw):
    output = []
    for index in range(struct.unpack_from("<H", raw, 2)[0]):
        at = 20 + 40 * index
        if raw[at:at + 8] == b".drectve":
            length, offset = struct.unpack_from("<II", raw, at + 16)
            output.append(raw[offset:offset + length].decode("ascii"))
    require(output, "COFF object has no linker directives")
    matches = re.findall(r'/DEFAULTLIB:(?:"([^"\s]+)"|([^\s]+))', " ".join(output), re.I)
    return sorted({(quoted or plain).casefold().removesuffix(".lib") + ".lib" for quoted, plain in matches})


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--preflight", action="store_true", help="Read-only source, donor and toolchain validation")
    options = args.parse_args()
    require(os.name == "nt" and sys.dont_write_bytecode and not sys.flags.optimize, "Use normal Windows Python -B")
    require(not any(value for name, value in os.environ.items() if name.upper() in ("CL", "_CL_", "LINK")),
            "Inherited CL/_CL_/LINK options are forbidden before any child command")
    for encoding in ("mbcs", "utf-8-sig", "utf-8", "ascii"):
        codecs.lookup(encoding)
    gzip.compress(b"warm", mtime=0)
    scope = Scope()
    tool = scope.ref(Path(__file__).absolute())
    base_ref = pin(scope, BASE, BASE_SHA)
    base = scope.json(BASE)
    require(base["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and base["build_id"] == BASE_ID and
            len(base["compiler_inputs"]) == 545 and len(base["sources"]) == 81 and
            len(base["current_source_inputs"]) == 588 and len(base["implicit_libraries"]) == 8, "Baseline inventory differs")
    proof_refs = {name: pin(scope, PROJECT / relative, sha) for name, (relative, sha) in PROOFS.items()}
    proofs = {name: scope.json(row["path"]) for name, row in proof_refs.items()}
    component, syntax = proofs["component"], proofs["syntax"]
    require(component["status"] == "PASS_PORTABLE_NATIVE_RESTORE_CONTRACT" and
            component["sdk_or_host_or_window_executed"] is False and component["native_restore_approved"] is False,
            "Portable component proof scope differs")
    require(syntax["status"] == "PASS_ACTUAL_CURRENT_HOST_MAIN_SYNTAX_ONLY" and syntax["returncode"] == 0 and
            syntax["unique_dependencies"] == 465 and syntax["unknown_dependencies"] == syntax["changed_inputs"] == syntax["issues"] == [] and
            syntax["inputs_unchanged"] is True and syntax["objects_created"] == 0 and syntax["host_linked"] is False,
            "Actual current Host syntax proof differs")
    for name in ("response", "log", "dependency_report"):
        scope.sealed(syntax[name])
    current = {key(PROJECT / "Source/Host" / name): pin(scope, PROJECT / "Source/Host" / name, sha, size)
               for name, (size, sha) in {**CHANGED, **ADDED}.items()}
    changed_keys = {key(PROJECT / "Source/Host" / name) for name in CHANGED}
    added_keys = {key(PROJECT / "Source/Host" / name) for name in ADDED}
    old_inputs = {key(row["original_path"]): row for row in base["compiler_inputs"]}
    require(len(old_inputs) == 545 and changed_keys <= set(old_inputs) and not added_keys & set(old_inputs), "Source revision scope differs")
    receipt = proofs["source_change"]
    require(receipt["backup_roundtrip_verified"] is True and
            {key(row["path"]) for row in receipt["before"]} == {key(row["path"]) for row in receipt["after"]} == changed_keys,
            "Integration receipt source set differs")
    revisions = []
    for before in receipt["before"]:
        expected = old_inputs[key(before["path"])]
        require(all(before[name] == expected[name] for name in ("bytes", "sha256")), "Integration before bytes differ from b9")
        after = next(row for row in receipt["after"] if key(row["path"]) == key(before["path"]))
        require(all(after[name] == current[key(after["path"])][name] for name in ("bytes", "sha256")), "Integration after bytes differ")
        revisions.append(dict(before=historical(scope, before["backup"], before), after=current[key(after["path"])]))
    live, donors = {}, {}

    def remember(row):
        path = key(row["path"])
        expected = current[path] if path in changed_keys else row
        value = scope.sealed(expected)
        require(path not in live or live[path] == value, "Conflicting current source identity")
        live[path] = value
        return value

    for row in base["current_source_inputs"]:
        remember(row)
    for path in added_keys:
        live[path] = current[path]
    require(len(live) == 592, "Current input count differs from b9 plus four headers")
    for group in ("compiler_inputs", "sources", "provider_inputs", "system_libraries", "build_tools", "implicit_libraries"):
        for row in base[group]:
            require(within(row["path"], BASE_ROOT / "frozen"), "Donor escaped the frozen successful build")
            donors[key(row["path"])] = scope.sealed(row)
    for row in [*base["provider_reports"].values(), base["ui_assets"]]:
        require(within(row["path"], BASE_ROOT / "frozen"), "Metadata donor escaped the frozen successful build")
        donors[key(row["path"])] = scope.sealed(row)
    for name in ("compiler", "linker", "dumpbin", "executable", "map", "link_response", "link_log"):
        scope.sealed(base[name])
    require(base["link_response"]["sha256"] == "357a9550f3d8a38b0a37aab1a2c2d075801b50819e71f0bbe1e7f40b4d32095f" and
            {row["name"].casefold() for row in base["implicit_libraries"]} ==
            {"msvcrt.lib", "msvcprt.lib", "vcruntime.lib", "oldnames.lib", "bcrypt.lib", "kernel32.lib", "ucrt.lib", "uuid.lib"},
            "Successful UUID-inclusive link recipe differs")
    toolchain_names = set()
    for row in component["inputs"]:
        if Path(row["path"]).name.casefold() in ("cl.exe", "c1xx.dll", "c2.dll", "link.exe", "vcvars64.bat"):
            require(within(row["path"], VS), "Portable proof toolchain path escaped the expected compiler root")
            scope.sealed(row)
            toolchain_names.add(Path(row["path"]).name.casefold())
    require(toolchain_names == {"cl.exe", "c1xx.dll", "c2.dll", "link.exe", "vcvars64.bat"}, "Compiler frontend/environment proof inventory differs")
    scope.ref(VCVARS)
    cmd = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/cmd.exe"
    require(key(cmd) == key(Path(r"C:\Windows\System32\cmd.exe")), "Unexpected command interpreter location")
    scope.ref(cmd)
    metadata = {}
    recovery_root = PROJECT / "evidence/native_save_archive/host_relink/18bbd0dd26e70e623276/publication"
    historical_metadata = []
    for relative, size, sha, packed_name, packed_size, packed_sha in HISTORICAL_METADATA:
        path = PROJECT / relative
        backup = pin(scope, recovery_root / packed_name, packed_sha, packed_size)
        historical_metadata.append(historical(scope, backup, dict(path=str(path), bytes=size, sha256=sha)))
        metadata[key(path)] = (size, sha)
    publication = proofs["pair_publication"]
    require(len(publication["changed_metadata"]) == 2, "Latest metadata publication inventory differs")
    for row in publication["changed_metadata"]:
        require(key(row["before"]["path"]) == key(row["after"]["path"]) in metadata and row["roundtrip"] is True,
                "Unexpected latest metadata revision")
        historical(scope, row["backup"], row["before"])
        scope.sealed(row["after"])
    for row in base["protected_artifacts"]:
        if key(row["path"]) in metadata:
            require((row["bytes"], row["sha256"]) == metadata[key(row["path"])], "Historical metadata does not belong to b9")
        else:
            remember(row) if key(row["path"]) in changed_keys else scope.sealed(row)
    pair = proofs["pair_audit"]
    require(pair["status"] == "PASS_LATEST_HOST_SDK_PRIVATE_PREPARATION_PUBLICATION" and
            pair["run_id"] == "20261024T031412Z_e06aeb61ed6a", "Prepared pair provenance differs")
    for row in [*pair["proofs"], *pair["current_source_and_test_files"]]:
        scope.sealed(row)
    request_ref = pin(scope, REQUEST, REQUEST_SHA)
    request = scope.json(REQUEST)
    require(len(request["runtime_inputs"]) == 24 and key(request["cwd"]) == key(PROJECT / "Build/InteractiveGameRuntime" / pair["run_id"]),
            "Prepared runtime input scope differs")
    for row in request["runtime_inputs"]:
        require(within(row["path"], Path(request["cwd"])), "Runtime input escaped its owned prepared root")
        scope.sealed(row)
    native = component["retained_native_input"]
    require(native["bytes"] == 9612910 and native["sha256"] == "d4f51ae15c11bce5dbec849d271a3c6cc80c8ae9d88b8a3b2e35069b0193c07b" and
            within(native["path"], PROJECT / "Build/InteractiveGameRuntime/20261022T001546Z_7fba195072e4/sessions"), "Native fixture provenance differs")
    scope.sealed(native)
    for row in proofs["saved_game_observations"]["inputs"]:
        scope.sealed(row)
    old_host_audit = proofs["old_host_audit"]
    old_attestation = scope.json(scope.sealed(old_host_audit["attestation"])["path"])
    require(old_host_audit["retired_files_absent"] == 586 and old_host_audit["retired_directories_absent"] == 58 and
            old_attestation["status"] == "PASS_RELINKED_NATIVE_HOST_STATIC_ATTESTATION", "Old Host retention proof differs")
    for record in base["final_compilation"]["translation_units"]:
        require(not os.path.lexists(record["object"]["path"]), "Expected retired old Host object is present")
    records = base["final_compilation"]["translation_units"]
    require(tuple(row["translation_unit"] for row in records) == UNITS, "TU order differs")
    old_deps, response_texts = {}, {}
    old_frozen = {key(row["path"]): row for row in base["compiler_inputs"]}
    for index, record in enumerate(records):
        scope.sealed(record["response"])
        paths, _ = dependencies(scope, record["dependency_report"])
        require(paths <= set(old_frozen) and len(paths) == COUNTS[index] - (4 if index == 0 else 0), "Old TU dependency closure differs")
        old_deps[UNITS[index]] = paths
        response_texts[UNITS[index]] = scope.read(record["response"]["path"], 16384).decode("utf-8-sig")
    require(set.union(*old_deps.values()) == set(old_frozen), "Old dependency union does not cover 545 inputs")
    syntax_paths, _ = dependencies(scope, syntax["dependency_report"])
    normalized_old_main = {key(old_frozen[path]["original_path"]) for path in old_deps["host_main"]}
    normalized_syntax = {key(old_frozen[path]["original_path"]) if path in old_frozen else path for path in syntax_paths}
    require(normalized_syntax == normalized_old_main | added_keys, "Actual syntax proof does not establish the exact new four-header closure")
    link_text = scope.read(base["link_response"]["path"], 16384).decode("utf-8-sig")
    parser = parser_module(scope)
    generated = PROJECT / "Source/Host/UiPopupAssets.generated.h"
    generated_ref = scope.ref(generated)
    require(generated_ref["sha256"] == "333cf40c942e2545c83372084ed276e2aec11ab9fd7cbf4744f8c0c4e7c48da9", "Generated 67-payload header differs")
    arrays, order = parser.parse_catalog(scope.read(generated, 32 * 1024 * 1024))
    previous_pe = parser.PE(scope.read(base["executable"]["path"], 32 * 1024 * 1024))
    previous_catalog = catalog_summary(previous_pe.catalog(arrays, order))
    require(previous_catalog == old_attestation["catalog"] and not previous_pe.occurrences(MARKER), "Old PE/catalog lineage differs")
    # A tooling-only edit must not silently authorize recompiling these sources.
    signature = hashlib.sha256((BASE_SHA + PROOFS["component"][1] + PROOFS["syntax"][1] +
                               PROOFS["source_change"][1]).encode("ascii")).hexdigest()[:20]
    stage = STAGE_ROOT / signature
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + signature[:12]
    build = PROJECT / "Build/UiWindowHost" / identifier
    output = PROJECT / "evidence/ui_window_host" / identifier
    for path in (stage, build, output):
        ordinary(path, file=False)
        require(not os.path.lexists(path), "Single-use attempt already exists; do not repeat compilation")
    require(shutil.disk_usage(PROJECT).free >= 384 * 1024 * 1024, "Insufficient free space for the bounded private build")
    scope.stable()
    if options.preflight:
        print(json.dumps(dict(status="PASS_CURRENT_NATIVE_RESTORE_HOST_PREFLIGHT", signature=signature,
              current_input_count=592, compiler_dependency_count=549, source_manifest_count=85,
              changed_sources=3, added_headers=4, translation_units=5, implicit_libraries=8,
              planned_child_commands=7, historical_metadata_recoveries=2, protected_runtime_inputs=24,
              unique_pinned_inputs=len(scope.rows), created_files=0, child_commands=0,
              host_or_sdk_or_window_executed=False, full_engine_goal_complete=False)))
        return 0
    scope.roots = (build, stage, output)
    scope.parents = {key(STAGE_ROOT), key(STAGE_ROOT.parent)}
    STAGE_ROOT.mkdir(parents=True, exist_ok=True)
    stage.mkdir(); build.mkdir(); output.mkdir()
    protected = list(scope.rows.values())
    completed, objects, materialized, commands = [], [], {}, scope.commands

    def relocate(path):
        require(within(path, BASE_ROOT), "Relocation source escaped the successful build")
        return build / Path(path).relative_to(BASE_ROOT)

    def replace_root(text):
        value = text.replace(str(BASE_ROOT), str(build)).replace(BASE_ROOT.as_posix(), build.as_posix())
        require(str(BASE_ROOT) not in value and BASE_ROOT.as_posix() not in value, "Old build path remains in a response")
        return value

    def freeze(row, source=None):
        target = relocate(row["path"])
        if key(target) in materialized:
            return materialized[key(target)]
        ordinary(target, file=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source is None:
            require(key(row["path"]) in donors, "Unregistered frozen donor")
            scope.links[key(target)] = key(row["path"])
            os.link(row["path"], target)
            method = "attested_snapshot_hardlink"
        else:
            raw = scope.read(source, 256 * 1024)
            with target.open("xb") as stream:
                stream.write(raw)
            scope.copies.add(key(target)); os.chmod(target, stat.S_IREAD)
            method = "owned_changed_source_copy"
        actual = scope.ref(target)
        expected = current[key(source)] if source is not None else row
        require(all(actual[name] == expected[name] for name in ("bytes", "sha256")), "Materialized content differs")
        require(source is not None or actual["file_identity"] == donors[key(row["path"])]["file_identity"], "Snapshot did not reuse its donor identity")
        require(source is None or actual["file_identity"] != current[key(source)]["file_identity"], "Changed live source was hardlinked")
        result = {**row, **actual, "materialization": method}
        result.pop("reused_from_path", None)
        if source is None:
            result["reused_from_path"] = row["path"]
        materialized[key(target)] = result
        return result

    def execute(command, cwd, log, env=None, *, environment=False):
        scope.pending = dict(command=[str(word) for word in command], cwd=str(cwd))
        try:
            result = subprocess.run(scope.pending["command"], cwd=cwd, env=env, capture_output=True,
                                    timeout=300, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        except subprocess.TimeoutExpired as error:
            log.write_bytes((error.stdout or b"") + (error.stderr or b"") if not environment else (error.stderr or b""))
            raise
        finally:
            scope.pending = None
        commands[-1]["returncode"] = result.returncode
        # The environment command emits inherited secrets on stdout; never persist it.
        log.write_bytes(result.stderr if environment else result.stdout + result.stderr)
        require(result.returncode == 0, "Child failed; retained log: " + str(log))
        if not environment:
            require(not re.search(r"\bwarning\s+(?:C|LNK)\d+", (result.stdout + result.stderr).decode("mbcs", errors="replace"), re.I),
                    "Compiler/linker warning; retained log: " + str(log))
        return result

    try:
        planned = [([str(cmd), "/d", "/c", str(build / "read_build_environment.cmd")], build)]
        planned += [([base["compiler"]["path"], "@" + str(relocate(row["response"]["path"]))],
                     relocate(row["response"]["path"]).parent) for row in records]
        planned += [([base["linker"]["path"], "@" + str(relocate(base["link_response"]["path"]))],
                     relocate(base["link_response"]["path"]).parent)]
        scope.allowed_commands = {(tuple(words), key(cwd)) for words, cwd in planned}
        require(len(scope.allowed_commands) == 7, "Planned exact command inventory differs")
        write(stage / "started.json", dict(schema="zerosis.native_restore.host_build_started.v1", utc=datetime.now(timezone.utc).isoformat(),
              signature=signature, build_id=identifier, builder=tool, baseline_build=base_ref, proofs=proof_refs,
              current_inputs=list(live.values()), protected_artifacts=protected, source_revisions=revisions,
              historical_metadata_recovery=historical_metadata, frozen_donors=list(donors.values()),
              planned_commands=[dict(command=words, cwd=str(cwd)) for words, cwd in planned],
              no_automatic_retry=True, host_or_sdk_or_window_execution_allowed=False, full_engine_goal_complete=False))
        compiler_inputs = [freeze(row, row["original_path"] if key(row["original_path"]) in changed_keys else None)
                           for row in base["compiler_inputs"]]
        template = next(row for row in base["compiler_inputs"] if Path(row["original_path"]).name == "SdkGameRestore.h")
        new_rows = []
        for name in ADDED:
            source = PROJECT / "Source/Host" / name
            row = {**template, "path": str(Path(template["path"]).with_name(name)), "original_path": str(source),
                   "relative_path": str(Path(template["relative_path"]).with_name(name))}
            new_rows.append(freeze(row, source))
        compiler_inputs += new_rows
        sources = []
        for row in base["sources"]:
            value = freeze(row, row["original_source"] if key(row["original_source"]) in changed_keys else None)
            sources.append({**value, "original_source": row["original_source"], "relative_path": row["relative_path"]})
        sources += [{**row, "original_source": row["original_path"]} for row in new_rows]
        providers = [freeze(row) for row in base["provider_inputs"]]
        systems = [freeze(row) for row in base["system_libraries"]]
        tools = [freeze(row) for row in base["build_tools"]]
        implicit = [freeze(row) for row in base["implicit_libraries"]]
        provider_reports = {name: freeze(row) for name, row in base["provider_reports"].items()}
        assets = freeze(base["ui_assets"])
        frozen = build / "frozen"
        setup = build / "read_build_environment.cmd"
        with setup.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(f'@echo off\ncall "{VCVARS}" >nul\nif errorlevel 1 exit /b 1\nset\n')
        initialized = execute([cmd, "/d", "/c", setup], build, stage / "environment.stderr.log", environment=True)
        env = {name.upper(): value for name, value in os.environ.items()}
        for line in initialized.stdout.decode("mbcs", errors="replace").splitlines():
            if "=" in line and not line.startswith("="):
                name, value = line.split("=", 1); env[name.upper()] = value
        require(not any(env.get(name) for name in ("CL", "_CL_", "LINK")), "Initialized CL/_CL_/LINK options are forbidden")
        compiler = shutil.which("cl.exe", path=env.get("PATH"))
        require(compiler is not None and key(compiler) == key(base["compiler"]["path"]), "Initialized compiler differs")
        compiler = base["compiler"]["path"]
        scope.sealed(base["compiler"]); scope.sealed(base["linker"])
        env["INCLUDE"] = ";".join(str(frozen / "include_roots" / ("system_%02d" % index)) for index in range(len(base["system_include_roots"])))
        env["LIB"] = str(frozen / "implicit_libraries"); env["LIBPATH"] = ""
        (build / "tmp").mkdir(); env["TMP"] = env["TEMP"] = str(build / "tmp"); env["VSLANG"] = "1033"
        closure = {key(row["path"]) for row in compiler_inputs}
        library_names = {row["name"].casefold() for row in implicit} | {Path(row["path"]).name.casefold() for row in providers + systems}
        union = set()
        for index, (name, stem, old) in enumerate(zip(UNITS, STEMS, records)):
            response = relocate(old["response"]["path"])
            dependency = relocate(old["dependency_report"]["path"])
            response.parent.mkdir(parents=True); (response.parent / "obj").mkdir()
            with response.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(replace_root(response_texts[name]))
            response_before = scope.ref(response)
            execute([compiler, "@" + str(response)], response.parent, stage / ("compile_" + name + ".log"), env)
            scope.sealed(response_before)
            expected = {key(relocate(path)) for path in old_deps[name]}
            if name == "host_main":
                expected.update(key(row["path"]) for row in new_rows)
            actual, visits = dependencies(scope, scope.ref(dependency))
            require(actual == expected and actual <= closure and len(actual) == COUNTS[index], "Actual " + name + " dependency set differs")
            union.update(actual)
            object_path = response.parent / "obj" / (stem + ".obj")
            raw = scope.read(object_path, 64 * 1024 * 1024)
            coff = parser.coff(raw)
            defaults = object_defaults(raw)
            require(coff["machine_hex"] == "0x8664" and set(defaults) <= library_names, "COFF requests an unpinned library")
            row = dict(translation_unit=name, command=[str(compiler), "@" + str(response)], response=scope.ref(response),
                       dependency_report=scope.ref(dependency), log=scope.ref(stage / ("compile_" + name + ".log")),
                       object=scope.ref(object_path), returncode=0, expected_dependency_count=len(expected),
                       actual_dependency_count=len(actual), dependency_visits=visits, default_libraries=defaults,
                       coff_machine=coff["machine_hex"], coff_sections=coff["section_count"])
            completed.append(row); objects.append(row["object"])
            write(stage / ("compiled_" + name + ".json"), row)
            print(json.dumps(dict(phase="compiled", translation_unit=name, object_bytes=row["object"]["bytes"])), flush=True)
        require(union == closure and len(closure) == 549 and len(sources) == 85, "Final compiler input union differs")
        link_response = relocate(base["link_response"]["path"])
        rewritten = replace_root(link_text)
        linked_objects = re.findall(r'^"([^"\n]+\.obj)"$', rewritten.replace("\r\n", "\n"), re.I | re.M)
        require([key(path) for path in linked_objects] == [key(row["path"]) for row in objects], "Link response does not consume exactly the new five objects")
        with link_response.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rewritten)
        link_response_before = scope.ref(link_response)
        before_link = [scope.sealed(row) for row in objects]
        execute([base["linker"]["path"], "@" + str(link_response)], link_response.parent, stage / "link.log", env)
        scope.sealed(link_response_before)
        require([scope.sealed(row) for row in objects] == before_link, "Link changed a compiled object")
        executable, mapfile = relocate(base["executable"]["path"]), relocate(base["map"]["path"])
        pe = parser.PE(scope.read(executable, 32 * 1024 * 1024))
        imports = pe.imports()
        require(len(imports) == len(set(imports)) and set(imports) == set(previous_pe.imports()), "Actual PE imports differ from the retained Host")
        catalog = catalog_summary(pe.catalog(arrays, order))
        require(all(catalog[name] == previous_catalog[name] for name in ("entry_count", "stride", "total_payload_bytes", "ordered_payload_manifest_sha256")),
                "New PE does not preserve the exact ordered 67 payloads")
        marker_rvas = pe.occurrences(MARKER)
        require(len(marker_rvas) == 1, "New PE lacks one read-only restore-contract marker")
        map_raw = scope.read(mapfile, 16 * 1024 * 1024)
        map_text = map_raw.decode("mbcs", errors="strict")
        mapped_libs = {match.casefold().removesuffix(".lib") + ".lib" for match in re.findall(r"\s([\w.-]+):\S+\.(?:obj|dll)\s*$", map_text, re.I | re.M)}
        require(mapped_libs <= library_names, "Link map reports an unpinned library")
        imports_log = stage / "imports.static.json"
        write(imports_log, dict(source="PURE_FILE_BACKED_PE_IMPORT_DIRECTORY", dependencies=imports, image=scope.ref(executable)))
        for row in materialized.values():
            scope.sealed(row)
        scope.stable()
        require(len(commands) == 7 and not scope.allowed_commands and all(row["returncode"] == 0 for row in commands), "Exact seven-command build scope differs")
        current_by_original = {key(row["original_source"]): row for row in sources}
        window_sources = [current_by_original[key(row["original_source"])] for row in base["window_sources"]]
        shared_lua = next(row for row in provider_reports.values() if key(row.get("original_path", "")) == key(base["shared_lua_build"]["original_path"]))
        report = dict(schema=base["schema"], status="UI_WINDOW_HOST_CANDIDATE_BUILT", build_id=identifier,
            baseline_build=base_ref, restore_contract_builder=tool, native_restore_contract_component=proof_refs["component"],
            actual_host_syntax=proof_refs["syntax"], source_change=proof_refs["source_change"],
            compiler=scope.sealed(base["compiler"]), linker=scope.sealed(base["linker"]), dumpbin=scope.sealed(base["dumpbin"]),
            compiler_version="MSVC x64; exact per-unit C++14/C++17 and source charset; /O2; /MD",
            toolchain={**base["toolchain"], "language": "EXACT_RETAINED_PER_TRANSLATION_UNIT_CXX14_AND_CXX17"},
            definitions=base["definitions"], system_include_roots=base["system_include_roots"],
            compiler_inputs=compiler_inputs, compiler_dependency_count=549, sources=sources, window_sources=window_sources,
            provider_inputs=providers, system_libraries=systems, libraries=providers + systems,
            system_library_names=base["system_library_names"], implicit_libraries=implicit,
            implicit_libraries_before=[donors[key(row["path"])] | {"name": row["name"]} for row in base["implicit_libraries"]],
            implicit_libraries_after=[scope.sealed(row) | {"name": row["name"]} for row in base["implicit_libraries"]],
            actual_implicit_library_namesfrommap=sorted(mapped_libs & {row["name"].casefold() for row in implicit}),
            build_tools=tools, provider_reports=provider_reports, shared_lua_build=shared_lua, ui_assets=assets,
            ui_asset_preparation=dict(status="UNCHANGED_ATTESTED_67_PAYLOAD_CATALOG_REUSED", executed=False),
            dependency_discovery=dict(executed=False, reason="Exact old five-TU dependency graphs plus the four headers observed by current actual HostMain syntax proof."),
            final_compilation=dict(translation_units=completed), final_dependency_reports={row["translation_unit"]: row["dependency_report"] for row in completed},
            response=completed[0]["response"], dependency_report=completed[0]["dependency_report"],
            link_response=scope.ref(link_response), link_log=scope.ref(stage / "link.log"), map=scope.ref(mapfile),
            executable={**scope.ref(executable), "pe": dict(architecture="x64", pe_format="PE32+", is_dll=False)},
            imports=dict(dependencies=imports, log=scope.ref(imports_log), source="PURE_PYTHON_STATIC_PE"),
            catalog=catalog, restore_contract_marker=dict(ascii=MARKER.decode("ascii"), rva=marker_rvas[0], inclusion_evidence_only=True),
            link_snapshot=dict(response=scope.ref(link_response), objects_before=before_link, objects_after=objects, returncode=0),
            current_source_inputs=list(live.values()), protected_artifacts=protected,
            sources_changed_from_baseline=[current[path] for path in sorted(changed_keys)], new_source_inputs=[current[path] for path in sorted(added_keys)],
            source_revision_provenance=revisions, historical_metadata_recovery=historical_metadata,
            final_environment={name: env.get(name, "") for name in ("INCLUDE", "LIB", "LIBPATH", "TMP", "TEMP", "VSLANG", "CL", "_CL_", "LINK")},
            frozen_input_reuse=dict(hardlinked_files=sum(row["materialization"] == "attested_snapshot_hardlink" for row in materialized.values()),
                hardlinked_logical_bytes=sum(row["bytes"] for row in materialized.values() if row["materialization"] == "attested_snapshot_hardlink"),
                copied_source_bytes=sum(row["bytes"] for row in materialized.values() if row["materialization"] == "owned_changed_source_copy"),
                donor_content_and_metadata_preserved=True),
            scope="Five current Host compilations and one private x64 link; static PE/67-payload/contract-marker verification only.",
            source_inputs_unchanged=True, provider_inputs_unchanged=True, host_runtime_executed=False, gamecore_loaded=False,
            sdk_linked=False, mods_updated=False, stage_updated=False, default_promoted=False, sdk_restore_verified=False,
            native_restore_approved=False, full_engine_goal_complete=False, forbidden_access_attempts=scope.denied)
        result_path = output / "build_result.json"
        write(result_path, report)
        run = dict(schema="zerosis.native_restore.host_build_run.v1", status="PASS_CURRENT_NATIVE_RESTORE_HOST_BUILD_ONLY",
                   utc=datetime.now(timezone.utc).isoformat(), build_id=identifier, builder=tool, build_result=scope.ref(result_path),
                   commands=commands, actual_objects=objects, catalog=catalog, restore_contract_marker=report["restore_contract_marker"],
                   compiler_dependency_count=549, actual_dependency_counts=list(COUNTS), current_source_count=592,
                   source_manifest_count=85, protected_runtime_inputs_unchanged=24, retained_native_input_unchanged=native,
                   input_files_unchanged=True, objects_retained_for_separate_cleanup=True, no_automatic_retry=True,
                   host_or_sdk_or_window_executed=False, original_game_or_user_state_accessed=False, network_used=False,
                   sdk_restore_verified=False, native_restore_approved=False, default_promoted=False, full_engine_goal_complete=False,
                   forbidden_access_attempts=scope.denied)
        write(stage / "run.json", run)
        print(json.dumps(dict(status=run["status"], build_id=identifier, build_result=scope.ref(result_path),
                              run=scope.ref(stage / "run.json"), executable=scope.ref(executable), child_commands=7)), flush=True)
        return 0
    except BaseException as error:
        write(stage / "failure.json", dict(schema="zerosis.native_restore.host_build_failure.v1", status="FAILED_DO_NOT_REPLAY",
              utc=datetime.now(timezone.utc).isoformat(), error_type=type(error).__name__, error=str(error)[:4000],
              commands=commands, completed_translation_units=completed, forbidden_access_attempts=scope.denied,
              objects_and_logs_retained=True, compilation_retry_allowed=False, host_or_sdk_or_window_executed=False,
              full_engine_goal_complete=False))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
