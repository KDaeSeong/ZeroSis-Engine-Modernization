"""Recompile the five attested UI Host units with the shared native V1 codec.

This command creates a private candidate only. It never runs the resulting Host,
loads GameCore, regenerates UI assets, or promotes an installed/default runtime.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

from collect_baseline import pe_header
from native_build import environment_for

PROJECT = Path(__file__).resolve().parents[1]
BASE_SHA = "8e6a2a283d22e042202d98b5e59320de5de73d1f98c44762e409f21f7fea1a02"
COMPONENT_SHA = "62acfd495ea42514be16d55cef421fcbb6965a955a362680fa2e650775769f7f"
UNITS = ("host_main", "window", "renderer", "world_renderer", "terrain_renderer")


def key(path):
    return os.path.normcase(os.path.abspath(path))


def artifact(path):
    path = Path(path)
    before = path.stat()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), str(path)
    return dict(path=str(path), bytes=after.st_size, sha256=sha,
                file_identity=[after.st_dev, after.st_ino], mtime_ns=after.st_mtime_ns)


def sealed(row):
    actual = artifact(row["path"])
    for name in ("bytes", "sha256", "file_identity", "mtime_ns"):
        if name in row:
            assert actual[name] == row[name], (name, row["path"])
    return actual


def document(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ordinary(path, root):
    path, root = Path(path), Path(root)
    assert path.is_absolute() and path.is_relative_to(root) and path.resolve() == path
    for part in [path, *path.parents]:
        if part.exists():
            assert not part.lstat().st_file_attributes & 0x400, str(part)
        if part == root:
            break


def dependencies(path):
    data = document(path)["Data"]
    assert isinstance(data["Source"], str) and isinstance(data["Includes"], list)
    return {key(p) for p in [data["Source"], *data["Includes"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-build", required=True)
    parser.add_argument("--preflight", action="store_true", help="Verify current inputs without creating or compiling anything")
    parser.add_argument("--retry-after", type=Path, help="Terminal precompile failure receipt for a distinct, explicitly scoped retry")
    args = parser.parse_args()
    assert re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", args.base_build)
    assert sys.dont_write_bytecode and not sys.flags.optimize
    assert not any(os.environ.get(k) for k in ("CL", "_CL_", "LINK"))
    base_root = PROJECT / "Build/UiWindowHost" / args.base_build
    base_path = PROJECT / "evidence/ui_window_host" / args.base_build / "build_result.json"
    base_ref = artifact(base_path)
    assert base_ref["sha256"] == BASE_SHA
    base = document(base_path)
    assert base["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and len(base["compiler_inputs"]) == 544
    component_path = PROJECT / "evidence/native_save_archive/portable_envelope/result.json"
    component_ref = artifact(component_path)
    assert component_ref["sha256"] == COMPONENT_SHA
    component = document(component_path)
    assert component["status"] == "PASS_PORTABLE_NATIVE_SAVE_ENVELOPE_COMPONENT"
    current_component = {key(r["path"]): r for r in component["inputs"]}
    archive = PROJECT / "Source/Host/NativeSaveArchive.h"
    envelope = PROJECT / "Source/Host/NativeSaveEnvelope.h"
    codec = [sealed(current_component[key(path)]) for path in (archive, envelope)]
    retry_ref = None
    if args.retry_after:
        ordinary(args.retry_after, PROJECT / "evidence/native_save_archive/host_relink")
        assert args.retry_after.name == "failure.json"
        failure = document(args.retry_after)
        assert failure["error_type"] in ("PermissionError", "KeyError")
        assert len(failure["commands"]) <= 1 and not failure["forbidden_access_attempts"]
        assert all(Path(c["executable"]).name.lower()=="cmd.exe" and c["returncode"]==0 for c in failure["commands"])
        retry_ref = artifact(args.retry_after)
    signature = hashlib.sha256((BASE_SHA + COMPONENT_SHA + artifact(__file__)["sha256"] + (retry_ref["sha256"] if retry_ref else "")).encode()).hexdigest()[:20]
    stage = PROJECT / "evidence/native_save_archive/host_relink" / signature
    assert not stage.exists(), "Single-use attempt; inspect the existing result/handle instead of replaying"
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + signature[:12]
    build = PROJECT / "Build/UiWindowHost" / identifier
    report_root = PROJECT / "evidence/ui_window_host" / identifier
    assert not build.exists() and not report_root.exists()
    sources_before, donors = {}, {}
    def remember(path):
        row = artifact(path)
        old = sources_before.setdefault(key(path), row)
        assert old == row
        return row
    def donor(row):
        frozen = sealed(row)
        ordinary(Path(row["path"]), base_root / "frozen")
        donors[key(row["path"])] = frozen
        original = row.get("original_path", row.get("original_source"))
        if original:
            live = remember(original)
            if key(original) != key(archive):
                assert (live["bytes"], live["sha256"]) == (row["bytes"], row["sha256"]), original
        return frozen
    for group in ("compiler_inputs", "sources", "provider_inputs", "system_libraries", "build_tools"):
        for row in base[group]:
            donor(row)
    for row in base["provider_reports"].values():
        donor(row)
    donor(base["ui_assets"])
    remember(envelope)
    for row in codec:
        assert sources_before[key(row["path"])] == row
    for name in ("compiler", "linker", "dumpbin", "executable", "map", "link_response", "link_log"):
        remember(base[name]["path"])
        sealed(base[name])
    protected_path = PROJECT / "evidence/native_save_archive/portable_envelope/publication/post_checks.json"
    previous = document(protected_path)
    protected = {key(r["path"]): sealed(r) for name in ("protected_files", "source_contract_inputs", "source_and_proof_files") for r in previous[name]}
    for change in previous["component_input_revisions"]:
        protected[key(change["after"]["path"])] = sealed(change["after"])
    protected[key(protected_path)] = remember(protected_path)
    for row in (base_ref, component_ref, artifact(__file__), *donors.values(), *sources_before.values()):
        protected[key(row["path"])] = row
    storage_ref = artifact(PROJECT / "evidence/native_save_archive/host_relink/storage_before.json")
    storage = document(storage_ref["path"])
    assert storage["errors"] == 0 and not storage["disposable_allocation_exceeding_10_GiB_established"]
    assert (datetime.now(timezone.utc)-datetime.fromisoformat(storage["utc"])).total_seconds() < 3600
    assert shutil.disk_usage(PROJECT).free > 512 * 1024 * 1024
    protected[key(storage_ref["path"])] = storage_ref
    if retry_ref:
        protected[key(retry_ref["path"])] = retry_ref
    if args.preflight:
        print(json.dumps(dict(status="PASS_CURRENT_NATIVE_SAVE_HOST_PREFLIGHT",signature=signature,live_inputs=len(sources_before),donor_snapshots=len(donors),protected=len(protected),changed_sources=codec[:1],new_sources=codec[1:],no_files_created=True,no_child_processes=True)))
        return 0
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    assert kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000)
    denied, commands = [], []
    pending = {}
    binaries = {key(base[n]["path"]): n for n in ("compiler", "linker", "dumpbin")}
    def guard(event, values):
        def deny():
            denied.append(dict(event=event, target=str(values[0])[:200] if values else ""))
            raise PermissionError("Private Host relink scope: " + event)
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            path, mode, flags = values
            absolute = key(os.fsdecode(path))
            if any(part in absolute for part in ("\\my games\\", "\\.codex\\", "\\steamapps\\common\\")):
                deny()
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not any(absolute.startswith(key(root) + os.sep) for root in (build, stage, report_root)):
                deny()
        elif event == "subprocess.Popen":
            executable, words, cwd, _ = values
            expected = pending.get("command")
            if not expected or key(cwd) != key(pending["cwd"]):deny()
            if isinstance(words, (list, tuple)):
                if [str(x) for x in words] != expected:deny()
            elif str(words) != subprocess.list2cmdline(expected):deny()
            words = expected
            if executable is None:
                executable = expected[0]
            elif key(executable) != key(expected[0]):
                deny()
            if Path(str(executable)).name.lower() == "cmd.exe":
                if words != ["cmd.exe", "/d", "/c", str(build / "read_build_environment.cmd")] or key(cwd) != key(build):
                    deny()
            elif key(executable) not in binaries or not Path(cwd).is_relative_to(build):
                deny()
            commands.append(dict(executable=str(executable), command=words, cwd=str(cwd)))
        elif event in ("os.mkdir", "os.chmod", "os.remove", "os.rmdir", "os.rename", "os.link"):
            targets = values[:2] if event in ("os.link", "os.rename") else values[:1]
            destination = targets[-1] if event in ("os.link", "os.rename") else targets[0]
            if not any(key(destination) == key(root) or key(destination).startswith(key(root) + os.sep) for root in (build, stage, report_root)):
                deny()
        elif event.startswith(("socket.", "ctypes.dlopen")) or event in ("os.system", "os.startfile", "os.startfile/2", "os.exec", "os.posix_spawn", "os.symlink", "os.truncate", "os.utime"):
            deny()
    stage.parent.mkdir(parents=True, exist_ok=True)
    ordinary(stage.parent, PROJECT)
    sys.addaudithook(guard)
    stage.mkdir(); build.mkdir(); report_root.mkdir()
    write(stage / "started.json", dict(utc=datetime.now(timezone.utc).isoformat(), build_id=identifier, signature=signature, baseline_build=base_ref, component=component_ref, storage_before=storage_ref, requirements="Recompile all five current Host units using the unchanged 67-payload catalog and native V1 schema; do not execute or promote a runtime.", prior_cleanup_audit=artifact(PROJECT / "evidence/native_save_archive/portable_envelope/publication/final_audit.json"), full_engine_goal_complete=False))
    if retry_ref:
        write(stage / "retry_authority.json", dict(prior_terminal_failure=retry_ref, prior_compiler_commands_started=0, unchanged_user_authorized_scope=True, reason="Distinct retry after a terminal precompile failure; no source or donor attribute changes."))
    materialized = {}
    def relocate(path):
        return build / Path(path).relative_to(base_root)
    def freeze(row, source=None):
        target = relocate(row["path"])
        if key(target) in materialized:
            return materialized[key(target)]
        ordinary(target, build); target.parent.mkdir(parents=True, exist_ok=True)
        if source is None:
            os.link(row["path"], target)
            method = "hardlink"
        else:
            with target.open("xb") as output:
                output.write(Path(source).read_bytes())
            os.chmod(target, stat.S_IREAD)
            method = "copy_changed_live_source"
        new = {**row, **artifact(target), "materialization": method}
        if source is not None:
            new.pop("reused_from_path", None)
            new["sha256"] = sources_before[key(source)]["sha256"]
            assert artifact(target)["sha256"] == new["sha256"]
        else:
            new["reused_from_path"] = row["path"]
        materialized[key(target)] = new
        return new
    report = {}
    try:
        compiler_inputs = [freeze(row, archive if key(row["original_path"]) == key(archive) else None) for row in base["compiler_inputs"]]
        template = next(r for r in base["compiler_inputs"] if key(r["original_path"]) == key(archive))
        envelope_row = {**template, "path": str(Path(template["path"]).with_name(envelope.name)), "original_path": str(envelope), "relative_path": str(Path(template["relative_path"]).with_name(envelope.name)), **{k: codec[1][k] for k in ("bytes", "sha256")}}
        compiler_inputs.append(freeze(envelope_row, envelope))
        sources = [{**freeze(row, archive if key(row["original_source"]) == key(archive) else None), "original_source": row["original_source"], "relative_path": row["relative_path"]} for row in base["sources"]]
        sources.append({**materialized[key(relocate(envelope_row["path"]))], "original_source": str(envelope)})
        providers = [freeze(row) for row in base["provider_inputs"]]
        systems = [freeze(row) for row in base["system_libraries"]]
        tools = [freeze(row) for row in base["build_tools"]]
        provider_reports = {name: freeze(row) for name, row in base["provider_reports"].items()}
        assets = freeze(base["ui_assets"])
        pending.update(command=["cmd.exe","/d","/c",str(build/"read_build_environment.cmd")],cwd=str(build))
        env, compiler = environment_for(Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"), "x64", build)
        commands[-1]["returncode"]=0;pending.clear()
        assert key(compiler) == key(base["compiler"]["path"]) and not any(env.get(k) for k in ("CL", "_CL_", "LINK"))
        frozen = build / "frozen"
        env["INCLUDE"] = ";".join(str(frozen / "include_roots" / ("system_%02d" % i)) for i in range(len(base["system_include_roots"])))
        (build / "tmp").mkdir();env["TMP"] = env["TEMP"] = str(build / "tmp");env["VSLANG"] = "1033"
        vc = Path(compiler).parents[3] / "lib/x64"
        um = Path(base["system_libraries"][0]["original_path"]).parent
        ucrt = um.parents[1] / "ucrt/x64"
        implicit_before = [artifact(root / name) | {"name": name} for root, name in ((vc,"msvcrt.lib"),(vc,"msvcprt.lib"),(vc,"vcruntime.lib"),(vc,"oldnames.lib"),(um,"bcrypt.lib"),(um,"kernel32.lib"),(ucrt,"ucrt.lib"))]
        implicit_folder = frozen / "implicit_libraries"; implicit_folder.mkdir()
        implicit_donor_root = PROJECT / "evidence/found_value_shared_bridge/20261002T152931Z_bbc131426b"
        implicit_donor_report = artifact(implicit_donor_root / "conformance.json")
        assert implicit_donor_report["sha256"] == "da2f1d5d9e759cbff7618ea280a3878177f16dc1f59d945d57e67be4a01d43df"
        protected[key(implicit_donor_report["path"])] = implicit_donor_report
        def all_refs(value):
            if isinstance(value, dict):
                if all(n in value for n in ("path", "sha256")) and ("bytes" in value or "size" in value):yield {**value,"bytes":value.get("bytes",value.get("size"))}
                for child in value.values():yield from all_refs(child)
            elif isinstance(value, list):
                for child in value:yield from all_refs(child)
        attested = {key(r["path"]):r for r in all_refs(document(implicit_donor_report["path"]))}
        implicit_donors = {name:implicit_donor_root / "frozen_inputs/libraries" / sub / filename for name,sub,filename in (("msvcprt.lib","lib_001","msvcprt.lib"),("msvcrt.lib","lib_002","msvcrt.lib"),("oldnames.lib","lib_003","oldnames.lib"),("kernel32.lib","lib_005","kernel32.Lib"),("vcruntime.lib","lib_006","vcruntime.lib"),("ucrt.lib","lib_007","ucrt.lib"))}
        implicit = []
        for row in implicit_before:
            target = implicit_folder / row["name"]
            old_donor = implicit_donors.get(row["name"])
            if old_donor is not None:
                ordinary(old_donor, implicit_donor_root)
                old_pin = sealed(attested[key(old_donor)])
                assert old_pin["sha256"] == row["sha256"]
                protected[key(old_donor)] = old_pin
                os.link(old_donor, target)
                method = "attested_snapshot_hardlink"
            else:
                with target.open("xb") as stream:stream.write(Path(row["path"]).read_bytes())
                os.chmod(target, stat.S_IREAD)
                method = "copied_system_input"
            snapshot = artifact(target);assert snapshot["sha256"] == row["sha256"]
            implicit.append({**snapshot, "original_path": row["path"], "name": row["name"], "materialization": method})
        env["LIB"] = str(implicit_folder)
        records, object_rows = [], []
        def execute(command, cwd, log):
            pending.update(command=[str(p) for p in command],cwd=str(cwd))
            result = subprocess.run(pending["command"], cwd=cwd, env=env, capture_output=True, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            commands[-1]["returncode"]=result.returncode;pending.clear()
            log.write_bytes(result.stdout + result.stderr)
            text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
            assert result.returncode == 0 and not re.search(r"\bwarning\s+(?:C|LNK)\d+", text, re.I), (result.returncode, text[-2500:])
            return result
        for index, name in enumerate(UNITS):
            old = next(r for r in base["final_compilation"]["translation_units"] if r["translation_unit"] == name)
            sealed(old["response"]);sealed(old["dependency_report"])
            response, dep = relocate(old["response"]["path"]), relocate(old["dependency_report"]["path"])
            response.parent.mkdir(parents=True);(response.parent / "obj").mkdir()
            text = Path(old["response"]["path"]).read_text(encoding="utf-8-sig")
            rewritten = text.replace(str(base_root), str(build)).replace(base_root.as_posix(), build.as_posix())
            assert str(base_root) not in rewritten and base_root.as_posix() not in rewritten
            response.write_text(rewritten, encoding="utf-8", newline="\n")
            log = stage / ("compile_" + name + ".log")
            execute([compiler, "@" + str(response)], response.parent, log)
            expected = {key(relocate(p)) for p in dependencies(old["dependency_report"]["path"])}
            if key(template["path"]) in dependencies(old["dependency_report"]["path"]):expected.add(key(relocate(envelope_row["path"])))
            actual = dependencies(dep);assert actual == expected, (name, sorted(actual-expected), sorted(expected-actual))
            objects = list((response.parent / "obj").glob("*.obj"));assert len(objects)==1
            obj = artifact(objects[0]);assert Path(obj["path"]).read_bytes()[:2] == b"\x64\x86"
            object_rows.append(obj)
            records.append(dict(translation_unit=name,command=[str(compiler),"@"+str(response)],response=artifact(response),log=artifact(log),dependency_report=artifact(dep),object=obj,returncode=0,expected_dependency_count=len(expected),actual_dependency_count=len(actual)))
            write(stage / ("compiled_" + name + ".json"), records[-1])
            print(json.dumps(dict(phase="compiled",translation_unit=name,object_bytes=obj["bytes"])),flush=True)
        link_response = relocate(base["link_response"]["path"])
        text = Path(base["link_response"]["path"]).read_text(encoding="utf-8-sig")
        link_response.write_text(text.replace(str(base_root),str(build)).replace(base_root.as_posix(),build.as_posix()) + "/VERBOSE:LIB\n",encoding="utf-8",newline="\n")
        link_log = stage / "link.log";execute([base["linker"]["path"],"@"+str(link_response)],link_response.parent,link_log)
        objects_after = [sealed(row) for row in object_rows];assert objects_after == object_rows
        executable = relocate(base["executable"]["path"]);mapfile=relocate(base["map"]["path"])
        imports_log=stage/"imports.log";result=execute([base["dumpbin"]["path"],"/dependents",str(executable)],executable.parent,imports_log)
        imports=re.findall(r"^\s+([\w.-]+\.dll)\s*$",result.stdout.decode("ascii",errors="replace"),re.M|re.I)
        assert {n.casefold() for n in imports}=={n.casefold() for n in base["imports"]["dependencies"]}
        pe=pe_header(executable);assert pe["architecture"]=="x64" and pe["pe_format"]=="PE32+"
        implicit_after=[sealed(row)|{"name":row["name"]} for row in implicit_before];assert implicit_after==implicit_before
        for row in implicit:sealed(row)
        for row in materialized.values():sealed(row)
        for row in protected.values():sealed(row)
        for row in sources_before.values():sealed(row)
        maptext=mapfile.read_text(encoding="mbcs",errors="replace")
        maplibs=sorted({m.casefold().removesuffix(".lib")+".lib" for m in re.findall(r"\s([\w.-]+):\S+\.(?:obj|dll)\s*$",maptext,re.I|re.M)})
        known={r["name"].casefold() for r in implicit}
        actual_implicit=sorted(set(maplibs)&known)
        report={**base,"build_id":identifier,"status":"UI_WINDOW_HOST_CANDIDATE_BUILT","baseline_build":base_ref,"native_save_component":component_ref,"relink_builder":artifact(__file__),"compiler_inputs":compiler_inputs,"compiler_dependency_count":len(compiler_inputs),"sources":sources,"provider_inputs":providers,"system_libraries":systems,"libraries":providers+systems,"provider_reports":provider_reports,"ui_assets":assets,"build_tools":tools,"ui_asset_preparation":{"status":"UNCHANGED_ATTESTED_67_PAYLOAD_CATALOG_REUSED","executed":False},"dependency_discovery":{"executed":False,"reason":"All historical live inputs matched except the approved archive refactor; every final compiler dependency was checked against the mapped closure plus its new envelope header."},"final_compilation":{"translation_units":records},"final_dependency_reports":{r["translation_unit"]:r["dependency_report"] for r in records},"response":records[0]["response"],"dependency_report":records[0]["dependency_report"],"link_response":artifact(link_response),"link_log":artifact(link_log),"link_snapshot":{"response":artifact(link_response),"objects_before":object_rows,"objects_after":objects_after,"returncode":0},"map":artifact(mapfile),"executable":artifact(executable)|{"pe":pe},"imports":{"dependencies":imports,"log":artifact(imports_log)},"current_source_inputs":list(sources_before.values()),"protected_artifacts":list(protected.values()),"implicit_libraries_before":implicit_before,"implicit_libraries_after":implicit_after,"implicit_libraries":implicit,"actual_implicit_library_namesfrommap":actual_implicit,"compiler":sealed(base["compiler"]),"linker":sealed(base["linker"]),"dumpbin":sealed(base["dumpbin"]),"source_inputs_unchanged":True,"provider_inputs_unchanged":True,"sources_changed_from_baseline":[codec[0]],"new_source_inputs":[codec[1]],"frozen_input_reuse":{"hardlinked_files":sum(r["materialization"]=="hardlink" for r in materialized.values()),"hardlinked_logical_bytes":sum(r["bytes"] for r in materialized.values() if r["materialization"]=="hardlink"),"copied_source_bytes":sum(r["bytes"] for r in materialized.values() if r["materialization"]!="hardlink"),"donor_content_and_metadata_preserved":True},"scope":"Five complete current Host compilations and one private x64 link only; unchanged generated UI catalog reused; no Host, SDK, GameCore or HWND execution.","host_runtime_executed":False,"gamecore_loaded":False,"sdk_linked":False,"mods_updated":False,"stage_updated":False,"default_promoted":False,"full_engine_goal_complete":False,"forbidden_access_attempts":denied}
        # Remove stale baseline fields that could imply this candidate consumed old paths.
        report["final_environment"] = {name:env.get(name,"") for name in ("INCLUDE","LIB","TMP","TEMP","VSLANG","CL","_CL_","LINK")}
        for field in ("dependency_discovery_reports","compile_log","source_hashes_before","source_hashes_after","compiler_dependency_live_hashes_after","ui_asset_preparation","frozen_input_reuse"):
            if field in ("ui_asset_preparation","frozen_input_reuse"):continue
            report.pop(field,None)
        assert not denied and len(records)==5 and len(compiler_inputs)==545 and len(sources)==81
        report_path=report_root/"build_result.json";write(report_path,report)
        run=dict(schema="zerosis.native_save.host_relink_run.v1",status="PASS_CURRENT_NATIVE_SAVE_HOST_LINK_ONLY",utc=datetime.now(timezone.utc).isoformat(),build_id=identifier,build_result=artifact(report_path),commands=commands,actual_objects=object_rows,link_snapshot=report["link_snapshot"],protected_unchanged=True,current_inputs_unchanged=True,forbidden_access_attempts=denied,host_runtime_executed=False,gamecore_loaded=False,hwnd_created=False,default_promoted=False,full_engine_goal_complete=False)
        write(stage/"run.json",run)
        print(json.dumps(dict(status=run["status"],build_id=identifier,build_result=artifact(report_path),run=artifact(stage/"run.json"),executable=report["executable"],commands=len(commands))),flush=True)
        return 0
    except BaseException as error:
        write(stage/"failure.json",dict(status="FAILED_DO_NOT_REPLAY",error_type=type(error).__name__,error=str(error)[:4000],commands=commands,forbidden_access_attempts=denied,full_engine_goal_complete=False))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
