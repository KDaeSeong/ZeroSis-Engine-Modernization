"""Record x64 diagnostics and link using platform libraries plus explicitly verified providers."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess

from collect_baseline import PROJECT, digest, read_text
from native_build import environment_for


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    parser.add_argument("--lua-provider", type=Path, help="Verified /MD provider build report")
    parser.add_argument("--stream-provider", type=Path, help="Verified /MD stream provider build report")
    parser.add_argument("--serialization-provider", type=Path, help="Verified enum/string serialization provider build report")
    parser.add_argument("--foundation-provider", type=Path, help="Verified CRC/lock/clock/aligned-memory provider build report")
    parser.add_argument("--temp-heap-provider", type=Path, help="Verified atomic arena and engine host binding provider build report")
    parser.add_argument("--auto-archive-provider", type=Path, help="Verified FINAL_RELEASE automatic archive provider build report")
    parser.add_argument("--database-provider", type=Path, help="Verified x64 database DLL/import-library component report")
    parser.add_argument("--flua-provider", type=Path, help="Verified x64 Lua value/table/protected-call bridge")
    parser.add_argument("--string-provider", type=Path, help="Verified x64 FString/UTF/string-field provider")
    parser.add_argument("--localization-provider", type=Path, help="Verified x64 String/parser/dictionary/ICU provider")
    parser.add_argument("--world-builder-types-provider", type=Path, help="Verified x64 WorldBuilder type maps and groups")
    parser.add_argument("--world-builder-mod-data-provider", type=Path, help="Verified x64 WorldBuilder mod-data schema, values and bounded wire reader")
    parser.add_argument("--world-builder-map-provider", type=Path, help="Verified x64 actual SDK map object and file API provider")
    parser.add_argument("--filesystem-provider", type=Path, help="Verified native Windows FIFile provider and map disk I/O")
    parser.add_argument("--logging-provider", type=Path, help="Verified native SDK logger and literal text callers")
    parser.add_argument("--debug-provider", type=Path, help="Verified native Windows SDK symbol service")
    args = parser.parse_args()
    evidence = PROJECT / "evidence/sdk_x64"
    compilation = json.loads((evidence / "build_result.json").read_text(encoding="utf-8"))
    if compilation["status"] != "SDK_X64_ALL_OBJECTS_COMPILED":
        raise RuntimeError("Complete x64 compilation required before the link probe")
    objects = compilation["objects"]
    if any(digest(Path(row["path"])) != row["sha256"] for row in objects):
        raise RuntimeError("Compiled object changed before link probe")
    compile_inputs=[compilation['patch_specification'],compilation['manifest'],*compilation['support_inputs']]
    if any(digest(Path(row['path']))!=row['sha256'] for row in compile_inputs):
        raise RuntimeError('SDK patch/header ABI changed since GameCore compilation; rebuild before linking')
    compiled_manifest=json.loads(Path(compilation['manifest']['path']).read_text(encoding='utf-8'))
    if any(digest(Path(row['port']))!=row['port_sha256'] for row in compiled_manifest):
        raise RuntimeError('SDK source changed since GameCore compilation; rebuild before linking')
    providers = []
    if args.lua_provider:
        provider_report = args.lua_provider.resolve()
        provider = json.loads(provider_report.read_text(encoding="utf-8"))
        conformance_path = PROJECT / "evidence/lua_reference/provider/conformance.json"
        conformance = json.loads(conformance_path.read_text(encoding="utf-8"))
        source_manifest = json.loads(Path(provider["source_manifest"]["path"]).read_text(encoding="utf-8"))
        required = [provider[key] for key in ("library", "builder", "source_manifest", "patches", "compiler", "log", "response", "sdk_configuration")]
        required += source_manifest + provider["objects"]
        required += [{"path": path, "sha256": value} for path, value in conformance["input_sha256"].items()]
        required += [r[key] for r in conformance["runs"] for key in ("trace", "scripts", "build")]
        if (provider["status"] != "LUA51_X64_MD_PROVIDER_BUILT" or provider["runtime"] != "/MD"
                or conformance["status"] != "SDK_LUA_X86_X64_CONFORMANCE_PASS" or conformance["different_results"]
                or conformance["runtime"] != "MD" or conformance["library"] != provider["library"]
                or any(digest(Path(row["path"])) != row["sha256"] for row in required)):
            raise RuntimeError("Lua provider lacks current source/build/reference-conformance evidence")
        providers.append({"name": "Lua51", "library": provider["library"],
            "build_report": {"path": str(provider_report), "sha256": digest(provider_report)},
            "conformance": {"path": str(conformance_path), "sha256": digest(conformance_path)},
            "runtime": "/MD", "scope": "TESTED_PROVIDER_NOT_FULL_GAME_ACCEPTANCE"})
    if args.stream_provider:
        from stream_evidence import validate
        _, _, entry = validate(args.stream_provider)
        providers.append(entry)
    if args.serialization_provider:
        if not args.stream_provider: raise RuntimeError('Serialization requires its tested stream provider')
        from serialization_evidence import validate
        _, _, entry = validate(args.serialization_provider)
        providers.append(entry)
    if args.foundation_provider:
        from foundation_evidence import validate
        _, _, entry = validate(args.foundation_provider)
        providers.append(entry)
    if args.temp_heap_provider:
        if not args.foundation_provider: raise RuntimeError('TempHeap requires its tested foundation allocator provider')
        from temp_heap_evidence import validate
        _, _, entry = validate(args.temp_heap_provider)
        providers.append(entry)
    if args.auto_archive_provider:
        if not args.stream_provider or not args.serialization_provider:
            raise RuntimeError('AutoArchive requires its tested stream and serialization providers')
        from auto_archive_evidence import validate
        _, _, entry = validate(args.auto_archive_provider)
        providers.append(entry)
    if args.database_provider:
        from database_evidence import validate
        _, _, entry = validate(args.database_provider)
        providers.append(entry)
    if args.flua_provider:
        if not args.lua_provider or not args.foundation_provider:
            raise RuntimeError('FLua requires its tested Lua runtime and Foundation lock provider')
        from flua_evidence import validate
        flua,_,entry=validate(args.flua_provider)
        lua_entry=next(p for p in providers if p['name']=='Lua51')
        if flua['x64']['libraries'][1]!=lua_entry['library'] or flua['lua_provider']!=lua_entry['build_report']:
            raise RuntimeError('FLua and GameCore Lua providers differ')
        providers.append(entry)
    if args.string_provider:
        if not args.stream_provider:raise RuntimeError('Strings requires its tested stream provider')
        from string_evidence import validate
        strings,_,entry=validate(args.string_provider)
        if strings['streams_provider']!=next(p for p in providers if p['name']=='Streams'):
            raise RuntimeError('Strings and GameCore stream providers differ')
        providers.append(entry)
    if args.localization_provider:
        if not args.database_provider:raise RuntimeError('Localization requires its tested Database DLL')
        from localization_provider_evidence import validate
        localization,_,entry=validate(args.localization_provider)
        if localization['dependencies']['database']!=next(p for p in providers if p['name']=='Database')['build_report']:
            raise RuntimeError('Localization and GameCore database providers differ')
        providers.append(entry)
    if args.world_builder_types_provider:
        from world_builder_types_evidence import validate
        world_types,_,entry=validate(args.world_builder_types_provider)
        if world_types['sdk_port_manifest']!=compilation['manifest']:
            raise RuntimeError('WorldBuilder type provider and GameCore SDK baselines differ')
        providers.append(entry)
    if args.world_builder_mod_data_provider:
        if not args.world_builder_types_provider or not args.foundation_provider:
            raise RuntimeError('WorldBuilder mod data requires its tested Types and Foundation providers')
        from world_builder_mod_data_evidence import validate
        mod_data,_,entry=validate(args.world_builder_mod_data_provider)
        if mod_data['sdk_port_manifest']!=compilation['manifest'] or mod_data['sdk_patch_specification']!=compilation['patch_specification']:
            raise RuntimeError('WorldBuilder mod data and GameCore SDK declarations differ')
        if mod_data['dependencies']!=[next(p for p in providers if p['name']==name) for name in ('WorldBuilderTypes','Foundation')]:
            raise RuntimeError('WorldBuilder mod-data dependencies differ')
        providers.append(entry)
    if args.world_builder_map_provider:
        from world_builder_map_bridge_evidence import provider as validate_map
        map_build,_,entry=validate_map(args.world_builder_map_provider)
        if map_build['sdk_port_manifest']!=compilation['manifest'] or map_build['sdk_patch_specification']!=compilation['patch_specification']:
            raise RuntimeError('WorldBuilder map and GameCore SDK declarations differ')
        required=('WorldBuilderTypes','WorldBuilderModData','Strings','Foundation')
        if any(not any(p['name']==name for p in providers) for name in required) or map_build['dependencies']!=[next(p for p in providers if p['name']==name) for name in required]:
            raise RuntimeError('WorldBuilder map dependencies differ')
        providers.append(entry)
    if args.filesystem_provider:
        from filesystem_evidence import validate as validate_filesystem
        filesystem,_,entry=validate_filesystem(args.filesystem_provider)
        if filesystem['map_provider'] not in providers:
            raise RuntimeError('Filesystem requires the exact SDK map provider used by native disk tests')
        providers.append(entry)
    if args.logging_provider:
        from logging_evidence import validate as validate_logging
        logging,_,entry=validate_logging(args.logging_provider)
        if logging['filesystem_provider'] not in providers or logging['sdk_port_manifest']!=compilation['manifest'] or logging['sdk_patch_specification']!=compilation['patch_specification']:
            raise RuntimeError('Logger and GameCore dependencies or SDK inputs differ')
        providers.append(entry)
    patch_plan=json.loads(Path(compilation['patch_specification']['path']).read_text(encoding='utf-8'))
    bootstrap_conformance=None
    globals_cleanup_conformance=None
    construction_conformance=None
    host_binding_conformance=None
    database_postprocess_conformance=None
    database_loader_conformance=None
    info_cleanup_conformance=None
    database_cache_conformance=None
    startup_owners_conformance=None
    gc_lifecycle_conformance=None
    lua_enum_conformance=None
    lua_registration_conformance=None
    lua_fractal_conformance=None
    fractal_numeric_conformance=None
    lua_borrowed_conformance=None
    if args.debug_provider:
        from debug_evidence import validate_component as validate_debug
        debug,_,entry=validate_debug(args.debug_provider)
        if debug['sdk_port_manifest']!=compilation['manifest'] or debug['sdk_patch_specification']!=compilation['patch_specification']:
            raise RuntimeError('Debugger and GameCore SDK inputs differ')
        providers.append(entry)
    if any(p['id'].startswith('bootstrap_callers_') for p in patch_plan['patches']):
        if not args.debug_provider:raise RuntimeError('Explicit bootstrap requires its verified symbol provider')
        from bootstrap_evidence import validate as validate_bootstrap
        _,_,bootstrap_conformance=validate_bootstrap()
    if any(p['id'].startswith('globals_callers_') for p in patch_plan['patches']):
        from globals_cleanup_evidence import validate as validate_globals_cleanup
        _,_,globals_cleanup_conformance=validate_globals_cleanup()
    if any(p['id'].startswith('construction_callers_') for p in patch_plan['patches']):
        from construction_evidence import validate as validate_construction
        _,_,construction_conformance=validate_construction()
    if any(p['id'].startswith('host_callers_') for p in patch_plan['patches']):
        from host_binding_evidence import validate as validate_host_binding
        _,_,host_binding_conformance=validate_host_binding()
    if any(p['id'].startswith('db_postprocess_') for p in patch_plan['patches']):
        from database_postprocess_evidence import validate as validate_database_postprocess
        _,_,database_postprocess_conformance=validate_database_postprocess()
    if any(p['id'].startswith('db_loader_') for p in patch_plan['patches']):
        from database_loader_evidence import validate as validate_database_loader
        _,_,database_loader_conformance=validate_database_loader()
    if any(p['id'].startswith('info_cleanup_') for p in patch_plan['patches']):
        from info_cleanup_evidence import validate as validate_info_cleanup
        _,_,info_cleanup_conformance=validate_info_cleanup()
    if any(p['id'].startswith('db_cache_') for p in patch_plan['patches']):
        from database_cache_evidence import validate as validate_database_cache
        _,_,database_cache_conformance=validate_database_cache()
    if any(p['id'].startswith('startup_owners_') for p in patch_plan['patches']):
        from startup_owners_evidence import validate as validate_startup_owners
        _,_,startup_owners_conformance=validate_startup_owners()
    if any(p['id'].startswith('gc_lifecycle_') for p in patch_plan['patches']):
        from gc_lifecycle_evidence import validate as validate_gc_lifecycle
        _,_,gc_lifecycle_conformance=validate_gc_lifecycle()
    if any(p['id'].startswith('lua_enum_') for p in patch_plan['patches']):
        from lua_enums_evidence import validate as validate_lua_enums
        _,_,lua_enum_conformance=validate_lua_enums()
    if any(p['id'].startswith('lua_registration_') for p in patch_plan['patches']):
        from lua_registration_evidence import validate as validate_lua_registration
        _,_,lua_registration_conformance=validate_lua_registration()
    if any(p['id'].startswith('lua_fractal_') for p in patch_plan['patches']):
        from lua_fractal_evidence import validate as validate_lua_fractal
        _,_,lua_fractal_conformance=validate_lua_fractal()
    if any(p['id'].startswith('fractal_numeric_') for p in patch_plan['patches']):
        from fractal_numeric_evidence import validate as validate_fractal_numeric
        _,_,fractal_numeric_conformance=validate_fractal_numeric()
    if any(p['id'].startswith('lua_borrowed_') for p in patch_plan['patches']):
        from lua_borrowed_evidence import validate as validate_lua_borrowed
        _,_,lua_borrowed_conformance=validate_lua_borrowed()
    if any(p['id'].startswith('logging_callers_') for p in patch_plan['patches']) and not args.logging_provider:
        raise RuntimeError('Patched logging callers require their verified native logger')
    caller_conformance=None
    if any(p['id'].startswith('temp_callers_') for p in patch_plan['patches']):
        from temp_heap_caller_evidence import validate
        callers,caller_conformance=validate()
        if any(entry not in providers for entry in callers['providers']):
            raise RuntimeError('Patched temporary-memory callers require the exact tested providers')
    port = PROJECT / "Source/SDK_BNW_x64"
    diagnostics = {}
    for phase in compilation["executions"]:
        for line in read_text(Path(phase["log"])).splitlines():
            found = re.match(r"^(.*)\((\d+)\): (warning|(?:fatal )?error) ([A-Z]+\d+): (.*)$", line)
            if found:
                file, number, kind, code, message = found.groups()
                source_path = Path(file).resolve()
                relative = source_path.relative_to(port).as_posix() if source_path.is_relative_to(port) else str(source_path)
                key = relative.lower(), int(number), kind, code
                if key not in diagnostics:
                    category = ("source_encoding" if code == "C4819" else "pointer_width" if code in {"C4302", "C4311", "C4312"}
                                else "numeric_or_container_narrowing" if code in {"C4244", "C4267", "C4838"}
                                else "legacy_declaration_or_api")
                    diagnostics[key] = {"file": relative, "line": int(number), "severity": kind, "code": code,
                                        "category": category, "example_message": message, "occurrences": 0}
                diagnostics[key]["occurrences"] += 1
    warnings_path = evidence / "compiler_diagnostics.csv"
    with warnings_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["file", "line", "severity", "code", "category", "example_message", "occurrences"])
        writer.writeheader()
        writer.writerows(diagnostics[key] for key in sorted(diagnostics))
    profile = ''.join('_'+entry['name'].lower() for entry in providers)
    # Long provider lists can exceed the linker's Windows output-path limit.
    # Keep the full provider records below; use a stable compact path when needed.
    path_profile=profile
    directory = PROJECT / "Build/SDK_x64" / f"attempt_{compilation['attempt']:03d}" / ("link_probe" + path_profile)
    if len(str(directory / "CvGameCoreDLL_Expansion2_x64_probe.dll"))>=240:
        path_profile='_p_'+hashlib.sha256(profile.encode('utf-8')).hexdigest()[:16]
        directory = PROJECT / "Build/SDK_x64" / f"attempt_{compilation['attempt']:03d}" / ("link_probe" + path_profile)
    directory.mkdir(parents=True, exist_ok=True)
    env, compiler = environment_for(args.vs, "x64", directory)
    linker = Path(compiler).parent / "link.exe"
    definition = port / "CvGameCoreDLL_Expansion2/CvGameCoreDLL.def"
    output = directory / "CvGameCoreDLL_Expansion2_x64_probe.dll"
    mapfile = directory / "CvGameCoreDLL_Expansion2_x64_probe.map"
    # Never use x86 SDK libraries, /FORCE, or placeholder implementations.
    system_libraries = [name + ".lib" for name in ("kernel32", "user32", "gdi32", "winspool", "comdlg32", "advapi32",
                         "shell32", "ole32", "oleaut32", "uuid", "odbc32", "odbccp32", "winmm")]
    if args.debug_provider:system_libraries.append('dbghelp.lib')
    flags = ["/NOLOGO", "/DLL", "/MACHINE:X64", "/INCREMENTAL:NO", "/OPT:REF", "/OPT:ICF",
             f'/DEF:"{definition}"', f'/OUT:"{output}"', f'/IMPLIB:"{directory / "probe.lib"}"', f'/MAP:"{mapfile}"']
    flags += [f'"{row["path"]}"' for row in objects]
    flags += [f'"{row["library"]["path"]}"' for row in providers] + system_libraries
    response = directory / "link.rsp"
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    log = evidence / f"link_probe_attempt_{compilation['attempt']:03d}{path_profile}.log"
    with log.open("wb") as stream:
        process = subprocess.run([str(linker), f"@{response}"], cwd=directory, env=env,
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=180,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    text = read_text(log)
    borrowed_registry_symbol = None
    if process.returncode == 0 and lua_borrowed_conformance:
        registry_lines = [line.strip() for line in read_text(mapfile).splitlines()
                          if '?state@?1??State@ZeroSisLuaBorrowed@@' in line]
        if len(registry_lines) != 1:
            raise RuntimeError('Integrated DLL must contain exactly one shared borrowed-reference registry')
        borrowed_registry_symbol = registry_lines[0]
    errors = [line for line in text.splitlines() if re.search(r"\b(?:fatal )?error LNK\d+", line)]
    symbol_rows = {}
    unparsed = []
    for line in errors:
        if "LNK2001" not in line and "LNK2019" not in line:
            continue
        payload = re.split(r"error LNK(?:2001|2019):\s*", line, maxsplit=1)[1]
        # The first C++ decorated symbol is unresolved; a second one in LNK2019
        # names its caller. Korean C diagnostics put the target before a quote.
        c_name = re.match(r'([A-Za-z_][A-Za-z_0-9@$?]*)(?="|$)', payload)
        decorated = re.search(r"\((\?[^\s()]+|__imp_[^\s()]+)\)", payload)
        trailing_c = re.search(r"\s([A-Za-z_][A-Za-z_0-9@$?]*)$", payload)
        if c_name:
            symbol = c_name.group(1)
        elif decorated:
            symbol = decorated.group(1)
        elif trailing_c:
            symbol = trailing_c.group(1)
        else:
            unparsed.append(line)
            continue
        symbol_rows.setdefault(symbol, line)
    unresolved_path = evidence / "link_unresolved_candidates.csv"
    with unresolved_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["decorated_or_c_symbol", "diagnostic_example"])
        writer.writeheader()
        writer.writerows({"decorated_or_c_symbol": symbol, "diagnostic_example": line} for symbol, line in sorted(symbol_rows.items()))
    summary_matches = re.findall(r"LNK1120:\s*(\d+)", text)
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "X64_LINK_BLOCKERS_CAPTURED" if process.returncode else "X64_LINK_PROBE_SUCCEEDED_UNTESTED",
              "build_attempt": compilation["attempt"], "build_result_sha256": digest(evidence / "build_result.json"),
              "diagnostics": {"path": str(warnings_path), "sha256": digest(warnings_path)},
              "diagnostic_locations": len(diagnostics),
              "diagnostic_location_codes": dict(Counter(row["code"] for row in diagnostics.values())),
              "diagnostic_categories": dict(Counter(row["category"] for row in diagnostics.values())),
              "link_exit_code": process.returncode, "linker": str(linker), "linker_sha256": digest(linker),
              "link_log": {"path": str(log), "sha256": digest(log)},
              "link_response": {"path": str(response), "sha256": digest(response)}, "platform_libraries": system_libraries,
              "link_map": {"path": str(mapfile), "sha256": digest(mapfile)} if process.returncode==0 else None,
              "lua_borrowed_shared_registry_symbol": borrowed_registry_symbol,
              "providers": providers, "provider_profile": profile, "output_path_profile": path_profile,
              "caller_patch_conformance":caller_conformance,"bootstrap_caller_conformance":bootstrap_conformance,
              "globals_cleanup_conformance":globals_cleanup_conformance,
              "construction_conformance":construction_conformance,
              "host_binding_conformance":host_binding_conformance,
              "database_postprocess_conformance":database_postprocess_conformance,
              "database_loader_conformance":database_loader_conformance,
              "info_cleanup_conformance":info_cleanup_conformance,
              "database_cache_conformance":database_cache_conformance,
              "startup_owners_conformance":startup_owners_conformance,
              "gc_lifecycle_conformance":gc_lifecycle_conformance,
              "lua_enum_conformance":lua_enum_conformance,
              "lua_registration_conformance":lua_registration_conformance,
              "lua_fractal_conformance":lua_fractal_conformance,
              "fractal_numeric_conformance":fractal_numeric_conformance,
              "lua_borrowed_conformance":lua_borrowed_conformance,
              "link_error_lines": len(errors), "link_error_code_counts": dict(Counter(re.search(r"error (LNK\d+)", line).group(1) for line in errors)),
              "linker_unresolved_symbol_total": int(summary_matches[-1]) if summary_matches else (0 if process.returncode==0 else None),
              "unresolved_candidates": {"path": str(unresolved_path), "sha256": digest(unresolved_path)},
              "parsed_unresolved_candidate_count": len(symbol_rows),
              "unparsed_unresolved_diagnostics": unparsed,
              "parsed_count_matches_linker": (bool(summary_matches) and len(symbol_rows) == int(summary_matches[-1]))
                    or (process.returncode==0 and not errors and not symbol_rows and not unparsed and output.is_file()),
              "generated_dll": {"path": str(output), "sha256": digest(output)} if output.is_file() else None,
              "missing_dependency_scope": "Remaining SDK providers unavailable in x64; only listed verified candidates included; x86 archives excluded",
              "parser_is_complete_symbol_graph": False, "game_launched": False, "runtime_verified": False,
              "analyzer": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))}}
    if process.returncode and not result['parsed_count_matches_linker']:
        result['status']='X64_LINK_TOOL_FAILURE'
    (evidence / "link_analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if result['status']=='X64_LINK_TOOL_FAILURE':
        raise RuntimeError('Link did not produce a complete unresolved-symbol result; inspect '+str(log))
    if [entry['name'] for entry in providers] == ['Lua51']:
        baseline = PROJECT / "evidence/lua_provider/link_before/link_unresolved_candidates.csv"
        with baseline.open(encoding="utf-8-sig") as stream:
            old_names = {row["decorated_or_c_symbol"] for row in csv.DictReader(stream)}
        current_names = set(symbol_rows)
        after_path=PROJECT/'evidence/lua_provider/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta = {"before": len(old_names), "after": len(current_names), "resolved": sorted(old_names-current_names),
            "added": sorted(current_names-old_names),
            "remaining_lua_c_api": sorted(name for name in current_names if name.startswith(("lua_", "luaL_", "luaopen_"))),
            "gamecore_linked": process.returncode == 0,
            "evidence": [{"path": str(path), "sha256": digest(path)} for path in (baseline, after_path)]}
        (PROJECT / "evidence/lua_provider/link_delta.json").write_text(json.dumps(delta, indent=2) + "\n", encoding="utf-8")
    if [entry['name'] for entry in providers] == ['Lua51','Streams']:
        baseline = PROJECT / 'evidence/streams/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/streams/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'remaining_stream_symbols':sorted(n for n in symbol_rows if any(s in n for s in ('FDataStream@@','FMemoryStream@@'))),
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/streams/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if [entry['name'] for entry in providers] == ['Lua51','Streams','Serialization']:
        baseline=PROJECT/'evidence/serialization/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/serialization/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/serialization/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if [entry['name'] for entry in providers] == ['Lua51','Streams','Serialization','Foundation']:
        baseline=PROJECT/'evidence/foundation/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/foundation/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/foundation/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if [entry['name'] for entry in providers] == ['Lua51','Streams','Serialization','Foundation','TempHeap'] and not caller_conformance:
        baseline=PROJECT/'evidence/temp_heap/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/temp_heap/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/temp_heap/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if caller_conformance and [entry['name'] for entry in providers] == ['Lua51','Streams','Serialization','Foundation','TempHeap']:
        baseline=PROJECT/'evidence/temp_heap_callers/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/temp_heap_callers/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'no_longer_required':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'scope':'Changed caller requirements, not additional implemented providers',
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/temp_heap_callers/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if [entry['name'] for entry in providers] == ['Lua51','Streams','Serialization','Foundation','TempHeap','AutoArchive']:
        baseline=PROJECT/'evidence/auto_archive/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/auto_archive/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'remaining_archive_symbols':sorted(n for n in symbol_rows if any(s in n for s in ('FAutoArchive@@','FAutoVariableBase@@','?toString@FSerialization@@'))),
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/auto_archive/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
        if any(p['id'].startswith('auto_callers_') for p in patch_plan['patches']):
            baseline=PROJECT/'evidence/auto_archive_callers/link_before/link_unresolved_candidates.csv'
            with baseline.open(encoding='utf-8-sig') as stream:
                old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
            after_path=PROJECT/'evidence/auto_archive_callers/link_after/link_unresolved_candidates.csv'
            after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
            delta={'before':len(old_names),'after':len(symbol_rows),'no_longer_required':sorted(old_names-set(symbol_rows)),
                'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
                'scope':'Recompiled x64 variable ABI and callers; not additional missing-provider closure',
                'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
            (PROJECT/'evidence/auto_archive_callers/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if [entry['name'] for entry in providers]==['Lua51','Streams','Serialization','Foundation','TempHeap','AutoArchive','Database']:
        baseline=PROJECT/'evidence/database/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/database/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'remaining_database_symbols':sorted(n for n in symbol_rows if '@Database@@' in n),
            'scope':'Real x64 database DLL import library; GameCore never loaded',
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/database/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if [entry['name'] for entry in providers]==['Lua51','Streams','Serialization','Foundation','TempHeap','AutoArchive','Database','FLua']:
        baseline=PROJECT/'evidence/flua/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/flua/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'remaining_flua_symbols':sorted(n for n in symbol_rows if '@FLua@@' in n),
            'scope':'Actual FLua value/table/protected-call bodies using tested Lua and Foundation; GameCore never loaded',
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/flua/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if [entry['name'] for entry in providers]==['Lua51','Streams','Serialization','Foundation','TempHeap','AutoArchive','Database','FLua','Strings']:
        baseline=PROJECT/'evidence/strings/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/strings/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'remaining_string_symbols':sorted(n for n in symbol_rows if any(key in n for key in ('FStringA','FStringW','@CvStringUtils@@'))),
            'scope':'Actual FString/UTF/field-stream bodies using the tested stream provider; GameCore never loaded',
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/strings/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if providers and providers[-1]['name']=='Localization':
        baseline=PROJECT/'evidence/localization/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/localization/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'remaining_localization_symbols':sorted(n for n in symbol_rows if '@Localization@@' in n),
            'scope':'Actual String/parser/dictionary and owned ICU component linked; GameCore never loaded',
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/localization/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if providers and providers[-1]['name']=='WorldBuilderTypes':
        baseline=PROJECT/'evidence/world_builder/link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/world_builder/link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'scope':'Actual SDK type map/group bodies; complete map and mod-data providers pending; GameCore never loaded',
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/world_builder/types/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    if providers and providers[-1]['name']=='WorldBuilderModData':
        baseline=PROJECT/'evidence/world_builder/mod_data_link_before/link_unresolved_candidates.csv'
        with baseline.open(encoding='utf-8-sig') as stream:
            old_names={row['decorated_or_c_symbol'] for row in csv.DictReader(stream)}
        after_path=PROJECT/'evidence/world_builder/mod_data_link_after/link_unresolved_candidates.csv'
        after_path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(unresolved_path,after_path)
        delta={'before':len(old_names),'after':len(symbol_rows),'resolved':sorted(old_names-set(symbol_rows)),
            'added':sorted(set(symbol_rows)-old_names),'gamecore_linked':process.returncode==0,
            'remaining_mod_data_symbols':sorted(n for n in symbol_rows if any(k in n for k in ('@ModDataEntry@@','@ModType@@','@ModEnum@@','@CvWorldBuilderMapModData@@'))),
            'scope':'Actual SDK mod-data bodies with transactional allocation and checked wire boundary; full map and GameCore runtime pending',
            'evidence':[{'path':str(p),'sha256':digest(p)} for p in (baseline,after_path)]}
        (PROJECT/'evidence/world_builder/mod_data/link_delta.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key: result[key] for key in ("status", "diagnostic_locations", "diagnostic_location_codes",
                    "link_exit_code", "link_error_code_counts", "linker_unresolved_symbol_total", "parsed_unresolved_candidate_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
