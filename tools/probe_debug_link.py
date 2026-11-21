"""Link the real x64 GameCore with the symbol provider; never load the resulting DLL."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    root = PROJECT / 'evidence/debug'
    build = json.loads((root / 'build_result.json').read_text(encoding='utf-8'))
    conformance = json.loads((root / 'conformance.json').read_text(encoding='utf-8'))
    official_path = PROJECT / 'evidence/sdk_x64/link_analysis.json'
    official = json.loads(official_path.read_text(encoding='utf-8'))
    check_artifacts([build, conformance, official])
    if conformance['status'] != 'DEBUG_NATIVE_SYMBOL_COMPONENT_PASS' or conformance['issues']:
        raise RuntimeError('Debug component has not passed')
    if official['linker_unresolved_symbol_total'] != 0 or len(official['providers']) != 16 or not official['generated_dll']:
        raise RuntimeError('Unexpected official GameCore baseline')
    from debug_evidence import validate_component
    _, _, entry = validate_component()
    from bootstrap_evidence import validate as validate_bootstrap
    _, _, bootstrap = validate_bootstrap()
    if entry not in official['providers'] or official['bootstrap_caller_conformance'] != bootstrap:
        raise RuntimeError('Official debugger/bootstrap contract differs')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if len(sdk['objects']) != 161 or build['sdk_patch_specification'] != sdk['patch_specification'] or build['sdk_port_manifest'] != sdk['manifest']:
        raise RuntimeError('Debug/SDK source provenance differs')
    response = Path(official['link_response']['path']).read_text(encoding='utf-8-sig')
    out = PROJECT / 'Build/Debug/link_trial'
    out.mkdir(parents=True, exist_ok=True)
    env, compiler = environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', out)
    linker, dumpbin = (Path(compiler).with_name(name) for name in ('link.exe', 'dumpbin.exe'))
    if digest(linker) != official['linker_sha256']:
        raise RuntimeError('Debug trial linker differs')
    dbghelp = next((Path(directory) / 'dbghelp.lib' for directory in env['LIB'].split(';')
                    if directory and (Path(directory) / 'dbghelp.lib').is_file()), None)
    if dbghelp is None:
        raise RuntimeError('Windows x64 DbgHelp import library missing')
    runs = []
    expected = {'?GetInstance@FDebugHelper@@SAAEAV1@XZ', '?LoadSymbols@FDebugHelper@@QEAA_NPEAUHINSTANCE__@@@Z', '?Shutdown@ZeroSisDebug@@YA_NXZ'}
    library_line = '"' + build['library']['path'] + '"'
    for name, include_debug in (('before', False), ('after', True)):
        destination = out / name
        destination.mkdir(parents=True, exist_ok=True)
        dll, linkmap = destination / 'GameCore_link_only.dll', destination / 'GameCore_link_only.map'
        lines = []
        for line in response.splitlines():
            if line.startswith('/MAP:'):
                continue
            if not include_debug and line.strip() == library_line:
                continue
            if line.startswith('/OUT:'):
                line = f'/OUT:"{dll}"'
            elif line.startswith('/IMPLIB:'):
                line = f'/IMPLIB:"{destination / "GameCore_link_only.lib"}"'
            lines.append(line)
        lines.append(f'/MAP:"{linkmap}"')
        lines.append(f'"{dbghelp}"')
        rsp = destination / 'link.rsp'
        rsp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        result = run([linker, '@' + str(rsp)], cwd=destination, env=env, timeout=180)
        log = root / ('link_' + name + '.log')
        log.write_bytes(result.stdout + result.stderr)
        text = read_text(log)
        if not include_debug:
            if not result.returncode or dll.exists() or not re.search(r'LNK1120:\s*3(?!\d)', text) or any(s not in text for s in expected):
                raise RuntimeError('Debug baseline did not reproduce its three missing symbols')
            runs.append({'name': name, 'exit_code': result.returncode, 'log': artifact(log), 'response': artifact(rsp), 'unresolved': sorted(expected), 'generated_dll': False})
            continue
        if result.returncode or not dll.is_file() or re.search(r'\b(?:warning|error)\s+LNK\d+', text, re.I):
            raise RuntimeError('Debug candidate failed to link: ' + text[-3500:])
        if pe_header(dll)['architecture'] != 'x64':
            raise RuntimeError('GameCore link candidate is not AMD64')
        symbols = read_text(linkmap)
        if any(s not in symbols for s in expected) or 'ZeroSis_Debug_x64:SdkDebugHelper.obj' not in symbols:
            raise RuntimeError('Real debug provider is absent from GameCore map')
        audit = checked_run([dumpbin, '/dependents', '/exports', dll], cwd=destination, env=env)
        audit_log = root / 'candidate_dll_inspection.log'
        audit_log.write_bytes(audit.stdout + audit.stderr)
        inspection = read_text(audit_log)
        if any(name not in inspection for name in ('DllGetGameContext','ZeroSisShutdownGameCore','ZeroSisGetBootstrapError')):
            raise RuntimeError('GameCore export missing')
        deps = re.findall(r'^\s+([\w.-]+\.dll)\s*$', inspection, re.M | re.I)
        runs.append({'name': name, 'exit_code': result.returncode, 'log': artifact(log), 'response': artifact(rsp),
                     'unresolved': [], 'generated_dll': True, 'dll': {**artifact(dll), 'pe': pe_header(dll)},
                     'map': artifact(linkmap), 'inspection': artifact(audit_log), 'dependencies': deps})
    check_artifacts(official)
    caller = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGameCoreDLL.cpp'
    from build_bootstrap_component import body
    dllmain = body(caller.read_bytes().decode('latin1'), 'BOOL APIENTRY DllMain(')
    if any(name in dllmain for name in ('LoadSymbols','timeBeginPeriod','InitializeSingleton','DestroySingleton','timeEndPeriod')):
        raise RuntimeError('Heavy initialization or cleanup returned to DllMain')
    report = {
        'status': 'DEBUG_GAMECORE_LINK_CANDIDATE_PASS_NOT_LOADABLE_RELEASE',
        'probe': artifact(Path(__file__).resolve()), 'official_link': artifact(official_path),
        'component_build': artifact(root / 'build_result.json'), 'component_conformance': artifact(root / 'conformance.json'),
        'gamecore_build': artifact(PROJECT / 'evidence/sdk_x64/build_result.json'), 'linker': artifact(linker),
        'additional_platform_library': artifact(dbghelp),
        'runs': runs, 'before': 3, 'after': 0, 'resolved': sorted(expected), 'gamecore_objects': 161, 'providers': 16,
        'official_report_replaced': False, 'official_unresolved_symbols': 0,
        'bootstrap_callers': bootstrap, 'explicit_bootstrap_integrated': True,
        'loader_lock_debug_caller': artifact(caller), 'loader_lock_bootstrap_fixed': False,
        'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False,
    }
    (root / 'link_trial.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'] + ' 3 -> 0; explicit bootstrap compiled, DLL never loaded')


if __name__ == '__main__':
    main()
