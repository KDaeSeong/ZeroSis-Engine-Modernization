"""Stage the compiled x64 SDK, linked DLL and evidence for review, never into the game."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from build_sdk_x64 import object_machine
from collect_baseline import PROJECT, digest, pe_header


def read(relative):
    return json.loads((PROJECT / relative).read_text(encoding="utf-8"))


def verify(entries):
    for row in entries:
        path = Path(row["path"])
        if not path.is_file() or digest(path) != row["sha256"]:
            raise RuntimeError(f"Evidence/input mismatch: {path}")


def main():
    build = read("evidence/sdk_x64/build_result.json")
    link = read("evidence/sdk_x64/link_analysis.json")
    allocator = read("evidence/sdk_x64_allocator/conformance.json")
    numeric = read("evidence/numeric_boundaries/conformance.json")
    lua = read("evidence/lua_component/build_result.json")
    manifest = read("evidence/sdk_x64/port_manifest.json")
    if (build["status"] != "SDK_X64_ALL_OBJECTS_COMPILED" or len(build["objects"]) != build["translation_units_expected"]
            or build["unique_error_lines"] or not build["original_files_unchanged"] or not build["generated_port_inputs_unchanged"]
            or allocator["status"] != "SDK_X64_ALLOCATOR_COMPONENT_PASS"
            or numeric["status"] != "SDK_X64_NUMERIC_BOUNDARIES_PASS" or not build["numeric_warning_gate"]["passed"]
            or not link["parsed_count_matches_linker"] or link["unparsed_unresolved_diagnostics"]
            or link["status"] != "X64_LINK_PROBE_SUCCEEDED_UNTESTED" or link["generated_dll"] is None
            or link['linker_unresolved_symbol_total']!=0 or link['link_exit_code']!=0
            or pe_header(Path(link['generated_dll']['path']))['architecture']!='x64'):
        raise RuntimeError("Port review bundle requires verified objects/providers and a successful AMD64 link")
    verify([build["patch_specification"], build["builder"], build["manifest"], link["analyzer"], allocator["build"],
            allocator["native_execution"], link["diagnostics"], link["unresolved_candidates"], link["link_log"], link["link_response"],
            {"path": str(PROJECT / "evidence/sdk_x64/build_result.json"), "sha256": link["build_result_sha256"]}])
    verify({"path": path, "sha256": value} for path, value in allocator["input_sha256"].items())
    verify(build["support_inputs"])
    verify({"path": path, "sha256": value} for path, value in numeric["input_sha256"].items())
    verify([numeric[key] for key in ("build", "native_execution", "fixtures", "trace", "notification_trace")])
    verify(lua["sources"] + [lua["archive"], lua["library"], lua["builder"], lua["log"]])
    provider_sources = []
    for entry in link.get("providers", []):
        verify([entry["library"], entry["build_report"], entry["conformance"]])
        provider = json.loads(Path(entry["build_report"]["path"]).read_text(encoding="utf-8"))
        if entry['name'] in ('Streams','Serialization','Foundation','TempHeap','AutoArchive','Database','FLua','Strings','Localization','WorldBuilderTypes','WorldBuilderModData','WorldBuilderMapBridge','FileSystem','Logging','Debug'):
            if entry['name']=='Streams':
                from stream_evidence import validate
            elif entry['name']=='Serialization':
                from serialization_evidence import validate
            elif entry['name']=='Foundation':
                from foundation_evidence import validate
            elif entry['name']=='TempHeap':
                from temp_heap_evidence import validate
            elif entry['name']=='AutoArchive':
                from auto_archive_evidence import validate
            elif entry['name']=='Database':
                from database_evidence import validate
            elif entry['name']=='FLua':
                from flua_evidence import validate
            elif entry['name']=='Strings':
                from string_evidence import validate
            elif entry['name']=='Localization':
                from localization_provider_evidence import validate
            elif entry['name']=='WorldBuilderTypes':
                from world_builder_types_evidence import validate
            elif entry['name']=='WorldBuilderModData':
                from world_builder_mod_data_evidence import validate
            elif entry['name']=='FileSystem':
                from filesystem_evidence import validate
            elif entry['name']=='Logging':
                from logging_evidence import validate
            elif entry['name']=='Debug':
                from debug_evidence import validate_component as validate
            else:
                from world_builder_map_bridge_evidence import provider as validate
            provider,conformance,checked=validate(entry['build_report']['path'])
            if checked!=entry: raise RuntimeError('Linked provider differs from conformance')
            for row in provider['sources']:
                source=Path(row['path'])
                relative=source.relative_to(PROJECT)
                provider_sources.append((source,Path('Providers')/entry['name']/relative))
            if entry['name']=='AutoArchive':
                existing={row['path'] for row in provider['sources']}
                for row in conformance['support_inputs']:
                    if row['path'] not in existing:
                        source=Path(row['path']);provider_sources.append((source,Path('Providers')/entry['name']/source.relative_to(PROJECT)))
                provider_sources.append((PROJECT/'evidence/auto_archive/link_delta.json',Path('Providers/AutoArchive/link_delta.json')))
                provider_sources.append((PROJECT/'evidence/auto_archive_callers/link_delta.json',Path('Providers/AutoArchive/caller_link_delta.json')))
            if entry['name']=='Database':
                provider_sources.append((Path(provider['dll']['path']),Path('Providers/Database')/Path(provider['dll']['path']).name))
                provider_sources.append((PROJECT/'evidence/database/link_delta.json',Path('Providers/Database/link_delta.json')))
                for row in conformance['support_inputs']:
                    source=Path(row['path']);provider_sources.append((source,Path('Providers/Database')/source.relative_to(PROJECT)))
                assignments=json.loads(Path(conformance['assignment_conformance']['path']).read_text(encoding='utf-8'))
                for row in assignments['sources']+[conformance['assignment_conformance']]:
                    source=Path(row['path']);provider_sources.append((source,Path('Providers/Database')/source.relative_to(PROJECT)))
                from database_corpus_evidence import validate as validate_corpus
                corpus,corpus_entry=validate_corpus()
                corpus_files=corpus['sources']+[corpus['builder'],corpus_entry]
                corpus_files += [row['log'] for row in corpus['runs']]+[row['diff'] for row in corpus['comparisons']]
                corpus_files.append({'path':str(PROJECT/'tools/database_corpus_evidence.py')})
                for row in corpus_files:
                    source=Path(row['path']);provider_sources.append((source,Path('Providers/Database')/source.relative_to(PROJECT)))
            if entry['name']=='FLua':
                for relative in ('tools/build_flua_provider.py','tools/verify_flua_provider.py','tools/flua_evidence.py',
                        'evidence/flua/link_delta.json'):
                    source=PROJECT/relative;provider_sources.append((source,Path('Providers/FLua')/relative))
                for row in conformance['runs']:
                    source=Path(row['log']['path']);provider_sources.append((source,Path('Providers/FLua')/source.relative_to(PROJECT)))
            if entry['name']=='Strings':
                string_files=provider['x64']['hardening']['sources']+[{'path':str(PROJECT/relative)} for relative in (
                    'tools/build_string_provider.py','tools/verify_string_provider.py','tools/string_evidence.py',
                    'docs/M2_STRINGS_PROVIDER.md','evidence/strings/link_delta.json')]
                string_files += [row['log'] for row in conformance['runs']]+[row['diff'] for row in conformance['comparisons']]
                string_files += [row['wire'] for row in conformance['cross_reads']]
                for row in string_files:
                    source=Path(row['path']);provider_sources.append((source,Path('Providers/Strings')/source.relative_to(PROJECT)))
            if entry['name']=='Localization':
                localization_files=[provider['dll'],provider['map']]+provider['objects']+[t['source'] for t in provider['tests']]
                localization_files += [{'path':str(PROJECT/relative)} for relative in (
                    'tools/build_localization_provider.py','tools/verify_localization_provider.py','tools/localization_provider_evidence.py',
                    'tools/probe_localization_runtime.py','tools/define_localization_patches.py',
                    'docs/M2_LOCALIZATION_INTEGRATION.md','Source/ThirdParty/ICU44/original/license.html',
                    'evidence/localization/link_delta.json')]
                localization_files += [r['log'] for r in conformance['executions']+conformance['hardening']]
                localization_files += [r['difference'] for r in conformance['executions']]
                for row in localization_files:
                    source=Path(row['path']);provider_sources.append((source,Path('Providers/Localization')/source.relative_to(PROJECT)))
            if entry['name']=='WorldBuilderTypes':
                from stage_world_builder_types import files_for_review
                for source in files_for_review(provider):
                    provider_sources.append((source,Path('Providers/WorldBuilderTypes')/source.relative_to(PROJECT)))
            if entry['name']=='WorldBuilderModData':
                from stage_world_builder_mod_data import files_for_review
                for source in files_for_review(provider):
                    provider_sources.append((source,Path('Providers/WorldBuilderModData')/source.relative_to(PROJECT)))
            if entry['name']=='WorldBuilderMapBridge':
                from world_builder_map_bridge_evidence import validate as validate_map_link
                validate_map_link()
                paths=[Path(r['path']) for r in provider['objects']+provider['logs']+provider['responses']]
                for consumer in provider['consumers'].values():paths.extend(Path(consumer[k]['path']) for k in ('source','executable','map'))
                paths += [PROJECT/relative for relative in ('tools/define_world_builder_map_patches.py','tools/world_builder_map_bridge_evidence.py',
                    'docs/M2_WORLD_BUILDER_MAP_BRIDGE.md','Stage/WorldBuilderMapBridge/review_bundle.json','evidence/world_builder/map_bridge/link_trial.json',
                    'docs/M2_WORLD_BUILDER_MAP_INTEGRATION.md','tools/verify_world_builder_map_integration.py','evidence/world_builder/map_bridge/sdk_integration.json')]
                for source in paths:provider_sources.append((source,Path('Providers/WorldBuilderMapBridge')/source.relative_to(PROJECT)))
            if entry['name']=='FileSystem':
                from stage_filesystem_provider import files_for_review
                for source in files_for_review(provider):
                    provider_sources.append((source,Path('Providers/FileSystem')/source.relative_to(PROJECT)))
                provider_sources.append((PROJECT/'Stage/FileSystem/review_bundle.json',Path('Providers/FileSystem/review_bundle.json')))
            if entry['name']=='Logging':
                from stage_logging_provider import files_for_review
                for source in files_for_review(provider):
                    provider_sources.append((source,Path('Providers/Logging')/source.relative_to(PROJECT)))
                provider_sources.append((PROJECT/'Stage/Logging/review_bundle.json',Path('Providers/Logging/review_bundle.json')))
            if entry['name']=='Debug':
                from stage_debug_provider import files_for_review
                for source in files_for_review():
                    provider_sources.append((source,Path('Providers/Debug')/source.relative_to(PROJECT)))
                provider_sources.append((PROJECT/'Stage/Debug/review_bundle.json',Path('Providers/Debug/review_bundle.json')))
            provider_sources += [(Path(row['path']),Path('Providers')/entry['name']/name) for row,name in (
                (entry['library'],'ZeroSis_'+entry['name']+'_x64.lib'),(entry['build_report'],'build_result.json'),
                (entry['conformance'],'conformance.json'))]
            continue
        if entry['name']!='Lua51': raise RuntimeError('Unknown provider staging contract')
        provider_manifest = json.loads(Path(provider["source_manifest"]["path"]).read_text(encoding="utf-8"))
        verify(provider_manifest + provider["objects"] + [provider[key] for key in
            ("source_manifest", "patches", "builder", "compiler", "response", "log", "sdk_configuration")])
        if numeric["lua_library"] != entry["library"] or numeric["runtime"] != entry["runtime"]:
            raise RuntimeError("Numeric boundary tests did not use the linked provider")
        provider_root = PROJECT / "Source/Lua51_x64"
        provider_sources += [(Path(row["path"]), Path("Providers/Lua51") / Path(row["path"]).relative_to(provider_root))
                             for row in provider_manifest]
        provider_sources += [(Path(row["path"]), Path("Providers/Lua51") / name) for row, name in (
            (entry["library"], "ZeroSis_Lua51_x64.lib"), (entry["build_report"], "build_result.json"),
            (entry["conformance"], "conformance.json"), (provider["patches"], "patches.json"),
            (provider["source_manifest"], "port_manifest.json"))]
    verify({"path": row["log"], "sha256": row["log_sha256"]} for row in build["executions"])
    for row in manifest:
        verify([{"path": row["source"], "sha256": row["original_sha256"]},
                {"path": row["snapshot"], "sha256": row["original_sha256"]},
                {"path": row["port"], "sha256": row["port_sha256"]}])
    for row in build["objects"]:
        actual = object_machine(Path(row["path"]))
        if actual != row or actual["architecture"] != "x64":
            raise RuntimeError(f"Unexpected compiled object: {row['path']}")
    if any(code in build["warning_code_counts"] for code in ("C4302", "C4311", "C4312")):
        raise RuntimeError("Pointer truncation/extension warnings remain in the compiled configuration")
    stage = PROJECT / "Stage/GameCore_x64"
    stage.mkdir(parents=True, exist_ok=True)
    bundle = stage / "review_bundle.json"
    previous = json.loads(bundle.read_text(encoding="utf-8")) if bundle.is_file() else {"files": []}
    previous_hashes = {row["path"]: row["sha256"] for row in previous["files"]}
    sources = [(Path(row["port"]), stage / "Source" / row["relative_path"]) for row in manifest if row["patch_ids"]]
    sources += [(Path(row["path"]), stage / "Porting" / Path(row["path"]).name) for row in build["support_inputs"]]
    sources += [(source, stage / relative) for source, relative in provider_sources]
    from bootstrap_evidence import validate as validate_bootstrap
    _,_,bootstrap=validate_bootstrap()
    if bootstrap!=link['bootstrap_caller_conformance']:raise RuntimeError('Linked bootstrap differs from tested SDK callers')
    from globals_cleanup_evidence import validate as validate_globals_cleanup
    from stage_globals_cleanup import files_for_review as globals_cleanup_files
    _,_,globals_cleanup=validate_globals_cleanup()
    if globals_cleanup!=link['globals_cleanup_conformance']:raise RuntimeError('Linked cleanup differs from tested SDK bodies')
    sources += [(source,stage/'Callers/GlobalsCleanup'/source.relative_to(PROJECT)) for source in globals_cleanup_files()]
    sources.append((PROJECT/'Stage/GlobalsCleanup/review_bundle.json',stage/'Callers/GlobalsCleanup/review_bundle.json'))
    from construction_evidence import validate as validate_construction
    from stage_construction import files_for_review as construction_files
    _,_,construction=validate_construction()
    if construction!=link['construction_conformance']:raise RuntimeError('Linked constructors differ from tested SDK bodies')
    sources += [(source,stage/'Callers/Construction'/source.relative_to(PROJECT)) for source in construction_files()]
    sources.append((PROJECT/'Stage/Construction/review_bundle.json',stage/'Callers/Construction/review_bundle.json'))
    from host_binding_evidence import validate as validate_host_binding
    from stage_host_binding import files_for_review as host_binding_files
    _,_,host_binding=validate_host_binding()
    if host_binding!=link['host_binding_conformance']:raise RuntimeError('Linked host binding differs from tested SDK bodies')
    sources += [(source,stage/'Callers/HostBinding'/source.relative_to(PROJECT)) for source in host_binding_files()]
    sources.append((PROJECT/'Stage/HostBinding/review_bundle.json',stage/'Callers/HostBinding/review_bundle.json'))
    from database_postprocess_evidence import validate as validate_database_postprocess
    from stage_database_postprocess import files_for_review as database_postprocess_files
    _,_,database_postprocess=validate_database_postprocess()
    if database_postprocess!=link['database_postprocess_conformance']:raise RuntimeError('Linked SQL postprocessing differs from tested SDK bodies')
    sources += [(source,stage/'Callers/DatabasePostprocess'/source.relative_to(PROJECT)) for source in database_postprocess_files()]

    from database_loader_evidence import validate as validate_database_loader
    from stage_database_loader import files_for_review as database_loader_files
    _,_,database_loader=validate_database_loader()
    if database_loader!=link['database_loader_conformance']:raise RuntimeError('Linked database loader differs from tested SDK bodies')
    sources += [(source,stage/'Callers/DatabaseLoader'/source.relative_to(PROJECT)) for source in database_loader_files()]
    sources += [(PROJECT/'Stage/DatabaseLoader/review_bundle.json',stage/'Callers/DatabaseLoader/review_bundle.json')]
    from info_cleanup_evidence import validate as validate_info_cleanup
    from stage_info_cleanup import files_for_review as info_cleanup_files
    _,_,info_cleanup=validate_info_cleanup()
    if info_cleanup!=link['info_cleanup_conformance']:raise RuntimeError('Linked rule cleanup differs from executed SDK bodies')
    sources += [(source,stage/'Callers/InfoCleanup'/source.relative_to(PROJECT)) for source in info_cleanup_files()]
    sources += [(PROJECT/'Stage/InfoCleanup/review_bundle.json',stage/'Callers/InfoCleanup/review_bundle.json')]
    from database_cache_evidence import validate as validate_database_cache
    from stage_database_cache import files_for_review as database_cache_files
    _,_,database_cache=validate_database_cache()
    if database_cache!=link['database_cache_conformance']:raise RuntimeError('Linked database cache differs from tested SDK bodies')
    sources += [(source,stage/'Callers/DatabaseCache'/source.relative_to(PROJECT)) for source in database_cache_files()]
    sources += [(PROJECT/'Stage/DatabaseCache/review_bundle.json',stage/'Callers/DatabaseCache/review_bundle.json')]
    from startup_owners_evidence import validate as validate_startup_owners
    from stage_startup_owners import files_for_review as startup_owners_files
    _,_,startup_owners=validate_startup_owners()
    if startup_owners!=link['startup_owners_conformance']:raise RuntimeError('Linked startup ownership differs from tested SDK bodies')
    sources += [(source,stage/'Callers/StartupOwners'/source.relative_to(PROJECT)) for source in startup_owners_files()]
    sources += [(PROJECT/'Stage/StartupOwners/review_bundle.json',stage/'Callers/StartupOwners/review_bundle.json')]
    from gc_lifecycle_evidence import validate as validate_gc_lifecycle
    from stage_gc_lifecycle import files_for_review as gc_lifecycle_files
    _,_,gc_lifecycle=validate_gc_lifecycle()
    if gc_lifecycle!=link['gc_lifecycle_conformance']:raise RuntimeError('Linked startup ownership differs from tested SDK bodies')
    sources += [(source,stage/'Callers/GCLifecycle'/source.relative_to(PROJECT)) for source in gc_lifecycle_files()]
    sources += [(PROJECT/'Stage/GCLifecycle/review_bundle.json',stage/'Callers/GCLifecycle/review_bundle.json')]
    from lua_enums_evidence import validate as validate_lua_enums
    from stage_lua_enums import files_for_review as lua_enum_files
    _,_,lua_enums=validate_lua_enums()
    if lua_enums!=link['lua_enum_conformance']:raise RuntimeError('Linked enum callers differ from tested SDK bodies')
    sources += [(source,stage/'Callers/LuaEnums'/source.relative_to(PROJECT)) for source in lua_enum_files()]
    sources += [(PROJECT/'Stage/LuaEnums/review_bundle.json',stage/'Callers/LuaEnums/review_bundle.json')]
    from lua_registration_evidence import validate as validate_lua_registration
    from stage_lua_registration import files_for_review as lua_registration_files
    _,_,lua_registration=validate_lua_registration()
    if lua_registration!=link['lua_registration_conformance']:raise RuntimeError('Linked registrar callers differ from tested SDK bodies')
    sources += [(source,stage/'Callers/LuaRegistration'/source.relative_to(PROJECT)) for source in lua_registration_files()]
    sources += [(PROJECT/'Stage/LuaRegistration/review_bundle.json',stage/'Callers/LuaRegistration/review_bundle.json')]
    from lua_fractal_evidence import validate as validate_lua_fractal
    from stage_lua_fractal import files_for_review as lua_fractal_files
    _,_,lua_fractal=validate_lua_fractal()
    if lua_fractal!=link['lua_fractal_conformance']:raise RuntimeError('Linked Fractal callers differ from tested SDK bodies')
    sources += [(source,stage/'Callers/LuaFractal'/source.relative_to(PROJECT)) for source in lua_fractal_files()]
    sources += [(PROJECT/'Stage/LuaFractal/review_bundle.json',stage/'Callers/LuaFractal/review_bundle.json')]
    from fractal_numeric_evidence import validate as validate_fractal_numeric
    from stage_fractal_numeric import files_for_review as fractal_numeric_files
    _,_,fractal_numeric=validate_fractal_numeric()
    if fractal_numeric!=link['fractal_numeric_conformance']:raise RuntimeError('Linked numeric Fractal callers differ from tested SDK bodies')
    sources += [(source,stage/'Callers/FractalNumeric'/source.relative_to(PROJECT)) for source in fractal_numeric_files()]
    sources += [(PROJECT/'Stage/FractalNumeric/review_bundle.json',stage/'Callers/FractalNumeric/review_bundle.json')]
    from lua_borrowed_evidence import validate as validate_lua_borrowed
    from stage_lua_borrowed import files_for_review as lua_borrowed_files
    _,_,lua_borrowed=validate_lua_borrowed()
    if lua_borrowed!=link['lua_borrowed_conformance']:raise RuntimeError('Linked borrowed references differ from tested SDK bodies')
    sources += [(source,stage/'Callers/LuaBorrowed'/source.relative_to(PROJECT)) for source in lua_borrowed_files()]
    sources += [(PROJECT/'Stage/LuaBorrowed/review_bundle.json',stage/'Callers/LuaBorrowed/review_bundle.json')]


    sources.append((PROJECT/'Stage/DatabasePostprocess/review_bundle.json',stage/'Callers/DatabasePostprocess/review_bundle.json'))
    from stage_bootstrap_component import files_for_review as bootstrap_files
    sources += [(source,stage/'Callers/Bootstrap'/source.relative_to(PROJECT)) for source in bootstrap_files()]
    sources += [(PROJECT/'Stage/Bootstrap/review_bundle.json',stage/'Callers/Bootstrap/review_bundle.json'),
                (Path(link['generated_dll']['path']),stage/'Binary/CvGameCoreDLL_Expansion2_x64.dll'),
                (Path(link['link_map']['path']),stage/'Binary/CvGameCoreDLL_Expansion2_x64.map')]
    if link.get('caller_patch_conformance'):
        from temp_heap_caller_evidence import validate as validate_callers
        callers,caller_entry=validate_callers()
        if caller_entry!=link['caller_patch_conformance']:raise RuntimeError('Caller link evidence differs from current tests')
        for row in callers['input_artifacts']:
            source=Path(row['path']);sources.append((source,stage/'Callers/TempHeap'/source.relative_to(PROJECT)))
        sources += [(PROJECT/relative,stage/'Callers/TempHeap'/name) for relative,name in (
            ('tools/temp_heap_caller_evidence.py','temp_heap_caller_evidence.py'),
            ('evidence/temp_heap_callers/conformance.json','conformance.json'),
            ('evidence/temp_heap_callers/link_delta.json','link_delta.json'))]
    sources += [(PROJECT / relative, stage / name) for relative, name in (
        ("Source/Porting/sdk_x64_patches.json", "sdk_x64_patches.json"),
        ("evidence/sdk_x64/port_manifest.json", "port_manifest.json"),
        ("evidence/sdk_x64/build_result.json", "compile_result.json"),
        ("evidence/sdk_x64/link_analysis.json", "link_analysis.json"),
        ("evidence/sdk_x64_allocator/conformance.json", "allocator_verification.json"),
        ("evidence/numeric_boundaries/conformance.json", "numeric_verification.json"),
        ("evidence/numeric_boundaries/edit_ledger.json", "numeric_edit_ledger.json"),
        ("evidence/lua_component/build_result.json", "lua_component_build.json"))]
    for source, target in sources:
        if target.is_file() and digest(target) not in (digest(source), previous_hashes.get(str(target))):
            raise RuntimeError(f"Untracked staging edit; refusing overwrite: {target}")
    files = []
    for source, target in sources:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(source) != digest(target):
            raise RuntimeError(f"Staging copy differs: {target}")
        files.append({"path": str(target), "sha256": digest(target), "source": str(source)})
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "status": "X64_COMPILE_AND_LINK_REVIEW_BUNDLE_READY",
              "scope": "SOURCE_AND_LINKED_X64_DLL_REVIEW; GAMECORE_RUNTIME_NOT_VERIFIED", "files": files,
              "linked_provider_candidates": [entry["name"] for entry in link.get("providers", [])],
              "object_files": len(build["objects"]), "modified_sdk_files": sum(bool(row["patch_ids"]) for row in manifest),
              "unresolved_link_symbols": link["linker_unresolved_symbol_total"],
              "remaining_compiler_diagnostic_locations": link["diagnostic_locations"],
              "explicit_bootstrap_integrated": True,
              "globals_cleanup_integrated": True,
              "construction_cleanup_integrated": True,
              "host_binding_integrated": True,
              "database_postprocess_integrated": True,
              "database_loader_integrated": True,
              "info_cleanup_integrated": True,
              "database_cache_integrated": True,
              "startup_owners_integrated": True,
              "gc_lifecycle_integrated": True,
              "lua_enum_integrated": True,
              "lua_registration_integrated": True,
              "lua_fractal_integrated": True,
              "fractal_numeric_integrated": True,
              "lua_borrowed_integrated": True,
              "gamecore_linked": True, "gamecore_runtime_verified": False, "game_launched": False}
    bundle.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "object_files", "modified_sdk_files", "unresolved_link_symbols", "scope")}))


if __name__ == "__main__":
    main()
