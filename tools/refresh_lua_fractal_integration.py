"""Refresh compiled Fractal ownership dependencies and review bundles without loading GameCore."""
import argparse
import json
import sys
from pathlib import Path
from collect_baseline import PROJECT,digest
from native_build import run
from refresh_lua_registration_integration import BUILD_STEPS as ENUM_BUILD, STAGE_STEPS as ENUM_STAGE

BUILD_STEPS=tuple(step for name in ENUM_BUILD for step in (
    (name,'define_lua_fractal_patches') if name=='define_lua_registration_patches' else
    (name,'build_lua_fractal','verify_lua_fractal','lua_fractal_evidence') if name=='lua_registration_evidence' else (name,)))
STAGE_STEPS=tuple(step for name in ENUM_STAGE for step in ((name,'stage_lua_fractal') if name=='stage_lua_registration' else (name,)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('build','stage'),required=True)
    parser.add_argument('--from-step',help='Resume only after the prior invocation is terminal.')
    args=parser.parse_args();names=BUILD_STEPS if args.phase=='build' else STAGE_STEPS
    if args.from_step and args.from_step not in names:parser.error('Unknown step')
    root=PROJECT/'evidence/lua_fractal/integration_refresh';root.mkdir(parents=True,exist_ok=True)
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
        extra=['--apply'] if name in ('define_lua_enum_patches','define_lua_registration_patches','define_lua_fractal_patches') else ['--production'] if name in ('build_lua_enums','build_lua_registration','build_lua_fractal') else []
        print('RUN '+name,flush=True)
        result=run([sys.executable,script,*extra],cwd=PROJECT,timeout=3600)
        log.write_bytes(result.stdout+result.stderr)
        rows.append({'step':name,'exit_code':result.returncode,'script':{'path':str(script),'sha256':digest(script)},
            'log':{'path':str(log),'sha256':digest(log)}})
        results.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
        if result.returncode:
            print((result.stdout+result.stderr).decode('utf-8',errors='replace')[-6500:],flush=True);raise SystemExit(result.returncode)
        if digest(patch)!=compiled['patch_specification']['sha256']:
            raise RuntimeError('A refreshed recipe changed compiled patch bytes: '+name)
        print('PASS '+name,flush=True)
    print('LUA_FRACTAL_'+args.phase.upper()+'_INTEGRATION_REFRESH_PASS',flush=True)


if __name__=='__main__':main()
