"""Build/run the isolated combat-presentation host boundary regression."""
import datetime
import hashlib
import json
import sys
import uuid
from pathlib import Path

from collect_baseline import PROJECT, read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

TEST = PROJECT / 'Tests/combat_presentation.cpp'
TOOL = Path(__file__).resolve()
OUT = PROJECT / 'evidence/host_combat_presentation'
FROZEN = [
    TEST, TOOL,
    PROJECT / 'Source/Host/CombatPresentation.h',
    PROJECT / 'Source/Host/HostServices.h',
    PROJECT / 'Source/Host/ActiveModCatalog.h',
    PROJECT / 'Source/Host/LocalGameCommands.h',
    PROJECT / 'Source/Host/GeneratedHostInterfaces.h',
    PROJECT / 'Source/Host/SdkHostIncludes.h',
]
def canon(path):
    return str(Path(path).resolve()).casefold()


def unchanged(before):
    changed = [p for p, digest in before.items() if artifact(Path(p))['sha256'] != digest]
    if changed:
        raise RuntimeError('Frozen component inputs changed during build/inspection: ' + ', '.join(changed))


def main():
    if len(sys.argv) != 1:
        raise SystemExit('This runner performs one frozen build and execution; no SDK runtime is loaded.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = stamp + '_' + uuid.uuid4().hex[:12]
    run_root = OUT / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    snapshot_root = run_root / 'frozen_inputs'
    snapshot_root.mkdir()
    build_name = 'sdk_host_combat_' + run_id
    lua_report = json.loads((PROJECT / 'evidence/lua_provider/build_result.json').read_text(encoding='utf-8'))
    check_artifacts(lua_report['library'])
    library_path = Path(lua_report['library']['path'])
    library_before = artifact(library_path)['sha256']
    from build_native_host import compile_program
    # Dependency discovery is preparatory only. Its compiler dependency report
    # determines the exact headers; only the following frozen build is evidence.
    discovery = compile_program(build_name + '_discovery', TEST,
                            libraries=[library_path], optimization='/O2')
    if artifact(library_path)['sha256'] != library_before:
        raise RuntimeError('Lua link input changed during dependency discovery')
    compiler_before = discovery['compiler']['sha256']
    if artifact(Path(discovery['compiler']['path']))['sha256'] != compiler_before:
        raise RuntimeError('Compiler binary changed after dependency discovery')
    discovered = {canon(row['path']): (Path(row['path']), row['sha256']) for row in discovery['compiler_inputs']}
    source_paths = {key: value[0] for key, value in discovered.items()}
    source_paths[canon(TOOL)] = TOOL
    for path in FROZEN:
        if canon(path) not in source_paths:
            raise RuntimeError('Expected frozen host/test source was not compiler-consumed: ' + str(path))
    before_all = {str(path): artifact(path)['sha256'] for path in source_paths.values()}
    for key, (path, digest) in discovered.items():
        if before_all[str(path)] != digest:
            raise RuntimeError('A dependency-discovery compiler input changed before freeze: ' + str(path))
    copy_paths = {}
    for key, original in source_paths.items():
        try:
            relative = original.relative_to(PROJECT)
        except ValueError:
            relative = Path('external') / hashlib.sha256(str(original).casefold().encode('utf-8')).hexdigest()[:20] / original.name
        copy = snapshot_root / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(original.read_bytes())
        if artifact(copy)['sha256'] != before_all[str(original)]:
            raise RuntimeError('Frozen copy differs from its source: ' + str(original))
        copy_paths[key] = copy
    frozen_by_canonical = {canon(path): path for path in source_paths.values()}
    frozen_tool = copy_paths[canon(TOOL)]
    unchanged(before_all)
    build = compile_program(build_name + '_frozen', TEST,
                            libraries=[library_path], optimization='/O2')
    if artifact(library_path)['sha256'] != library_before:
        raise RuntimeError('Lua link input changed during the frozen build')
    if build['compiler']['sha256'] != compiler_before or artifact(Path(build['compiler']['path']))['sha256'] != compiler_before:
        raise RuntimeError('Frozen build used a different compiler binary')
    consumed = {canon(row['path']): (Path(row['path']), row['sha256']) for row in build['compiler_inputs']}
    if set(consumed) != set(discovered):
        raise RuntimeError('Frozen build consumed a different compiler dependency set than discovery')
    for key, (path, digest) in consumed.items():
        if before_all[str(frozen_by_canonical[key])] != digest:
            raise RuntimeError('Frozen build compiler input differs from the pre-build snapshot: ' + str(path))
    unchanged(before_all)
    for _key, (path, digest) in consumed.items():
        if artifact(path)['sha256'] != digest:
            raise RuntimeError('A compiler input changed after the frozen build: ' + str(path))
    exe = Path(build['executable']['path'])
    result = run([exe], cwd=exe.parent, timeout=90)
    log = run_root / 'run.log'
    log.write_bytes(result.stdout + result.stderr)
    output = read_text(log)
    if result.returncode or 'COMBAT_PRESENTATION_PASS checks=' not in output or 'GAMECORE_LOADED=false' not in output:
        raise RuntimeError(f'Boundary regression failed exit=0x{result.returncode & 0xffffffff:08X}: ' + output[-6000:])
    unchanged(before_all)
    if artifact(Path(build['compiler']['path']))['sha256'] != compiler_before:
        raise RuntimeError('Compiler binary changed before the report was sealed')
    copied_compiler_inputs = []
    for key, (path, digest) in consumed.items():
        copy = copy_paths[key]
        if artifact(copy)['sha256'] != digest:
            raise RuntimeError('Retained frozen copy differs from consumed compiler input: ' + str(path))
        copied_compiler_inputs.append({**artifact(copy), 'original_source': str(frozen_by_canonical[key])})
    frozen_manifest = run_root / 'freeze_manifest.json'
    frozen_manifest.write_text(json.dumps({
        'inputs': [{'original_source': str(frozen_by_canonical[key]), 'sha256': before_all[str(frozen_by_canonical[key])],
                    'frozen_copy': str(copy_paths[key])} for key in sorted(copy_paths)]}, indent=2) + '\n', encoding='utf-8')
    builder_result = run_root / 'builder_result.json'
    builder_result.write_text(json.dumps(build, indent=2) + '\n', encoding='utf-8')
    report = {
        'status': 'COMBAT_PRESENTATION_COMPONENT_PASS',
        'run_id': run_id,
        'executable': build['executable'],
        'compiler': build['compiler'],
        'compiler_inputs': copied_compiler_inputs,
        'builder_result': artifact(builder_result),
        'runner': {**artifact(frozen_tool), 'original_source': str(TOOL)},
        'freeze_manifest': artifact(frozen_manifest),
        'run_log': artifact(log),
        'native_checks': int(output.split('COMBAT_PRESENTATION_PASS checks=', 1)[1].split()[0]),
        'gamecore_loaded': False,
        'sdk_dll_loaded': False,
        'scope': 'MOCKED_HOST_COMPONENT_BOUNDARY_FOR_COMBAT_CAPTURE_MOD_ACTIVATION_LOCAL_UNIT_COMMANDS_AND_UI_PRESENTATION',
        'limitations': 'Does not establish GameCore runtime effects, actual renderer behavior, SDK command acceptance, or retail callback equivalence.',
    }
    report_path = run_root / 'conformance.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    unchanged(before_all)
    check_artifacts(report)
    print(json.dumps({'status': report['status'], 'checks': report['native_checks'],
                      'executable': build['executable']['sha256'], 'report': artifact(report_path)}))


if __name__ == '__main__':
    main()
