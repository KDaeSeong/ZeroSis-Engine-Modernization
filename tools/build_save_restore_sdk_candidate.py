"""Build a uniquely isolated SaveRestoreSDK candidate on top of NewGameSDK.

This tool is intentionally explicit: it never writes to the accepted SDK or
NewGameSDK directories, and it never changes the active Stage bundle.
"""
from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


ACCEPTED = PROJECT / "evidence/sdk_x64/attempts/attempt_037/build_result.json"
NEW_GAME = PROJECT / "evidence/new_game_sdk/build_result.json"
SHARED_LUA = PROJECT / "evidence/shared_lua_runtime/build_result.json"
SAVE_RESTORE_SPEC = PROJECT / "Source/Porting/save_restore_patches.json"
PATCH_BUILDER = PROJECT / "tools/define_save_restore_patches.py"
SDK_ORIGINAL = PROJECT / "Source/SDK_BNW_Original"
SDK_PORTED = PROJECT / "Source/SDK_BNW_x64"
SAVE_RESTORE_ROOT = PROJECT / "evidence/save_restore_sdk"
SAVE_RESTORE_BUILD = PROJECT / "Build/SaveRestoreSDK"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
EXPECTED_STATUS = "SDK_SAVE_RESTORE_PATCHES_PROPOSED_NOT_APPLIED"
EXPECTED_TUS = {
    "CvGameCoreDLL_Expansion2/CvPreGame.cpp",
    "CvGameCoreDLL_Expansion2/CvTeam.cpp",
}


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def quote_include_graph_contains(root: Path, target_name: str, include_dirs: list[Path]) -> bool:
    """Resolve quoted includes from a PCH header, limited to source-local files."""
    pattern = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.M)
    pending = [root.resolve()]
    visited = set()
    target_key = target_name.casefold()
    while pending:
        current = pending.pop()
        key = str(current).casefold()
        if key in visited:
            continue
        visited.add(key)
        if current.name.casefold() == target_key:
            return True
        try:
            text = current.read_bytes().decode("latin1")
        except OSError:
            continue
        for include in pattern.findall(text):
            candidates = [current.parent / include, *(directory / include for directory in include_dirs)]
            found = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
            if found is not None and str(found).casefold() not in visited:
                pending.append(found)
    return False


def sdk_baseline_text(relative: str, baseline_spec: dict) -> str:
    original = SDK_ORIGINAL / relative
    raw = original.read_bytes()
    text = raw.decode("latin1")
    if not relative.startswith("CvGameCoreDLL_Expansion2/"):
        raise RuntimeError("Unexpected SDK path: " + relative)
    for patch in baseline_spec["patches"]:
        if patch["file"] != relative:
            continue
        if text.count(patch["old"]) != patch["count"]:
            raise RuntimeError("Accepted SDK baseline context mismatch: " + patch["id"])
        text = text.replace(patch["old"], patch["new"])
    expected_ported = SDK_PORTED / relative
    if not expected_ported.is_file() or expected_ported.read_bytes() != text.encode("latin1"):
        raise RuntimeError("Current x64 SDK source differs from reconstructed attempt_037: " + relative)
    return text


def apply_save_restore_patches(spec: dict, baseline_spec: dict) -> tuple[dict[str, str], list[dict]]:
    patches = spec.get("patches")
    target_files = spec.get("target_files")
    if not isinstance(patches, list) or not patches or not isinstance(target_files, list):
        raise RuntimeError("Save-restore patch plan is empty or malformed")
    files = sorted({row.get("file") for row in patches})
    if files != sorted(target_files):
        raise RuntimeError("Patch target_files do not match patch rows")
    texts = {relative: sdk_baseline_text(relative, baseline_spec) for relative in files}
    for row in patches:
        relative = row["file"]
        original = SDK_ORIGINAL / relative
        if row.get("source_sha256") != digest(original):
            raise RuntimeError("Patch source hash changed: " + row.get("id", "<unnamed>"))
        before = row["old"]
        if texts[relative].count(before) != row.get("count"):
            raise RuntimeError("Patch context or count mismatch: " + row.get("id", "<unnamed>"))
        texts[relative] = texts[relative].replace(before, row["new"])
    return texts, patches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace-player-save', action='store_true', help='Trace isolated Player Read/Write stream positions for diagnosis')
    parser.add_argument('--trace-player-id', type=int, choices=range(64), default=0)
    parser.add_argument('--no-update-latest', action='store_true', help='Keep a diagnostic build from replacing the current candidate pointer')
    args = parser.parse_args()
    if args.trace_player_id and not args.trace_player_save:parser.error('A trace player ID requires --trace-player-save')
    build_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    build_dir = SAVE_RESTORE_BUILD / build_id
    evidence_dir = SAVE_RESTORE_ROOT / build_id
    # exist_ok=False makes accidental reuse a hard failure instead of an overwrite.
    build_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir.mkdir(parents=True, exist_ok=False)
    report_path = evidence_dir / "build_result.json"
    report: dict = {"status": "SAVE_RESTORE_SDK_CANDIDATE_BUILDING", "build_id": build_id}
    try:
        accepted = json.loads(ACCEPTED.read_text(encoding="utf-8"))
        new_game = json.loads(NEW_GAME.read_text(encoding="utf-8"))
        shared_lua = json.loads(SHARED_LUA.read_text(encoding="utf-8"))
        spec = json.loads(SAVE_RESTORE_SPEC.read_text(encoding="utf-8"))
        baseline_spec_path = Path(spec["baseline"]["path"])
        baseline_spec = json.loads(baseline_spec_path.read_text(encoding="utf-8"))
        for value in (accepted, new_game, shared_lua):
            check_artifacts(value)
        if accepted.get("status") != "SDK_X64_ALL_OBJECTS_COMPILED" or accepted.get("attempt") != 37:
            raise RuntimeError("Required accepted attempt_037 build is not current")
        if new_game.get("status") != "NEW_GAME_SDK_CANDIDATE_LINKED":
            raise RuntimeError("A linked NewGameSDK candidate is required")
        if shared_lua.get("status") != "SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
            raise RuntimeError("A shared Lua runtime candidate is required")
        if spec.get("status") != EXPECTED_STATUS:
            raise RuntimeError("Save-restore patch plan is not in the proposed, reviewable state")
        baseline_sha256 = digest(baseline_spec_path)
        if spec.get("baseline", {}).get("sha256") != baseline_sha256:
            raise RuntimeError("Save-restore patch plan baseline does not match accepted SDK patch plan")
        if accepted.get("patch_specification", {}).get("sha256") != baseline_sha256:
            raise RuntimeError("Accepted attempt_037 patch hash differs from frozen save-restore baseline")
        if not PATCH_BUILDER.is_file():
            raise RuntimeError("Save-restore patch builder is missing")
        if spec.get("recipe", {}).get("sha256") and spec["recipe"]["sha256"] != digest(PATCH_BUILDER):
            raise RuntimeError("Save-restore patch builder changed after patch-plan generation")
        if len(baseline_spec.get("patches", [])) != 693:
            raise RuntimeError("attempt_037 patch baseline count changed")

        affected = spec.get("translation_units")
        if not isinstance(affected, list):
            raise RuntimeError("Save-restore patch plan lacks translation_units")
        affected = sorted(set(affected))
        if not affected or not EXPECTED_TUS.issubset(set(affected)):
            raise RuntimeError("Required serialization translation units are missing")
        directly_patched = {row["file"] for row in spec["patches"] if row["file"].lower().endswith(".cpp")}
        helper_rows = [row for row in spec["patches"] if row["file"].lower().endswith(".h")]
        caller_units = {caller["file"] for row in helper_rows
                        for caller in row.get("caller_evidence", []) if caller.get("file", "").lower().endswith(".cpp")}
        expected_translation_units = directly_patched | caller_units
        if set(affected) != expected_translation_units:
            raise RuntimeError("translation_units do not cover exactly the patched/caller serialization units")
        helper_required_tus = {caller["file"] for row in helper_rows
                               for caller in row.get("caller_evidence", []) if caller.get("file", "").lower().endswith(".cpp")}
        if any(not x.startswith("CvGameCoreDLL_Expansion2/") or not x.lower().endswith(".cpp")
               or not (SDK_ORIGINAL / x).is_file() for x in affected):
            raise RuntimeError("Serialization translation-unit path is invalid")
        contents, patches = apply_save_restore_patches(spec, baseline_spec)
        if args.trace_player_save:
            relative = 'CvGameCoreDLL_Expansion2/CvPlayer.cpp'
            traced = contents.get(relative, sdk_baseline_text(relative, baseline_spec))
            for operation in ('Read', 'Write'):
                signature = 'void CvPlayer::' + operation + '(FDataStream& kStream)' + (' const' if operation == 'Write' else '')
                start = traced.index('\r\n{', traced.index(signature)) + 3
                end = traced.index('\r\n}', start)
                body = traced[start:end]
                first_line = traced[:start].count('\n') + 1
                lines = body.splitlines(keepends=True)
                for index, line in enumerate(lines):
                    lines[index] = re.sub(r'\bkStream\b', 'zeroSisTraceStream(' + str(first_line + index) + ')', line)
                helper = ('\r\n\tconst auto zeroSisTraceStream = [&](int line) -> FDataStream& {\r\n'
                          '\t\tif (GetID() == ' + str(args.trace_player_id) + ' || GetID() == NO_PLAYER) fprintf(stderr, "SDK_PLAYER_' + operation.upper() + '_POSITION=%d,%u\\n", line, static_cast<unsigned>(kStream.GetPosition()));\r\n'
                          '\t\treturn kStream;\r\n\t};\r\n')
                traced = traced[:start] + helper + ''.join(lines) + traced[end:]
            contents[relative] = traced
        patch_spec_before = digest(SAVE_RESTORE_SPEC)
        patch_builder_before = digest(PATCH_BUILDER)
        builder_before = digest(Path(__file__).resolve())
        frozen_dir = evidence_dir / "frozen"
        frozen_dir.mkdir()
        frozen_spec = frozen_dir / "save_restore_patches.json"
        frozen_patch_builder = frozen_dir / "define_save_restore_patches.py"
        frozen_builder = frozen_dir / "build_save_restore_sdk_candidate.py"
        frozen_spec.write_bytes(SAVE_RESTORE_SPEC.read_bytes())
        frozen_patch_builder.write_bytes(PATCH_BUILDER.read_bytes())
        frozen_builder.write_bytes(Path(__file__).resolve().read_bytes())
        if (digest(frozen_spec) != patch_spec_before or digest(frozen_patch_builder) != patch_builder_before
                or digest(frozen_builder) != builder_before):
            raise RuntimeError("Candidate plan freeze copy does not match its source")
        source_pairs = []
        for relative in sorted(set(contents) | set(affected)):
            original = SDK_ORIGINAL / relative
            ported = SDK_PORTED / relative
            source_pairs.extend((artifact(original), artifact(ported)))

        overlay = build_dir / "Source/CvGameCoreDLL_Expansion2"
        overlay.mkdir(parents=True, exist_ok=False)
        sources = []
        for relative in sorted(contents):
            target = overlay / Path(relative).name
            target.write_bytes(contents[relative].encode("latin1"))
            sources.append(target)
        for relative in affected:
            filename = Path(relative).name
            target = overlay / filename
            if relative not in contents:
                source_text = sdk_baseline_text(relative, baseline_spec)
                target.write_bytes(source_text.encode("latin1"))
            sources.append(target)
        helper = overlay / "CvInfosSerializationHelper.h"
        if not helper.exists() or digest(helper) == digest(SDK_PORTED / "CvGameCoreDLL_Expansion2/CvInfosSerializationHelper.h"):
            raise RuntimeError("Patched serialization helper overlay was not produced")
        pch_header = SDK_PORTED / "CvGameCoreDLL_Expansion2/CvGameCoreDLLPCH.h"
        include_dirs = [SDK_PORTED / "CvGameCoreDLL_Expansion2", PROJECT / "Source/Porting",
            PROJECT / "Source/LuaBorrowed", SDK_PORTED / "CvWorldBuilderMap/include",
            SDK_PORTED / "CvGameCoreDLLUtil/include", SDK_PORTED / "CvLocalization/include",
            SDK_PORTED / "CvGameDatabase/include", SDK_PORTED / "FirePlace/include",
            SDK_PORTED / "ThirdPartyLibs/Lua51/include"]
        if quote_include_graph_contains(pch_header, "CvInfosSerializationHelper.h", include_dirs):
            raise RuntimeError("Serialization helper reaches the PCH include graph; isolated TU strategy is invalid")
        if (not quote_include_graph_contains(helper, "CvCheckedNarrow.h", [overlay, *include_dirs])
                and not quote_include_graph_contains(pch_header, "CvCheckedNarrow.h", include_dirs)):
            raise RuntimeError("CvChecked declarations are unavailable to helper template users")

        env, compiler_name = environment_for(VS, "x64", build_dir)
        compiler = Path(compiler_name)
        env["VSLANG"] = "1033"
        original_response = Path(accepted["executions"][1]["response"])
        flags = [line for line in original_response.read_text(encoding="utf-8").splitlines()
                 if not line.startswith('"') and not line.startswith("/Fo") and line != "/MP4"]
        units = []
        for relative in affected:
            source = overlay / Path(relative).name
            obj = build_dir / (source.stem + ".obj")
            response = build_dir / (source.stem + ".rsp")
            dependencies = build_dir / (source.stem + "_dependencies.json")
            response.write_text("\n".join(flags + [f'/Fo"{obj}"', f'/sourceDependencies "{dependencies}"', f'"{source}"']) + "\n", encoding="utf-8")
            result = run([compiler, "@" + str(response)], cwd=overlay, env=env, timeout=180)
            log = evidence_dir / (source.stem + ".log")
            log.write_bytes(result.stdout + result.stderr)
            output = read_text(log)
            if result.returncode or re.search(r"warning\s+C(?:4244|4267|4838)\b", output):
                raise RuntimeError("Save-restore compile failed or emitted a width warning: " + source.stem + "\n" + output[-7000:])
            consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
            helper_inputs = {Path(p).resolve() for p in consumed["Includes"]
                             if Path(p).name.casefold() == "cvinfosserializationhelper.h"}
            if ((relative in helper_required_tus and helper_inputs != {helper.resolve()})
                    or any(path != helper.resolve() for path in helper_inputs)):
                raise RuntimeError("Compile did not consume only the patched helper overlay: " + source.stem)
            units.append({"source": artifact(source), "object": artifact(obj), "response": artifact(response),
                "log": artifact(log), "dependencies": artifact(dependencies),
                "compiler_inputs": [artifact(Path(p)) for p in [consumed["Source"], *consumed["Includes"]]]})

        response = Path(new_game["link_response"]["path"])
        link_text = response.read_text(encoding="utf-8")
        for unit in units:
            name = Path(unit["source"]["path"]).stem
            old_object = next(Path(row["path"]) for row in accepted["objects"] if Path(row["path"]).stem == name)
            if link_text.count('"' + str(old_object) + '"') != 1:
                raise RuntimeError("NewGameSDK link response does not contain exactly one accepted object: " + name)
            link_text = link_text.replace('"' + str(old_object) + '"', '"' + unit["object"]["path"] + '"')
        dll = build_dir / "CvGameCoreDLL_Expansion2_x64.dll"
        map_file = dll.with_suffix(".map")
        for option, target in (("OUT", dll), ("IMPLIB", dll.with_suffix(".lib")), ("MAP", map_file)):
            link_text, count = re.subn(r"^/" + option + r":[^\r\n]+", lambda _: f'/{option}:"{target}"', link_text, flags=re.M)
            if count != 1:
                raise RuntimeError("NewGameSDK link output option differs: " + option)
        link_response = build_dir / "link.rsp"
        link_response.write_text(link_text, encoding="utf-8")
        linked = run([compiler.with_name("link.exe"), "@" + str(link_response)], cwd=build_dir, env=env, timeout=180)
        link_log = evidence_dir / "link.log"
        link_log.write_bytes(linked.stdout + linked.stderr)
        if linked.returncode:
            raise RuntimeError("Candidate DLL link failed: " + read_text(link_log)[-7000:])
        inspected = checked_run([compiler.with_name("dumpbin.exe"), "/dependents", dll], cwd=build_dir, env=env)
        imports_log = evidence_dir / "imports.log"
        imports_log.write_bytes(inspected.stdout + inspected.stderr)
        imports = re.findall(r"^\s+([\w.-]+\.dll)\s*$", read_text(imports_log), re.M | re.I)
        if "ZeroSisLua51_x64.dll" not in imports or "dummynode_" in read_text(map_file):
            raise RuntimeError("Candidate no longer imports the shared Lua runtime")
        if digest(SAVE_RESTORE_SPEC) != patch_spec_before or digest(PATCH_BUILDER) != patch_builder_before or digest(Path(__file__).resolve()) != builder_before:
            raise RuntimeError("Frozen save-restore plan or builder changed while candidate was being built")
        check_artifacts([accepted, new_game, shared_lua])

        report = {
            "status": "SAVE_RESTORE_SDK_CANDIDATE_LINKED", "build_id": build_id,
            "builder": {**artifact(frozen_builder), "original_source": str(Path(__file__).resolve())},
            "patch_specification": {**artifact(frozen_spec), "original_source": str(SAVE_RESTORE_SPEC)},
            "patch_builder": {**artifact(frozen_patch_builder), "original_source": str(PATCH_BUILDER)},
            "accepted_build": artifact(ACCEPTED), "new_game_sdk_build": artifact(NEW_GAME),
            "shared_lua_build": artifact(SHARED_LUA), "sdk_baseline_patch_specification": artifact(baseline_spec_path),
            "source_overlay": [artifact(path) for path in sources], "source_pairs": source_pairs,
            "consumed_inputs": [artifact(path) for path in (ACCEPTED, NEW_GAME, SHARED_LUA,
                baseline_spec_path, original_response, Path(new_game["link_response"]["path"]),
                Path(shared_lua["gamecore_link_response"]["path"]),
                frozen_spec, frozen_patch_builder, frozen_builder)] + source_pairs,
            "mutable_source_freeze": {
                "patch_specification": {"path": str(SAVE_RESTORE_SPEC), "sha256_before": patch_spec_before,
                                        "sha256_after": digest(SAVE_RESTORE_SPEC), "unchanged": digest(SAVE_RESTORE_SPEC) == patch_spec_before},
                "patch_builder": {"path": str(PATCH_BUILDER), "sha256_before": patch_builder_before,
                                  "sha256_after": digest(PATCH_BUILDER), "unchanged": digest(PATCH_BUILDER) == patch_builder_before},
                "candidate_builder": {"path": str(Path(__file__).resolve()), "sha256_before": builder_before,
                                      "sha256_after": digest(Path(__file__).resolve()), "unchanged": digest(Path(__file__).resolve()) == builder_before},
            },
            "units": units,
            "compiler": artifact(compiler), "pch_reused": artifact(PROJECT / "Build/SDK_x64/attempt_037/GameCore_x64.pch"),
            "link_response": artifact(link_response), "link_log": artifact(link_log),
            "gamecore": {**artifact(dll), "pe": pe_header(dll)}, "map": artifact(map_file),
            "imports": imports, "imports_log": artifact(imports_log),
            "patch_count": len(patches), "translation_units_recompiled": len(units),
            "diagnostic_player_stream_trace": args.trace_player_save,
            "diagnostic_trace_player_id": args.trace_player_id if args.trace_player_save else None,
            "accepted_objects_reused": 159 - len(units), "new_game_objects_reused": 2,
            "gamecore_loaded": False,
            "active_sdk_updated": False, "accepted_bundle_replaced": False,
        }
        atomic_json(report_path, report)
        history_path = SAVE_RESTORE_ROOT / "history.json"
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {"candidates": []}
        history["candidates"].append(artifact(report_path))
        atomic_json(history_path, history)
        if not args.no_update_latest:atomic_json(SAVE_RESTORE_ROOT / "build_result.json", report)
        print(json.dumps({"status": report["status"], "build_id": build_id,
                          "translation_units_recompiled": len(units)}, ensure_ascii=False), flush=True)
    except Exception as error:
        report.update(status="SAVE_RESTORE_SDK_CANDIDATE_FAILED", error=str(error),
                      builder=artifact(Path(__file__).resolve()), patch_specification=artifact(SAVE_RESTORE_SPEC) if SAVE_RESTORE_SPEC.exists() else None,
                      gamecore_loaded=False, active_sdk_updated=False, accepted_bundle_replaced=False)
        atomic_json(report_path, report)
        raise


if __name__ == "__main__":
    main()
