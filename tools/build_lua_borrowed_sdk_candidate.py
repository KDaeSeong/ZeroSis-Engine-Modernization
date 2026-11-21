"""Compile all 161 SDK units with borrowed-reference patches in a separate candidate tree."""
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from native_build import environment_for, run
from probe_world_builder import artifact
from build_sdk_x64 import object_machine
from define_lua_borrowed_patches import BASE, patches


def main():
    evidence = PROJECT/'evidence/lua_borrowed/sdk_candidate'
    evidence.mkdir(parents=True, exist_ok=True)
    build = PROJECT/'Build/LuaBorrowed/SDKCandidate'
    root = build/'Source'
    obj = build/'obj'
    obj.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    proposed = patches()
    plan = dict(baseline)
    plan['patches'] = baseline['patches']+proposed
    plan_path = evidence/'sdk_x64_patches.json'
    plan_path.write_text(json.dumps(plan, indent=2)+'\n', encoding='utf-8')
    by_file = defaultdict(list)
    for patch in plan['patches']: by_file[patch['file']].append(patch)
    snapshot = json.loads((PROJECT/'evidence/sdk_reference/snapshot_manifest.json').read_text(encoding='utf-8'))
    manifest_path = evidence/'source_manifest.json'
    previous = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []
    previous_hashes = {row['relative_path']:row['sha256'] for row in previous}
    pending = []
    for row in snapshot:
        source = Path(row['snapshot'])
        relative = source.relative_to(PROJECT/'Source/SDK_BNW_Original').as_posix()
        if digest(source) != row['sha256'] or digest(Path(row['source'])) != row['sha256']:
            raise RuntimeError('Original SDK or frozen snapshot changed: '+relative)
        content = source.read_bytes()
        for patch in by_file[relative]:
            old, new = patch['old'].encode('latin1'), patch['new'].encode('latin1')
            if patch['source_sha256'] != row['sha256'] or content.count(old) != patch['count']:
                raise RuntimeError('Candidate patch context mismatch: '+patch['id'])
            content = content.replace(old, new)
        target = root/relative
        if target.exists() and target.read_bytes() != content and digest(target) != previous_hashes.get(relative):
            raise RuntimeError('Untracked candidate edit: '+str(target))
        pending.append((relative, target, content, source, row['sha256']))
    manifest = []
    for relative, target, content, source, original_hash in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != content: target.write_bytes(content)
        manifest.append(dict(relative_path=relative, **artifact(target), source=str(source), original_sha256=original_hash,
            patch_ids=[p['id'] for p in by_file[relative]]))
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    # The accepted CvGameCoreDLL.cpp includes ../../Providers/Debug relative to the SDK.
    # Mirror reviewed provider headers in that same sibling relationship, without links.
    provider_headers = []
    for source in sorted((PROJECT/'Source/Providers').rglob('*.h')):
        target = build/'Providers'/source.relative_to(PROJECT/'Source/Providers')
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_bytes()
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError('Candidate provider header differs: '+str(target))
        if not target.exists(): target.write_bytes(content)
        provider_headers.append(dict(source=artifact(source), candidate=artifact(target)))
    gamecore = root/'CvGameCoreDLL_Expansion2'
    ns = {'m':'http://schemas.microsoft.com/developer/msbuild/2003'}
    project = gamecore/'CvGameCoreDLL_Expansion2.vs2013.vcxproj'
    units = [node.attrib['Include'] for node in ET.parse(project).findall('.//m:ClCompile[@Include]', ns)]
    assert len(units) == 161 and len({Path(name).stem for name in units}) == 161
    support = [*sorted((PROJECT/'Source/Porting').glob('*.h')), *sorted((PROJECT/'Source/LuaBorrowed').glob('*.h'))]
    env, compiler = environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', build)
    compiler = Path(compiler)
    env['VSLANG'] = '1033'
    includes = [gamecore, PROJECT/'Source/Porting', PROJECT/'Source/LuaBorrowed']+[root/p for p in (
        'CvWorldBuilderMap/include', 'CvGameCoreDLLUtil/include', 'CvLocalization/include', 'CvGameDatabase/include',
        'FirePlace/include', 'FirePlace/include/FireWorks', 'ThirdPartyLibs/Lua51/include')]
    flags = ['/nologo', '/c', '/std:c++14', '/EHsc', '/MD', '/Od', '/fp:strict', '/W3', '/bigobj', '/FC',
        '/we4302', '/we4311', '/we4312', '/DFXS_IS_DLL', '/DWIN32', '/DNDEBUG', '/D_WINDOWS', '/D_USRDLL',
        '/DCVGAMECOREDLL_EXPORTS', '/DFINAL_RELEASE', '/D_CRT_SECURE_NO_WARNINGS', '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS']
    flags += [f'/I"{p}"' for p in includes]+[f'/Fp"{build/"GameCore_x64.pch"}"', f'/Fo"{obj.as_posix()}/"']
    phases = []
    for phase, names, extra in (
        ('pch', ['_precompile.cpp'], ['/YcCvGameCoreDLLPCH.h', '/d1reportSingleClassLayoutCvPlayerAI']),
        ('gamecore', [n for n in units if n != '_precompile.cpp'], ['/YuCvGameCoreDLLPCH.h', '/MP4'])):
        response = evidence/(phase+'.rsp')
        response.write_text('\n'.join(flags+extra+[f'"{gamecore/n}"' for n in names])+'\n', encoding='utf-8')
        print(json.dumps(dict(phase=phase, units=len(names), active_sdk_unchanged=True)), flush=True)
        result = run([compiler, '@'+str(response)], cwd=gamecore, env=env, timeout=900)
        log = evidence/(phase+'.log')
        log.write_bytes(result.stdout+result.stderr)
        output = read_text(log)
        errors = sorted(set(re.findall(r'(?m)^.*\b(?:fatal )?error\s+[A-Z]+\d+[^\r\n]*', output)))
        warnings = sorted(set(re.findall(r'(?m)^.*\bwarning\s+[A-Z]+\d+[^\r\n]*', output)))
        phases.append(dict(phase=phase, exit_code=result.returncode, response=artifact(response), log=artifact(log),
            translation_units=names, errors=errors, warnings=warnings))
        if result.returncode: break
    objects = [object_machine(p) for p in sorted(obj.glob('*.obj'))]
    complete = len(phases) == 2 and all(p['exit_code'] == 0 for p in phases) and len(objects) == 161
    report = dict(status='LUA_BORROWED_FULL_SDK_CANDIDATE_COMPILED' if complete else 'LUA_BORROWED_SDK_CANDIDATE_COMPILE_FAILED',
        builder=artifact(Path(__file__).resolve()), compiler=artifact(compiler), baseline=artifact(BASE),
        recipe=artifact(PROJECT/'tools/define_lua_borrowed_patches.py'), patch_plan=artifact(plan_path),
        source_manifest=artifact(manifest_path), support_headers=[artifact(p) for p in support],
        provider_headers=provider_headers,
        phases=phases, objects=objects, patch_count=len(plan['patches']), added_patches=len(proposed),
        native_lifetime_hooks_compiled=complete, dll_linked=False, active_sdk_updated=False,
        gameplay_owner_runtime_executed=False, gamecore_loaded=False, game_launched=False)
    (evidence/'build_result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if not complete:
        raise RuntimeError('\n'.join(error for phase in phases for error in phase['errors'])[-6500:])
    if any(row['architecture'] != 'x64' for row in objects): raise RuntimeError('Unexpected candidate object architecture')
    print(json.dumps(dict(status=report['status'], objects=len(objects), patches=len(plan['patches']))))


if __name__ == '__main__':
    main()
