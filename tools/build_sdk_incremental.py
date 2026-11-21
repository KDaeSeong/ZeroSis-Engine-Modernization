"""Compile BNW SDK sources incrementally in private folders; never link or deploy.

MSBuild owns PCH ordering and transitive header tracking. This wrapper preserves
its project/tlogs and checks content hashes to catch restored timestamps and
damaged outputs that timestamp-only tracking would otherwise miss.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

from collect_baseline import PROJECT, digest, read_text
from build_sdk_x64 import object_machine

NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace("", NS)
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
BUILD_ROOT = PROJECT / "Build/SDKIncremental"
EVIDENCE_ROOT = PROJECT / "evidence/sdk_incremental"


def tag(name):
    return f"{{{NS}}}{name}"


def element(parent, name, value=None, **attributes):
    child = ET.SubElement(parent, tag(name), attributes)
    if value is not None:
        child.text = str(value)
    return child


def escape(value):
    # MSBuild escaping is distinct from shell or XML escaping.
    return "".join(f"%{ord(c):02X}" if c in "%$@();'?*" else c for c in str(value))


def write_if_changed(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != content:
        temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
        temporary.write_bytes(content)
        temporary.replace(path)


def save(path, value):
    write_if_changed(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def write_project(path, tree):
    ET.indent(tree)
    write_if_changed(path, ET.tostring(tree, encoding="utf-8", xml_declaration=True))


def x64_project(path, sources, flags, pch_header, tool_version):
    """Generate a tracked compile-only project without changing SDK sources."""
    root = ET.Element(tag("Project"), DefaultTargets="ClCompile", ToolsVersion="Current")
    configs = element(root, "ItemGroup", Label="ProjectConfigurations")
    config = element(configs, "ProjectConfiguration", Include="Dev|x64")
    element(config, "Configuration", "Dev")
    element(config, "Platform", "x64")
    globals_ = element(root, "PropertyGroup", Label="Globals")
    element(globals_, "ProjectGuid", "{D6FEA83C-856B-4AD1-9794-C10884C3AD08}")
    element(globals_, "Keyword", "Win32Proj")
    element(globals_, "WindowsTargetPlatformVersion", "10.0.26100.0")
    element(globals_, "VCToolsVersion", tool_version)
    element(root, "Import", Project="$(VCTargetsPath)\\Microsoft.Cpp.Default.props")
    settings = element(root, "PropertyGroup", Label="Configuration")
    for name, value in {"ConfigurationType": "DynamicLibrary", "PlatformToolset": "v143",
                        "UseDebugLibraries": "false", "CharacterSet": "NotSet"}.items():
        element(settings, name, value)
    element(root, "Import", Project="$(VCTargetsPath)\\Microsoft.Cpp.props")
    output = element(root, "PropertyGroup")
    element(output, "IntDir", escape(path.parent / "obj") + "\\")
    element(output, "OutDir", escape(path.parent / "out") + "\\")
    definitions = element(root, "ItemDefinitionGroup")
    compile_ = element(definitions, "ClCompile")
    values = {"Optimization": "Disabled", "RuntimeLibrary": "MultiThreadedDLL",
              "ExceptionHandling": "Sync", "WarningLevel": "Level3", "FloatingPointModel": "Strict",
              "DebugInformationFormat": "None", "MinimalRebuild": "false", "EnablePREfast": "false",
              "MultiProcessorCompilation": "true", "PrecompiledHeader": "Use",
              "PrecompiledHeaderFile": pch_header,
              "PrecompiledHeaderOutputFile": "$(IntDir)GameCore_x64.pch",
              "ObjectFileName": "$(IntDir)",
              "AdditionalOptions": escape(" ".join(flags)) + " %(AdditionalOptions)"}
    for name, value in values.items():
        element(compile_, name, value)
    items = element(root, "ItemGroup")
    for source in sources:
        item = element(items, "ClCompile", Include=escape(source))
        if source.name == "_precompile.cpp":
            element(item, "PrecompiledHeader", "Create")
            element(item, "MultiProcessorCompilation", "false")
    element(root, "Import", Project="$(VCTargetsPath)\\Microsoft.Cpp.targets")
    write_project(path, root)


def prepare(architecture, directory):
    source_root = PROJECT / ("Source/SDK_BNW_x64" if architecture == "x64" else "Source/SDK_BNW_Original")
    sdk_project = source_root / "CvGameCoreDLL_Expansion2/CvGameCoreDLL_Expansion2.vs2010.vcxproj"
    original_tree = ET.parse(sdk_project)
    sources = [sdk_project.parent / node.attrib["Include"].replace("\\", "/")
               for node in original_tree.findall(f".//{tag('ClCompile')}[@Include]")]
    if len({source.stem.casefold() for source in sources}) != len(sources):
        raise RuntimeError("Object filenames collide")
    if not sources or any(not source.is_file() for source in sources):
        raise RuntimeError("SDK translation units missing")
    project = directory / "sdk_incremental.vcxproj"
    if architecture == "x64":
        accepted = PROJECT / "evidence/sdk_x64/attempts/attempt_037/build_result.json"
        recipe = json.loads(accepted.read_text(encoding="utf-8"))
        if recipe["status"] != "SDK_X64_ALL_OBJECTS_COMPILED":
            raise RuntimeError("Accepted compiler recipe missing")
        response = Path(recipe["executions"][1]["response"])
        if digest(response) != recipe["executions"][1]["response_sha256"]:
            raise RuntimeError("Accepted compile recipe changed")
        flags = [line for line in response.read_text(encoding="utf-8").splitlines()
                 if line and not line.startswith('"') and not re.match(r"(?i)^/(Fo|Fp|Yu|Yc|MP)", line)]
        compiler = Path(recipe["compiler"])
        if not compiler.is_file() or digest(compiler) != recipe["compiler_sha256"]:
            raise RuntimeError("Accepted compiler differs; review compiler upgrade first")
        x64_project(project, sources, flags, "CvGameCoreDLLPCH.h", compiler.parents[3].name)
        msbuild = VS / "MSBuild/Current/Bin/amd64/MSBuild.exe"
        configuration, platform = "Dev", "x64"
        watched_roots = [source_root, PROJECT / "Source/Porting", PROJECT / "Source/LuaBorrowed"]
    else:
        # Keep the original v90 ABI and optimization flags. Static analysis is a
        # separate validation step; this private project is for edit/build loops.
        tree = original_tree.getroot()
        for node in tree.iter():
            if "Include" in node.attrib and node.tag in {tag(name) for name in
                    ("ClCompile", "ClInclude", "ResourceCompile", "None")}:
                node.set("Include", escape(sdk_project.parent / node.attrib["Include"].replace("\\", "/")))
            if node.tag == tag("EnablePREfast"):
                node.text = "false"
            if node.tag == tag("ModuleDefinitionFile"):
                node.text = escape(sdk_project.parent / "CvGameCoreDLL.def")
        write_project(project, tree)
        msbuild = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\MSBuild.exe")
        configuration, platform = "Mod", "Win32"
        watched_roots = [source_root, PROJECT / "Source/BuildSupport"]
    if not msbuild.is_file():
        raise RuntimeError("MSBuild not found: " + str(msbuild))
    command = [str(msbuild), str(project), "/nologo", "/t:ClCompile", "/m:1", "/nr:false", "/v:minimal",
               f"/p:Configuration={configuration}", f"/p:Platform={platform}",
               "/p:BuildProjectReferences=false", "/p:PreferredToolArchitecture=x64",
               "/p:TargetPlatformDisplayName=Windows",
               "/p:TrackFileAccess=true", "/p:UseMultiToolTask=false",
               "/p:SolutionDir=" + escape(source_root) + "/",
               "/p:IntDir=" + escape(directory / "obj") + "/",
               "/p:OutDir=" + escape(directory / "out") + "/",
               "/p:UserRootDir=" + escape(directory / "NoUserProps") + "/"]
    if architecture == "x86":
        windows_sdk = Path(r"C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A")
        if not (windows_sdk / "Include/Windows.h").is_file():
            raise RuntimeError("Legacy Windows SDK v7.0A missing")
        command += ["/p:WindowsSdkDir=" + escape(windows_sdk) + "/",
                    "/p:TargetPlatformSdkPath=" + escape(windows_sdk) + "/"]
    else:
        # Set this as a global property so MSBuild skips user-profile SDK
        # enumeration, which is unavailable in the restricted execution host.
        windows_sdk = Path(r"C:\Program Files (x86)\Windows Kits\10")
        if not (windows_sdk / "Include/10.0.26100.0/um/Windows.h").is_file():
            raise RuntimeError("Windows SDK 10.0.26100.0 missing")
        command += ["/p:WindowsTargetPlatformVersion=10.0.26100.0",
                    "/p:_LatestWindowsTargetPlatformVersion=10.0.26100.0",
                    "/p:TargetPlatformSdkPath=" + escape(windows_sdk) + "/",
                    "/p:WindowsSdkDir=" + escape(windows_sdk) + "/"]
    return project, command, sources, watched_roots


@contextmanager
def build_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "build.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("Another incremental build owns this output folder") from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def input_files(roots, prior):
    extensions = {".h", ".hpp", ".inl", ".inc", ".cpp", ".c", ".def", ".rc", ".vcxproj"}
    paths = {str(path.resolve()).casefold(): path.resolve() for root in roots
             for path in root.rglob("*") if path.is_file() and path.suffix.lower() in extensions}
    for row in prior.get("inputs", {}).values():
        path = Path(row["path"])
        if path.is_file():
            paths[str(path.resolve()).casefold()] = path.resolve()
    return paths


def dependency_files(directory):
    paths = {}
    for log in (directory / "obj").rglob("CL.read.*.tlog"):
        for line in log.read_text(encoding="utf-16", errors="strict").splitlines():
            if re.match(r"^[A-Za-z]:[\\/]", line):
                path = Path(line)
                if path.is_file() and not path.resolve().is_relative_to(directory.resolve()):
                    paths[str(path.resolve()).casefold()] = path.resolve()
    return paths


def snapshot(paths):
    return {key: {"path": str(path), "sha256": digest(path), "mtime_ns": path.stat().st_mtime_ns}
            for key, path in sorted(paths.items())}


def clear_outputs(directory, paths=None):
    # Delete regenerable compiler outputs only in this builder's private folder.
    obj = (directory / "obj").resolve()
    for path in paths if paths is not None else [*obj.glob("*.obj"), *obj.glob("*.pch")]:
        path = Path(path).resolve()
        if path.parent != obj or path.suffix.lower() not in {".obj", ".pch"}:
            raise RuntimeError("Refusing output invalidation outside private obj folder")
        path.unlink(missing_ok=True)


def tracked_compile(directory, project, command, sources, roots, run_dir, jobs, rebuild=False):
    started = time.perf_counter()
    state_path = directory / "state.json"
    prior = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    watched = input_files(roots, prior)
    # CL.read tlogs may list the PCH consumed by /Yu as well as source headers.
    # The PCH is a compiler output; rebuilding it must not count as source drift.
    watched = {key: path for key, path in watched.items()
               if not path.is_relative_to(directory.resolve())}
    watched[str(project.resolve()).casefold()] = project.resolve()
    before_inputs = snapshot(watched)
    reasons = []
    previous = prior.get("inputs", {})
    if previous and set(previous) != set(before_inputs):
        reasons.append("input_inventory_changed")
    for key, row in before_inputs.items():
        old = previous.get(key)
        if old and row["sha256"] != old["sha256"] and row["mtime_ns"] <= old["mtime_ns"]:
            reasons.append("changed_content_with_restored_timestamp")
            break
    bad_outputs = [Path(row["path"]) for row in prior.get("outputs", [])
                   if not Path(row["path"]).is_file() or digest(Path(row["path"])) != row["sha256"]]
    if any(path.suffix.lower() == ".pch" for path in bad_outputs):
        reasons.append("missing_or_damaged_pch")
    if rebuild or reasons:
        clear_outputs(directory)
    elif bad_outputs:
        clear_outputs(directory, bad_outputs)
    before_objects = {source.stem: (directory / "obj" / (source.stem + ".obj")).stat().st_mtime_ns
                      for source in sources if (directory / "obj" / (source.stem + ".obj")).is_file()}
    command = command + [f"/p:CL_MPCount={jobs}"]
    log = run_dir / "msbuild.log"
    environment = {key.upper(): value for key, value in os.environ.items()}
    environment["VSLANG"] = "1033"
    print(json.dumps({"phase": "SDK_INCREMENTAL_COMPILE", "units": len(sources), "jobs": jobs,
                      "rebuild": rebuild, "invalidation_reasons": reasons}), flush=True)
    compile_started = time.perf_counter()
    with log.open("wb") as stream:
        result = subprocess.run(command, cwd=directory, env=environment, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=1800,
                                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    compile_seconds = time.perf_counter() - compile_started
    output = read_text(log)
    errors = sorted(set(re.findall(r"(?m)^.*\b(?:fatal )?error\s+[A-Z]+\d+[^\r\n]*", output)))
    numeric_warnings = sorted(set(re.findall(r"(?m)^.*\bwarning\s+C(?:4244|4267|4838)\b[^\r\n]*", output)))
    objects = [object_machine(directory / "obj" / (source.stem + ".obj")) for source in sources
               if (directory / "obj" / (source.stem + ".obj")).is_file()]
    for row in objects:
        row["architecture"] = {"0x8664": "x64", "0x014c": "x86"}.get(row["machine"], "unexpected")
    rebuilt = [Path(row["path"]).stem for row in objects
               if Path(row["path"]).stat().st_mtime_ns != before_objects.get(Path(row["path"]).stem)]
    inputs_unchanged = all(path.is_file() and digest(path) == before_inputs[key]["sha256"]
                           for key, path in watched.items())
    expected_machine = "0x8664" if "/p:Platform=x64" in command else "0x014c"
    passed = (result.returncode == 0 and not errors and not numeric_warnings and inputs_unchanged
              and len(objects) == len(sources) and all(row["machine"] == expected_machine for row in objects))
    if passed:
        watched.update(dependency_files(directory))
        inputs = snapshot(watched)
        outputs = [{"path": row["path"], "sha256": row["sha256"]} for row in objects]
        outputs += [{"path": str(path), "sha256": digest(path)} for path in (directory / "obj").glob("*.pch")]
        save(state_path, {"inputs": inputs, "outputs": outputs})
    report = {"status": "SDK_INCREMENTAL_COMPILE_PASS" if passed else "SDK_INCREMENTAL_COMPILE_FAILED",
              "captured_at_utc": datetime.now(timezone.utc).isoformat(), "command": command,
              "builder": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))},
              "project": {"path": str(project), "sha256": digest(project)},
              "translation_units_expected": len(sources), "objects": objects,
              "rebuilt_units": rebuilt, "rebuilt_count": len(rebuilt), "reused_count": len(objects) - len(rebuilt),
              "compiler_seconds": compile_seconds, "total_seconds": time.perf_counter() - started,
              "exit_code": result.returncode, "inputs_unchanged": inputs_unchanged,
              "invalidation_reasons": reasons, "damaged_outputs_invalidated": [str(path) for path in bad_outputs],
              "unique_error_lines": errors, "numeric_warning_lines": numeric_warnings,
              "log": {"path": str(log), "sha256": digest(log)},
              "linked": False, "deployed": False, "game_launched": False,
              "scope": "PRIVATE_DEVELOPER_COMPILE_ONLY"}
    save(run_dir / "build_result.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("x86", "x64"), default="x64")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--rebuild", action="store_true", help="Recompile private outputs; keep sources unchanged")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must be between 1 and 16")
    directory = BUILD_ROOT / args.arch
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    run_dir = EVIDENCE_ROOT / args.arch / run_id
    with build_lock(directory):
        project, command, sources, roots = prepare(args.arch, directory)
        run_dir.mkdir(parents=True, exist_ok=False)
        report = tracked_compile(directory, project, command, sources, roots, run_dir, args.jobs, args.rebuild)
        save(EVIDENCE_ROOT / args.arch / "latest.json", report)
    print(json.dumps({key: report[key] for key in ("status", "rebuilt_count", "reused_count", "compiler_seconds", "total_seconds")}), flush=True)
    print(json.dumps({"report": str(run_dir / "build_result.json")}), flush=True)
    if report["status"] != "SDK_INCREMENTAL_COMPILE_PASS":
        print("\n".join(report["unique_error_lines"][:8]), flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
