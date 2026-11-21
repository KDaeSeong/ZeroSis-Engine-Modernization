"""Refresh changed SDK provenance, link and review bundles; never load GameCore.

Run build_sdk_x64 first. Historical validators refer to the current patch plan
and SDK manifest, so regenerate their dependent evidence after adding enum patches.
"""
import argparse
import json
import sys
from pathlib import Path
from collect_baseline import PROJECT,digest
from native_build import run

BUILD_STEPS=(
    'define_logging_caller_patches','define_bootstrap_patches','define_debug_caller_patches',
    'define_globals_cleanup_patches','define_construction_patches','define_host_binding_patches',
    'define_database_postprocess_patches','define_database_loader_patches','define_info_cleanup_patches',
    'define_database_cache_patches','define_startup_owners_patches','define_gc_lifecycle_patches',
    'define_lua_enum_patches','refresh_world_builder_dependencies','build_gc_lifecycle','verify_gc_lifecycle',
    'build_lua_enums','verify_lua_enums','lua_enums_evidence','refresh_gc_lifecycle_integration')
STAGE_STEPS=(
    'audit_gc_initialization','stage_localization_values','stage_localization_provider',
    'stage_world_builder_types','stage_world_builder_mod_data','stage_world_builder_map_wire',
    'stage_world_builder_map_object','stage_world_builder_map_bridge','stage_filesystem_provider',
    'stage_logging_provider','stage_bootstrap_component','stage_debug_provider','stage_globals_cleanup',
    'stage_construction','stage_host_binding','stage_database_postprocess','stage_database_loader',
    'stage_info_cleanup','stage_database_cache','stage_startup_owners','stage_gc_lifecycle','stage_lua_enums',
    'stage_sdk_x64_port','audit_static_initialization','verify_static_initialization','stage_static_initialization',
    'build_native_host','prepare_native_host_bundle','verify_native_host','audit_host_script_bindings',
    'native_host_evidence','audit_native_host_services','stage_native_host','verify_project')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('build','stage'),required=True)
    parser.add_argument('--from-step',help='Resume only after the prior invocation is terminal.')
    args=parser.parse_args();names=BUILD_STEPS if args.phase=='build' else STAGE_STEPS
    if args.from_step and args.from_step not in names:parser.error('Unknown step')
    root=PROJECT/'evidence/lua_enums/integration_refresh';root.mkdir(parents=True,exist_ok=True)
    results=root/(args.phase+'_results.json')
    prior=json.loads(results.read_text(encoding='utf-8')) if args.from_step and results.exists() else []
    start=names.index(args.from_step) if args.from_step else 0
    rows=[r for r in prior if names.index(r['step'])<start]
    if args.from_step and [r['step'] for r in rows if r['exit_code']==0]!=list(names[:start]):
        raise RuntimeError('Resume requires preceding successful recorded steps')
    for row in rows:
        if digest(Path(row['script']['path']))!=row['script']['sha256']:
            raise RuntimeError('A preceding step changed; resume from '+row['step'])
    patch=PROJECT/'Source/Porting/sdk_x64_patches.json';compiled=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if digest(patch)!=compiled['patch_specification']['sha256']:raise RuntimeError('Current patch plan has not been compiled')
    for name in names[start:]:
        script=PROJECT/'tools'/(name+'.py');log=root/(name+'.log')
        extra=['--apply'] if name=='define_lua_enum_patches' else ['--production'] if name=='build_lua_enums' else []
        print('RUN '+name,flush=True)
        result=run([sys.executable,script,*extra],cwd=PROJECT,timeout=3600)
        log.write_bytes(result.stdout+result.stderr)
        rows.append({'step':name,'exit_code':result.returncode,'script':{'path':str(script),'sha256':digest(script)},
                     'log':{'path':str(log),'sha256':digest(log)}})
        results.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
        if result.returncode:
            print((result.stdout+result.stderr).decode('utf-8',errors='replace')[-6500:],flush=True)
            raise SystemExit(result.returncode)
        if digest(patch)!=compiled['patch_specification']['sha256']:
            raise RuntimeError('A refreshed recipe changed compiled patch bytes: '+name)
        print('PASS '+name,flush=True)
    print('LUA_ENUM_'+args.phase.upper()+'_INTEGRATION_REFRESH_PASS',flush=True)


if __name__=='__main__':main()
