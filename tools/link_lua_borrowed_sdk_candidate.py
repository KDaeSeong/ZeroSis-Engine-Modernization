"""Link the isolated lifetime candidate against accepted providers, without loading it."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    root = PROJECT/'evidence/lua_borrowed'
    compilation_path = root/'sdk_candidate/build_result.json'
    component_path = root/'conformance.json'
    baseline_path = PROJECT/'evidence/sdk_x64/link_analysis.json'
    compiled, component, baseline = (json.loads(path.read_text(encoding='utf-8'))
        for path in (compilation_path, component_path, baseline_path))
    check_artifacts([compiled, component, baseline])
    if compiled['status'] != 'LUA_BORROWED_FULL_SDK_CANDIDATE_COMPILED' or len(compiled['objects']) != 161:
        raise RuntimeError('Complete isolated SDK compilation required')
    if component['status'] != 'LUA_BORROWED_CANDIDATE_COMPONENT_PASS_NOT_INTEGRATED':
        raise RuntimeError('Current isolated component execution required')
    if baseline['status'] != 'X64_LINK_PROBE_SUCCEEDED_UNTESTED' or baseline['build_attempt'] != 36:
        raise RuntimeError('Accepted attempt_036 provider baseline changed')
    manifest = json.loads(Path(compiled['source_manifest']['path']).read_text(encoding='utf-8'))
    check_artifacts(manifest)
    providers = baseline['providers']
    if len(providers) != 16 or any(row['architecture'] != 'x64' for row in compiled['objects']):
        raise RuntimeError('Unexpected native link inputs')
    provider_records = []
    for entry in providers:
        report = json.loads(Path(entry['build_report']['path']).read_text(encoding='utf-8'))
        check_artifacts(report)
        provider_records.append(entry['build_report'])
    directory = PROJECT/'Build/LuaBorrowed/SDKCandidate/link'
    directory.mkdir(parents=True, exist_ok=True)
    env, compiler = environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', directory)
    compiler = Path(compiler)
    env['VSLANG'] = '1033'
    definition = directory.parent/'Source/CvGameCoreDLL_Expansion2/CvGameCoreDLL.def'
    if definition.read_bytes() != (PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGameCoreDLL.def').read_bytes():
        raise RuntimeError('Public export contract changed')
    output = directory/'CvGameCoreDLL_Expansion2_x64_borrowed.dll'
    linker = compiler.with_name('link.exe')
    response, mapfile = directory/'link.rsp', directory/'borrowed.map'
    flags = ['/NOLOGO', '/DLL', '/MACHINE:X64', '/INCREMENTAL:NO', '/OPT:REF', '/OPT:ICF', '/Brepro',
        f'/DEF:"{definition}"', f'/OUT:"{output}"', f'/IMPLIB:"{directory/"borrowed.lib"}"', f'/MAP:"{mapfile}"']
    flags += [f'"{row["path"]}"' for row in compiled['objects']]
    flags += [f'"{row["library"]["path"]}"' for row in providers]+baseline['platform_libraries']
    response.write_text('\n'.join(flags)+'\n', encoding='utf-8')
    result = run([linker, '@'+str(response)], cwd=directory, env=env, timeout=180)
    log = root/'sdk_candidate/link.log'
    log.write_bytes(result.stdout+result.stderr)
    text = read_text(log)
    errors = re.findall(r'(?m)^.*\b(?:fatal )?error\s+LNK\d+[^\r\n]*', text)
    if result.returncode or errors:
        raise RuntimeError('Isolated SDK candidate link failed: '+text[-6500:])
    pe = pe_header(output)
    if pe['machine_hex'] != '0x8664' or pe['pe_format'] != 'PE32+' or not pe['is_dll']:
        raise RuntimeError('Link output is not an AMD64 DLL')
    inspection = {}
    for kind in ('exports', 'dependents'):
        value = checked_run([compiler.with_name('dumpbin.exe'), '/'+kind, output], cwd=directory, env=env)
        path = root/'sdk_candidate'/(kind+'.log')
        path.write_bytes(value.stdout+value.stderr)
        inspection[kind] = artifact(path)
    exports = set(re.findall(r'^\s*\d+\s+[A-F0-9]+\s+[A-F0-9]+\s+(\w+)', read_text(Path(inspection['exports']['path'])), re.M))
    required = {'DllGetGameContext', 'ZeroSisShutdownGameCore', 'ZeroSisGetBootstrapError'}
    if not required <= exports:
        raise RuntimeError('Candidate startup/shutdown exports missing')
    imports = re.findall(r'^\s+([\w.-]+\.dll)\s*$', read_text(Path(inspection['dependents']['path'])), re.M|re.I)
    symbols = [line.strip() for line in read_text(mapfile).splitlines()
        if '?state@?1??State@ZeroSisLuaBorrowed@@' in line]
    if len(symbols) != 1:
        raise RuntimeError('Shared lifetime registry symbol must appear exactly once in the linked DLL')
    report = dict(status='LUA_BORROWED_ISOLATED_SDK_DLL_LINKED_NOT_LOADED',
        builder=artifact(Path(__file__).resolve()), compiler=artifact(compiler), linker=artifact(linker),
        compilation=artifact(compilation_path), component=artifact(component_path), accepted_link=artifact(baseline_path),
        source_manifest=compiled['source_manifest'], provider_reports=provider_records, providers=providers,
        response=artifact(response), log=artifact(log), map=artifact(mapfile), definition=artifact(definition),
        generated_dll={**artifact(output), 'pe':pe}, inspection=inspection, exports=sorted(exports), imports=imports,
        shared_registry_symbol=symbols[0], link_exit_code=0, unresolved_symbols=0,
        reused_accepted_provider_libraries=True, sdk_objects=161, patch_count=compiled['patch_count'],
        active_sdk_updated=False, stage_updated=False, gamecore_loaded=False, game_launched=False,
        scope='ISOLATED_CANDIDATE_LINK_WITH_ACCEPTED_PROVIDER_LIBRARIES_NOT_FULL_INTEGRATION_OR_RUNTIME')
    (root/'sdk_candidate/link_result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], objects=161, providers=16, unresolved=0, dll=report['generated_dll'])))


if __name__ == '__main__':
    main()
