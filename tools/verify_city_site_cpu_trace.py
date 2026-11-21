"""Retain immutable evidence for the isolated CitySite CPU-trace checks.

This verifier builds frozen offline sources and exercises the reader's help and
topology-sidecar round trip. It never captures WPR/ETW data or loads GameCore.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import sys
import traceback

from collect_baseline import PROJECT
from native_build import environment_for, run


VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
BUILD_ROOT = PROJECT / "Build"
EVIDENCE_ROOT = PROJECT / "evidence/city_site_cpu_trace"
OWNED = {
    "header": PROJECT / "Source/Diagnostics/CitySiteCpuTrace.h",
    "provider": PROJECT / "Source/Diagnostics/CitySiteCpuTrace.cpp",
    "reader": PROJECT / "tools/city_site_cpu_trace_reader.cpp",
    "test": PROJECT / "Tests/city_site_cpu_trace.cpp",
    "verifier": Path(__file__).resolve(),
}
def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def allocate_run() -> tuple[str, Path, Path]:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)
        build_dir = BUILD_ROOT / run_id
        evidence_dir = EVIDENCE_ROOT / run_id
        try:
            build_dir.mkdir(parents=False, exist_ok=False)
            evidence_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            # A collision is extraordinarily unlikely; retain any directory already
            # created and use a fresh ID on the next attempt.
            continue
        return run_id, build_dir, evidence_dir
    raise RuntimeError("Could not allocate a unique retained run ID")


def toolchain_inputs(compiler: str, env: dict, directory: Path) -> list[dict]:
    linker = shutil.which("link.exe", path=env.get("PATH"))
    command_shell = shutil.which("cmd.exe", path=env.get("PATH"))
    if not linker or not command_shell:
        raise RuntimeError("Compiler linker or command-shell helper is unavailable")
    candidates = [
        ("compiler", Path(compiler)),
        ("linker", Path(linker)),
        ("command_shell", Path(command_shell)),
        ("vcvars64", VS / "VC/Auxiliary/Build/vcvars64.bat"),
        ("environment_setup", directory / "read_build_environment.cmd"),
    ]
    result = []
    seen = set()
    for role, path in candidates:
        resolved = path.resolve(strict=True)
        key = str(resolved).casefold()
        if key not in seen:
            seen.add(key)
            result.append({"role": role, "path": str(resolved), "sha256": sha(resolved)})
    return result


def parse_source_dependencies(path: Path, expected_source: Path) -> list[Path]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read MSVC sourceDependencies output {path}: {error}") from error
    data = document.get("Data", document)
    if not isinstance(data, dict) or not isinstance(data.get("Includes"), list):
        raise RuntimeError(f"MSVC sourceDependencies document has no Includes array: {path}")
    raw_paths = [data.get("Source", str(expected_source)), *data["Includes"]]
    dependencies = []
    seen = set()
    for raw in raw_paths:
        if not isinstance(raw, str) or not raw:
            raise RuntimeError(f"MSVC sourceDependencies contains an invalid path: {path}")
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = expected_source.parent / candidate
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise RuntimeError(f"MSVC source dependency is not a file: {resolved}")
        key = str(resolved).casefold()
        if key not in seen:
            seen.add(key)
            dependencies.append(resolved)
    source_key = str(expected_source.resolve(strict=True)).casefold()
    if source_key not in seen:
        dependencies.insert(0, expected_source.resolve(strict=True))
    return dependencies


def compile_one(compiler: str, env: dict, directory: Path, sources,
               name: str, optimization: str, extra_link=()) -> tuple[Path, str, Path, dict]:
    exe = directory / f"{name}.exe"
    common_flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", optimization,
                    "/MD", "/fp:strict", "/DWIN32", "/D_WIN32_WINNT=0x0A00", "/DNOMINMAX",
                    "/DWIN32_LEAN_AND_MEAN"]
    tu_records = []
    logs = []
    objects = []
    for index, source in enumerate(sources):
        source = source.resolve(strict=True)
        object_file = directory / f"{name}_{index}.obj"
        response = directory / f"{name}_{index}.rsp"
        dependency_file = directory / f"{name}_{index}.sourceDependencies.json"
        compile_flags = [*common_flags, "/c", f'"{source}"', f'/Fo"{object_file}"',
                         f'/sourceDependencies "{dependency_file}"']
        response.write_text("\n".join(compile_flags) + "\n", encoding="utf-8")
        compiled = run([compiler, f"@{response}"], cwd=directory, env=env, timeout=180)
        compile_output = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
        compile_log_path = directory / f"{name}_{index}.compile.log"
        compile_log_path.write_text(compile_output, encoding="utf-8")
        logs.append(compile_output)
        if compiled.returncode or re.search(r"\bwarning\s+C\d+", compile_output, re.I):
            raise RuntimeError(f"{name} translation unit {source} failed or warned ({compiled.returncode}):\n{compile_output[-6000:]}")
        if not object_file.is_file() or not dependency_file.is_file():
            raise RuntimeError(f"Compiler did not produce object/sourceDependencies output for {source}")
        dependencies = parse_source_dependencies(dependency_file, source)
        objects.append(object_file)
        tu_records.append({
            "source": str(source), "source_sha256": sha(source),
            "response_file": str(response), "response_file_sha256": sha(response),
            "arguments": compile_flags,
            "dependency_document": str(dependency_file),
            "dependency_document_sha256": sha(dependency_file),
            "dependencies": [str(item) for item in dependencies],
            "object": str(object_file), "object_sha256": sha(object_file),
            "compile_log": str(compile_log_path), "compile_log_sha256": sha(compile_log_path),
        })

    link_response = directory / f"{name}.link.rsp"
    linker = shutil.which("link.exe", path=env.get("PATH"))
    if not linker:
        raise RuntimeError("Linker executable is unavailable")
    link_flags = [*(f'"{item}"' for item in objects), f'/OUT:"{exe}"',
                  "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX",
                  "/OPT:REF", "/OPT:ICF", *extra_link]
    link_response.write_text("\n".join(link_flags) + "\n", encoding="utf-8")
    linked = run([linker, f"@{link_response}"], cwd=directory, env=env, timeout=180)
    link_output = (linked.stdout + linked.stderr).decode("mbcs", errors="replace")
    logs.append(link_output)
    link_log = directory / f"{name}.link.log"
    link_log.write_text(link_output, encoding="utf-8")
    output = "\n".join(logs)
    if linked.returncode or re.search(r"\bwarning\s+(?:C|LNK)\d+", link_output, re.I):
        raise RuntimeError(f"{name} link failed or warned ({linked.returncode}):\n{link_output[-6000:]}")
    if not exe.is_file():
        raise RuntimeError(f"Linker did not produce executable: {exe}")
    log = directory / f"{name}.compile.log"
    log.write_text(output, encoding="utf-8")
    compile_record = {
        "optimization": optimization,
        "compiler": str(Path(compiler).resolve()),
        "compiler_sha256": sha(Path(compiler).resolve()),
        "linker": str(Path(linker).resolve()),
        "linker_sha256": sha(Path(linker).resolve()),
        "link_arguments": link_flags,
        "link_response_file": str(link_response), "link_response_file_sha256": sha(link_response),
        "link_log": str(link_log), "link_log_sha256": sha(link_log),
        "translation_units": tu_records,
        "exe": str(exe), "exe_sha256": sha(exe),
    }
    return exe, output, log, compile_record


def run_json(command, *, cwd: Path, env: dict, timeout: int, label: str) -> tuple[dict, str]:
    result = run(command, cwd=cwd, env=env, timeout=timeout)
    raw = result.stdout + result.stderr
    try:
        output = raw.decode("utf-8", errors="strict")
        document = json.loads(output)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} did not return machine-readable UTF-8 JSON: {error}") from error
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}: {output[-3000:]}")
    if not isinstance(document, dict):
        raise RuntimeError(f"{label} JSON root is not an object")
    return document, output


def validate_topology_schema(document: dict) -> None:
    expected = {"schema", "boot_time_100ns", "qpc_frequency", "os_version", "processor_count", "topology"}
    if set(document) != expected or document.get("schema") != "zerosiscitysite.topology.v1":
        raise RuntimeError("Topology sidecar schema or root keys differ")
    for key in ("boot_time_100ns", "qpc_frequency", "processor_count"):
        value = document.get(key)
        if type(value) is not int or value <= 0:
            raise RuntimeError(f"Topology sidecar {key} is not a positive integer")
    os_version = document.get("os_version")
    if not isinstance(os_version, dict) or set(os_version) != {"major", "minor", "build"}:
        raise RuntimeError("Topology sidecar OS version keys differ")
    if any(type(os_version[key]) is not int or os_version[key] < 0 for key in ("major", "minor", "build")):
        raise RuntimeError("Topology sidecar OS version contains an invalid integer")
    topology = document.get("topology")
    if not isinstance(topology, list) or len(topology) != document["processor_count"]:
        raise RuntimeError("Topology sidecar processor count differs from its entries")
    seen = set()
    for entry in topology:
        if not isinstance(entry, dict) or set(entry) != {"group", "logical_processor", "physical_core"}:
            raise RuntimeError("Topology sidecar entry keys differ")
        group, logical, core = (entry.get("group"), entry.get("logical_processor"), entry.get("physical_core"))
        if (type(group) is not int or not 0 <= group <= 65535 or
                type(logical) is not int or not 0 <= logical <= 255 or
                type(core) is not int or not 0 <= core <= 0xFFFFFFFF):
            raise RuntimeError("Topology sidecar entry contains an out-of-range integer")
        key = (group, logical)
        if key in seen:
            raise RuntimeError("Topology sidecar contains a duplicate logical processor")
        seen.add(key)


def reject_topology_cases(reader: Path, build_dir: Path, env: dict, source_document: dict) -> list[dict]:
    cases = []
    duplicate_root = json.dumps(source_document, separators=(",", ":"), ensure_ascii=False)
    duplicate_root = duplicate_root.replace(
        '"schema":"zerosiscitysite.topology.v1",',
        '"schema":"zerosiscitysite.topology.v1","schema":"zerosiscitysite.topology.v1",', 1)
    duplicate_document = json.loads(json.dumps(source_document))
    duplicate_document["topology"].insert(1, dict(duplicate_document["topology"][0]))
    duplicate_document["processor_count"] += 1
    compact = lambda document: json.dumps(document, separators=(",", ":"), ensure_ascii=False)
    canonical = compact(source_document)
    negative_number = re.sub(r'("boot_time_100ns":)([0-9]+)', r'\1-\2', canonical, count=1)
    leading_zero = re.sub(r'("qpc_frequency":)([0-9]+)',
                          lambda match: match.group(1) + "0" + match.group(2), canonical, count=1)
    mutations = {
        "duplicate_root_key": duplicate_root,
        "duplicate_logical_processor": compact(duplicate_document),
        "negative_numeric_field": negative_number,
        "leading_zero_numeric_field": leading_zero,
        "trailing_bytes": canonical + "\ntrailing",
    }
    for name, payload in mutations.items():
        sidecar = build_dir / f"topology_invalid_{name}.json"
        sidecar.write_text(payload, encoding="utf-8", newline="\n")
        result = run([reader, "--check-topology", sidecar], cwd=build_dir, env=env, timeout=10)
        output = (result.stdout + result.stderr).decode("utf-8", errors="strict")
        try:
            document = json.loads(output)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Malformed topology case {name} returned non-JSON output: {error}") from error
        if result.returncode == 0 or document.get("status") != "ETL_READ_FAILED" or document.get("capture_started") is not False:
            raise RuntimeError(f"Reader accepted malformed topology case {name}: {output[-1000:]}")
        cases.append({"name": name, "return_code": result.returncode,
                      "status": document["status"], "capture_started": False,
                      "sidecar_sha256": sha(sidecar)})
    return cases


def source_hashes() -> dict[str, str]:
    return {key: sha(path) for key, path in OWNED.items()}


def dependency_overlay_path(dependency: Path, frozen_root: Path) -> Path:
    resolved = dependency.resolve(strict=True)
    try:
        resolved.relative_to(frozen_root.resolve())
        return resolved
    except ValueError:
        pass
    path_key = hashlib.sha256(str(resolved).casefold().encode("utf-8")).hexdigest()[:20]
    return frozen_root / "dependencies/files" / f"{path_key}_{resolved.name}"


def freeze_dependency_closure(records: list[dict], frozen_root: Path) -> tuple[dict, dict]:
    dependencies = {}
    for record in records:
        for translation_unit in record["translation_units"]:
            for path in translation_unit["dependencies"]:
                dependency = Path(path).resolve(strict=True)
                key = str(dependency).casefold()
                dependencies.setdefault(key, dependency)
    before = {}
    overlay = {}
    for key, dependency in sorted(dependencies.items()):
        source_hash = sha(dependency)
        destination = dependency_overlay_path(dependency, frozen_root)
        if dependency != destination.resolve(strict=False):
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(dependency, destination)
            except OSError as error:
                raise RuntimeError(f"Could not freeze compiler dependency {dependency} to {destination}: {error}") from error
        copied_hash = sha(destination)
        if source_hash != copied_hash:
            raise RuntimeError(f"Frozen dependency differs from source: {dependency}")
        before[str(dependency)] = source_hash
        overlay[str(dependency)] = {"path": str(destination), "sha256": copied_hash}
    return before, overlay


def write_conformance(evidence_dir: Path, document: dict) -> Path:
    path = evidence_dir / "conformance.json"
    # Exclusive creation preserves the evidence record if a path is reused by mistake.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--etl", type=Path)
    parser.add_argument("--topology", type=Path)
    parser.add_argument("--capture-result", type=Path)
    args = parser.parse_args()
    if (args.etl is None) != (args.topology is None) or (args.etl is None) != (args.capture_result is None):
        raise RuntimeError("--etl, --topology, and --capture-result must be specified together")
    if args.etl is not None and any(not path.is_file() for path in (args.etl, args.topology, args.capture_result)):
        raise RuntimeError("The retained ETL, capture topology, and capture result must all exist")
    missing = [str(path) for path in OWNED.values() if not path.is_file()]
    if missing:
        raise RuntimeError("CitySite CPU trace input is missing: " + ", ".join(missing))
    before = source_hashes()
    run_id, retained_build, evidence_dir = allocate_run()
    frozen = retained_build / "frozen"
    frozen_paths = {
        "header": frozen / "Source/Diagnostics/CitySiteCpuTrace.h",
        "provider": frozen / "Source/Diagnostics/CitySiteCpuTrace.cpp",
        "reader": frozen / "tools/city_site_cpu_trace_reader.cpp",
        "test": frozen / "Tests/city_site_cpu_trace.cpp",
    }
    for directory in {path.parent for path in frozen_paths.values()}:
        directory.mkdir(parents=True, exist_ok=True)

    result = {
        "schema": "zerosiscitysite.cpu_trace_conformance.v1",
        "run_id": run_id,
        "status": "RUNNING",
        "scope": "offline_provider_checks_reader_help_topology_roundtrip_and_optional_retained_etl_read",
        "capture_started": False,
        "wpr_capture_started": False,
        "etl_opened": False,
        "gamecore_loaded": False,
        "physical_multicore_proven": False,
        "source_hashes_before": before,
        "frozen_inputs": {},
        "frozen_input_hashes_after": None,
        "source_dependencies": [],
        "dependency_closure_hashes_before": None,
        "frozen_dependency_closure": None,
        "dependency_closure_hashes_after": None,
        "frozen_dependency_closure_hashes_after": None,
        "toolchain_inputs_before": {},
        "toolchain_inputs_after": None,
        "compile_inputs": [],
        "source_hashes_after": None,
        "retained_build": str(retained_build),
        "evidence_path": str(evidence_dir / "conformance.json"),
        "builds": {},
        "captured_etl": None,
        "capture_provenance": None,
        "decoder_reference_sources": [
            "https://learn.microsoft.com/en-us/windows/win32/api/tdh/nf-tdh-tdhgeteventinformation",
            "https://learn.microsoft.com/en-us/windows/win32/api/tdh/ne-tdh-tdh_context_type",
            "https://learn.microsoft.com/en-us/windows/win32/etw/process-v2-typegroup1",
            "https://learn.microsoft.com/en-us/windows/win32/etw/thread-v2-typegroup1",
            "https://learn.microsoft.com/en-us/windows/win32/etw/cswitch",
            "https://github.com/microsoft/perfview/blob/a4f670e/src/TraceEvent/Parsers/KernelTraceEventParser.cs",
        ],
        "etl_reader_result": None,
        "retained_etl_analysis": None,
    }

    try:
        for key, destination in frozen_paths.items():
            shutil.copy2(OWNED[key], destination)
            frozen_hash = sha(destination)
            if frozen_hash != before[key]:
                raise RuntimeError(f"Frozen input differs from source: {key}")
            result["frozen_inputs"][key] = {"path": str(destination), "sha256": frozen_hash}

        outputs = result["builds"]
        compile_records = []
        for optimization in ("/O2", "/Od"):
            label = optimization[1:]
            build_dir = retained_build / label
            build_dir.mkdir()
            env, compiler = environment_for(VS, "x64", build_dir)
            env.pop("ZEROSIS_CITY_SITE_CPU_TRACE", None)
            for item in toolchain_inputs(compiler, env, build_dir):
                result["toolchain_inputs_before"].setdefault(item["path"], item)
            exe, compile_log, log_path, compile_record = compile_one(
                compiler, env, build_dir, (frozen_paths["test"], frozen_paths["provider"]),
                f"city_site_cpu_trace_{label}", optimization,
                extra_link=("advapi32.lib",))
            compile_records.append(compile_record)
            result["compile_inputs"].append(compile_record)
            result["source_dependencies"].extend(
                {"translation_unit": item["source"], "document": item["dependency_document"],
                 "document_sha256": item["dependency_document_sha256"],
                 "dependency_count": len(item["dependencies"]),
                 "dependencies": item["dependencies"]}
                for item in compile_record["translation_units"])
            executed = run([exe], cwd=build_dir, env=env, timeout=20)
            output = (executed.stdout + executed.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
            expected = "CITY_SITE_CPU_TRACE_OFFLINE_PASS checks=14 capture=false GAMECORE_LOADED=false"
            if executed.returncode or output.strip() != expected:
                raise RuntimeError(f"{optimization} offline test failed ({executed.returncode}):\n{output}")
            outputs[label] = {
                "status": output.strip(), "checks": 14, "capture_started": False,
                "gamecore_loaded": False, "physical_multicore_proven": False,
                "exe": str(exe), "exe_sha256": sha(exe),
                "compile_log": str(log_path), "compile_log_sha256": sha(log_path),
                "response_file": str(build_dir / f"city_site_cpu_trace_{label}.rsp"),
            }

        build_dir = retained_build / "reader_o2"
        build_dir.mkdir()
        env, compiler = environment_for(VS, "x64", build_dir)
        env.pop("ZEROSIS_CITY_SITE_CPU_TRACE", None)
        for item in toolchain_inputs(compiler, env, build_dir):
            result["toolchain_inputs_before"].setdefault(item["path"], item)
        reader, compile_log, log_path, compile_record = compile_one(
            compiler, env, build_dir, (frozen_paths["reader"], frozen_paths["provider"]),
            "city_site_cpu_trace_reader", "/O2", extra_link=("tdh.lib", "advapi32.lib"))
        compile_records.append(compile_record)
        result["compile_inputs"].append(compile_record)
        result["source_dependencies"].extend(
            {"translation_unit": item["source"], "document": item["dependency_document"],
             "document_sha256": item["dependency_document_sha256"],
             "dependency_count": len(item["dependencies"]),
             "dependencies": item["dependencies"]}
            for item in compile_record["translation_units"])

        help_json, help_output = run_json([reader, "--help"], cwd=build_dir, env=env, timeout=10,
                                          label="Reader help")
        if help_json.get("capture_started") is not False or help_json.get("status") != "HELP":
            raise RuntimeError("Reader help contract differs")
        outputs["reader_help"] = {
            "exe": str(reader), "exe_sha256": sha(reader), "compile_log": str(log_path),
            "compile_log_sha256": sha(log_path), "json": help_json,
            "capture_started": False, "etl_opened": False, "gamecore_loaded": False,
            "physical_multicore_proven": False,
        }

        sidecar = build_dir / "topology.json"
        write_json, write_output = run_json([reader, "--write-topology", sidecar], cwd=build_dir,
                                            env=env, timeout=10, label="Topology snapshot write")
        if write_json.get("status") != "TOPOLOGY_SNAPSHOT_WRITTEN" or write_json.get("capture_started") is not False:
            raise RuntimeError("Reader topology write contract differs")
        topology_document = json.loads(sidecar.read_text(encoding="utf-8"))
        validate_topology_schema(topology_document)

        check_json, check_output = run_json([reader, "--check-topology", sidecar], cwd=build_dir,
                                            env=env, timeout=10, label="Topology snapshot read")
        if (check_json.get("status") != "TOPOLOGY_SIDECAR_VALID" or
                check_json.get("capture_started") is not False or
                check_json.get("etl_opened") is not False or
                check_json.get("gamecore_loaded") is not False or
                check_json.get("physical_multicore_proven") is not False or
                check_json.get("processor_count") != topology_document["processor_count"]):
            raise RuntimeError("Reader topology read contract differs")
        outputs["topology_roundtrip"] = {
            "sidecar": str(sidecar), "sidecar_sha256": sha(sidecar),
            "schema": topology_document["schema"],
            "processor_count": topology_document["processor_count"],
            "write_json": write_json, "read_json": check_json,
            "capture_started": False, "etl_opened": False, "gamecore_loaded": False,
            "physical_multicore_proven": False,
        }
        outputs["topology_negative_cases"] = {
            "status": "MALFORMED_TOPOLOGY_REJECTED",
            "cases": reject_topology_cases(reader, build_dir, env, topology_document),
            "etl_opened": False, "gamecore_loaded": False,
            "capture_started": False, "physical_multicore_proven": False,
        }

        if args.etl is not None:
            etl_hash_before = sha(args.etl)
            topology_hash_before = sha(args.topology)
            capture_result_hash_before = sha(args.capture_result)
            capture_provenance = json.loads(args.capture_result.read_text(encoding="utf-8"))
            if (capture_provenance.get("capture_started") is not True or
                    capture_provenance.get("gamecore_loaded") is not True or
                    Path(capture_provenance.get("etl", {}).get("path", "")).resolve() != args.etl.resolve() or
                    capture_provenance.get("etl", {}).get("sha256") != etl_hash_before or
                    Path(capture_provenance.get("topology_before", {}).get("path", "")).resolve() != args.topology.resolve() or
                    capture_provenance.get("topology_before", {}).get("sha256") != topology_hash_before):
                raise RuntimeError("Capture result does not bind this ETL and pre-capture topology")
            etl_result = run([reader, args.etl.resolve(), "--topology", args.topology.resolve()],
                             cwd=build_dir, env=env, timeout=180)
            raw = (etl_result.stdout + etl_result.stderr).decode("utf-8", errors="strict")
            try:
                etl_json = json.loads(raw)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"Reader returned non-JSON retained-ETL output: {error}: {raw[-3000:]}") from error
            if not isinstance(etl_json, dict) or etl_json.get("capture_started") is not False:
                raise RuntimeError("Reader ETL result violated its no-capture contract")
            etl_hash_after = sha(args.etl)
            topology_hash_after = sha(args.topology)
            captured_etl = {
                "path": str(args.etl.resolve()), "sha256_before": etl_hash_before,
                "sha256_after": etl_hash_after, "topology_path": str(args.topology.resolve()),
                "topology_sha256_before": topology_hash_before,
                "topology_sha256_after": topology_hash_after,
                "captured_by_this_verifier": False,
                "capture_result_path": str(args.capture_result.resolve()),
                "capture_result_sha256_before": capture_result_hash_before,
                "capture_result_sha256_after": sha(args.capture_result),
            }
            if etl_hash_before != etl_hash_after or topology_hash_before != topology_hash_after:
                raise RuntimeError("The retained ETL or capture topology changed during reader analysis")
            etl_log = build_dir / "retained_etl_reader.json"
            etl_log.write_text(raw, encoding="utf-8", newline="\n")
            etl_reader_record = {
                "return_code": etl_result.returncode, "json": etl_json,
                "output_path": str(etl_log), "output_sha256": sha(etl_log),
                "reader_etl_opened": etl_json.get("etl_opened"),
                "reader_process_gamecore_loaded": False,
                "capture_started_by_this_verifier": False,
            }
            if etl_result.returncode == 0 and etl_json.get("status") == "ETW_DISTINCT_CORE_OVERLAP_PROVEN":
                retained_etl_status = "ETW_DISTINCT_CORE_OVERLAP_PROVISIONAL"
            elif etl_json.get("status") == "ETL_READ_FAILED":
                retained_etl_status = "ETL_READ_DIAGNOSTIC_COMPLETE"
            else:
                retained_etl_status = "ETL_READ_NO_PROOF"
            capture_record = {
                "path": str(args.capture_result.resolve()),
                "sha256": capture_result_hash_before,
                "capture_id": capture_provenance.get("capture_id"),
                "capture_started": capture_provenance.get("capture_started"),
                "gamecore_loaded": capture_provenance.get("gamecore_loaded"),
                "sdk_run_id": capture_provenance.get("sdk_run_id"),
                "sdk_process_id": capture_provenance.get("process_id"),
                "wpr_stop_exit_code": next((item.get("exit_code") for item in capture_provenance.get("commands", [])
                                             if item.get("name") == "stop"), None),
            }
            result["retained_etl_analysis"] = {
                "status": retained_etl_status,
                "captured_etl": captured_etl,
                "reader_result": etl_reader_record,
                "capture_provenance": capture_record,
                "capture_started_by_this_verifier": False,
                "reader_process_gamecore_loaded": False,
                "physical_multicore_proven": False,
                "physical_multicore_claimed_by_reader": etl_json.get("physical_multicore_proven"),
                "decoder_source_revision": {
                    "url": "https://github.com/microsoft/perfview/blob/a4f670e/src/TraceEvent/Parsers/KernelTraceEventParser.cs",
                    "revision": "a4f670e",
                    "scope": "versioned classic Thread and CSwitch field offsets; supplemental to Microsoft Learn typegroup schemas",
                },
            }
            # The conformance record keeps its original offline-only status and flags.
            result["status"] = "CITY_SITE_CPU_TRACE_OFFLINE_PASS"
            result["capture_started"] = False
            result["wpr_capture_started"] = False
            result["etl_opened"] = False
            result["gamecore_loaded"] = False
            result["physical_multicore_proven"] = False

        dependency_before, frozen_dependency_closure = freeze_dependency_closure(compile_records, frozen)
        dependency_after = {path: sha(Path(path)) for path in dependency_before}
        result["dependency_closure_hashes_before"] = dependency_before
        result["frozen_dependency_closure"] = frozen_dependency_closure
        result["dependency_closure_hashes_after"] = dependency_after
        if dependency_before != dependency_after:
            raise RuntimeError("A compiler dependency changed during isolated verification")
        frozen_after = {
            source: sha(Path(item["path"]))
            for source, item in frozen_dependency_closure.items()
        }
        result["frozen_dependency_closure_hashes_after"] = frozen_after
        if frozen_after != dependency_before:
            raise RuntimeError("A frozen compiler dependency changed during isolated verification")

        toolchain_after = {
            path: {"role": item["role"], "sha256": sha(Path(path))}
            for path, item in result["toolchain_inputs_before"].items()
        }
        result["toolchain_inputs_after"] = toolchain_after
        if any(item["sha256"] != toolchain_after[path]["sha256"]
               for path, item in result["toolchain_inputs_before"].items()):
            raise RuntimeError("A compiler or build-helper input changed during isolated verification")

        frozen_after = {key: sha(path) for key, path in frozen_paths.items()}
        result["frozen_input_hashes_after"] = frozen_after
        expected_frozen = {key: value["sha256"] for key, value in result["frozen_inputs"].items()}
        if expected_frozen != frozen_after:
            raise RuntimeError("A frozen compile input changed during isolated verification")
        after = source_hashes()
        result["source_hashes_after"] = after
        if before != after:
            raise RuntimeError("A guarded source changed during isolated verification")
        if result["status"] == "RUNNING":
            result["status"] = "CITY_SITE_CPU_TRACE_OFFLINE_PASS"
        if (args.capture_result is not None and
                result["retained_etl_analysis"]["captured_etl"]["capture_result_sha256_before"] != sha(args.capture_result)):
            raise RuntimeError("The immutable capture result changed during reader analysis")
        result["reader_artifact"] = {
            "path": str(reader), "sha256": sha(reader), "format": "PE32+ x64 executable",
            "compile_record_index": len(compile_records) - 1,
        }
        result["artifacts"] = {
            "build_files": {
                str(path.relative_to(retained_build)): sha(path)
                for path in retained_build.rglob("*") if path.is_file()
            },
            "conformance_written_last": True,
        }
        conformance = write_conformance(evidence_dir, result)
        print(json.dumps({"status": result["status"], "run_id": run_id,
                          "conformance": str(conformance), "build": str(retained_build),
                          "capture_started": False, "gamecore_loaded": False,
                          "physical_multicore_proven": result["physical_multicore_proven"]}, sort_keys=True))
        return 0
    except Exception as error:
        try:
            result["source_hashes_after"] = source_hashes()
            if all(path.is_file() for path in frozen_paths.values()):
                result["frozen_input_hashes_after"] = {key: sha(path) for key, path in frozen_paths.items()}
        except OSError:
            result["source_hashes_after"] = None
        result["status"] = "CITY_SITE_CPU_TRACE_OFFLINE_FAIL"
        result["error"] = f"{type(error).__name__}: {error}"
        result["error_traceback"] = traceback.format_exc()
        try:
            write_conformance(evidence_dir, result)
        except FileExistsError:
            pass
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"verify_city_site_cpu_trace: {error}", file=sys.stderr)
        raise SystemExit(1)
