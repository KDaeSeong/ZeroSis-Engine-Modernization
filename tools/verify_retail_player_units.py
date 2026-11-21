"""Build and run the standalone BNW Unit body and Player unit-list framing component."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
from collect_baseline import pe_header
from native_build import environment_for
from verify_retail_save_header import artifact, require, key, within, pe_imports, COMPILER, COMPILER_SHA, VS
from verify_retail_save_state import public_input, OUTPUT_SHA

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/player_units'
REPORT = STAGE / 'build_result.json'
SOURCE = PROJECT / 'Tests/retail_player_units.cpp'
HEADER_NAMES = (
    'RetailSavePlayerUnits.h', 'RetailSaveUnit.h', 'RetailSaveUnitArchive.h',
    'RetailSaveUnitServices.h', 'RetailSavePlayerCities.h', 'RetailSaveCity.h', 'RetailSaveFreeList.h',
    'RetailSaveCityServices.h', 'RetailSaveCityPopulation.h', 'RetailSavePlayerPostTraits.h', 'RetailSavePlayerEspionage.h', 'RetailSavePlayerTrade.h',
    'RetailSavePlayerServices.h', 'RetailSavePlayerAiLate.h', 'RetailSavePlayerMinor.h',
    'RetailSavePlayerInfrastructure.h', 'RetailSavePlayerTraits.h', 'RetailSavePlayerAiMid.h',
    'RetailSavePlayerDiplomacy.h', 'RetailSavePlayerReligionTech.h', 'RetailSavePlayerTactical.h',
    'RetailSavePlayerPrefix.h', 'RetailSavePlayerFront.h', 'RetailSavePlayerAiEarly.h',
    'RetailSavePlayerAiStrategy.h', 'RetailSaveStateWire.h', 'RetailSaveMap.h', 'RetailSavePlot.h',
    'RetailSaveMapTail.h', 'RetailSaveState.h', 'RetailSaveGameFront.h', 'RetailSaveGameTail.h',
    'RetailSaveTeam.h')



def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def unchanged(rows):
    for row in rows:
        require(artifact(row['path']) == row, 'A pinned component input changed: ' + row['path'])


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected component arguments')
    from inspect_unit_object_sources import inspect
    headers = [PROJECT / 'Source/Host' / name for name in HEADER_NAMES]
    helpers = [PROJECT / 'tools' / name for name in ('verify_retail_player_units.py',
        'inspect_unit_object_sources.py', 'inspect_player_post_traits_sources.py',
        'verify_retail_save_header.py',
        'verify_retail_save_state.py', 'native_build.py', 'collect_baseline.py',
        'publish_retail_team_stage.py')]
    inputs = [artifact(path) for path in (SOURCE, *headers, *helpers)]
    compiler = artifact(COMPILER)
    require(compiler['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    fingerprint = hashlib.sha256(json.dumps({'inputs': inputs, 'compiler': compiler}, sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT / 'Build/RetailSavePlayerUnits' / fingerprint
    if REPORT.exists():
        prior = read(REPORT)
        require(prior['status'] == 'PASS_X64_RETAIL_PLAYER_UNITS_COMPONENT' and
                prior['inputs'] == inputs, 'Inspect the existing component before replacing it')
        for mode in prior['results']:
            unchanged([mode['executable'], mode['dependencies'], mode['response']])
        unchanged(prior['source_inputs'])
        unchanged([prior['source_conformance']])
        print(json.dumps({'status': 'CURRENT_COMPONENT_REUSED', 'report': artifact(REPORT)}))
        return 0
    require(not root.exists() and not (STAGE / 'build_started.json').exists(),
            'Inspect prior partial output instead of starting another build')
    # Read the pinned public fixture into memory before installing the offline guard.
    # The inflater's nonfinal termination remains diagnostic, not loader approval.
    public = public_input()
    require(hashlib.sha256(public).hexdigest() == OUTPUT_SHA, 'Public RAM input changed')
    conformance = inspect(PROJECT)
    source_inputs = conformance['inputs']
    unchanged(source_inputs)
    protected_paths = [PROJECT / name for name in (
        'Play/EarlyAccess/release.json', 'tools/Start-Engine.ps1',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        'evidence/sdk_runtime_play/post_publication_checks.json',
        'evidence/sdk_runtime_play/preparation_started.json',
        'evidence/sdk_runtime_play/prepared.json',
        'evidence/sdk_runtime_current/build_result.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'docs/M7_RETAIL_SAVE_BOUNDARY.md',
        'evidence/retail_save_container/player_post_traits/build_result.json',
        'evidence/retail_save_container/player_post_traits/post_publication_checks.json',
        'evidence/retail_save_container/player_cities/build_result.json',
        'evidence/retail_save_container/player_cities/post_publication_checks.json')]
    old_preparation = read(PROJECT / 'evidence/sdk_runtime_play/preparation_started.json')
    # These are the retained bytes actually protected by the current preparation,
    # not historical discovery objects or mutable original-game state.
    protected_paths.extend(Path(row['path']) for row in old_preparation['protected_inputs'])
    protected_paths.extend(Path(row['path']) for row in source_inputs)
    current = read(PROJECT / 'evidence/sdk_runtime_play/prepared.json')
    protected_paths.append(Path(current['request']['path']))
    protected_paths.extend(Path(row['path']) for row in read(current['request']['path'])['runtime_inputs'])
    protected = list({key(path): artifact(path) for path in protected_paths}.values())
    for row in protected:
        path = Path(row['path'])
        require(within(path, PROJECT) or within(path, Path(sys.executable).parent),
                'Unexpected protected path outside the engine and interpreter')
    for path in (root, *root.parents, STAGE):
        if path.exists():
            require(not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400, 'Reparse build path')
    root.parent.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    allowed = {('cmd.exe', '/d', '/c', str(root / 'read_build_environment.cmd'))}
    calls, denied = [], []
    reports = {key(STAGE / name) for name in ('build_started.json', 'build_result.json',
        'failed_attempt.json', 'source_conformance.json', 'compile_O2.log', 'compile_Od.log',
        'test_O2.log', 'test_Od.log')}

    def fail(reason):
        denied.append(reason)
        raise RuntimeError(reason)

    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((x for x in allowed if subprocess.list2cmdline(x) == args[1]), None) \
                if isinstance(args[1], str) else tuple(str(x) for x in args[1])
            if command not in allowed:
                fail('Unapproved component child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                    Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe',
                    'Unexpected executable override')
            calls.append(command)
        if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            target = os.fsdecode(args[0])
            parts = [part.casefold() for part in Path(target).parts]
            if any(part in ('my games', 'mods', 'saves', '.codex') for part in parts) or \
                    ('steamapps' in parts and 'common' in parts):
                fail('Original-game or internal state access is outside this component')
            if event == 'open':
                writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                    isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                if writing and not (within(target, root) or key(target) in reports):
                    fail('Write escaped component outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            for target in args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]:
                if isinstance(target, (str, bytes, os.PathLike)) and not within(os.fsdecode(target), root):
                    fail('Mutation escaped component build root')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or \
                event in ('os.system', 'os.startfile', 'os.startfile/2'):
            fail('Network, dynamic loading and interactive launch are forbidden')

    sys.addaudithook(audit)
    root.mkdir()
    (STAGE / 'build_started.json').write_text(json.dumps({'schema': 'zerosis.retail.player_units.started.v1',
        'inputs': inputs, 'protected': protected, 'build_root': str(root),
        'public_bytes': len(public), 'public_sha256': OUTPUT_SHA,
        'previous_goal_turn_classification': 'progress'}, indent=2) + '\n', encoding='utf8')
    (STAGE / 'source_conformance.json').write_text(json.dumps(conformance, indent=2) + '\n', encoding='utf8')
    results = []
    try:
        environment, selected = environment_for(VS, 'x64', root)
        require(key(selected) == key(COMPILER), 'Compiler selection changed')
        environment['VSLANG'] = '1033'
        for flavor, options in (('O2', ['/O2']), ('Od', ['/Od', '/RTC1'])):
            directory = root / flavor
            directory.mkdir()
            environment['TMP'] = environment['TEMP'] = str(directory)
            exe, obj = directory / 'RetailSavePlayerUnitsTests.exe', directory / 'retail_player_units.obj'
            response, dependencies = directory / 'compile.rsp', directory / 'dependencies.json'
            flags = ['/nologo', '/std:c++17', '/EHsc', '/W4', '/WX', '/MT', '/utf-8', *options,
                     f'/I"{PROJECT / "Source/Host"}"',
                     f'"{SOURCE}"', f'/Fo"{obj}"', f'/Fe"{exe}"', f'/sourceDependencies "{dependencies}"']
            response.write_text('\n'.join(flags) + '\n', encoding='utf8')
            command = [str(COMPILER), '@' + str(response), '/link', '/MACHINE:X64', '/INCREMENTAL:NO',
                       '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF']
            allowed.add(tuple(command))
            compiled = subprocess.run(command, cwd=directory, env=environment, capture_output=True,
                timeout=120, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            output = (compiled.stdout + compiled.stderr).decode('mbcs', errors='replace')
            compile_log = STAGE / ('compile_' + flavor + '.log')
            compile_log.write_text(output, encoding='utf8')
            require(compiled.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', output, re.I),
                    'Compile failed; inspect ' + compile_log.name)
            dependency_data = read(dependencies)['Data']
            require(key(dependency_data['Source']) == key(SOURCE) and
                    all(any(key(h) == key(x) for x in dependency_data['Includes']) for h in headers) and
                    not any('sdk_bnw_' in key(x) for x in dependency_data['Includes']),
                    'Actual portable header dependencies differ')
            imports = pe_imports(exe)
            require(imports == ['kernel32.dll'], 'Component imports exceed the headless scope')
            pe = pe_header(exe)
            command = [str(exe), '--public']
            allowed.add(tuple(command))
            tested = subprocess.run(command, cwd=directory, env=environment, input=public,
                capture_output=True, timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            output = (tested.stdout + tested.stderr).decode('utf8', errors='replace').strip()
            test_log = STAGE / ('test_' + flavor + '.log')
            test_log.write_text(output + '\n', encoding='utf8')
            require(tested.returncode == 0, 'Component tests failed; inspect ' + test_log.name)
            observation = json.loads(output)
            require(observation['status'] == 'PASS_RETAIL_PLAYER_UNITS_COMPONENT' and
                    observation['synthetic_cases'] >= 4 and observation['checks'] > 1000 and
                    observation['truncations'] >= 768 and observation['mutations'] == 2048 and
                    observation['accepted_mutations'] + observation['rejected_mutations'] == 2048,
                    'Missing independent fixture, truncation or mutation evidence')
            for field in ('gamecore_loaded', 'window_created', 'game_accessed', 'user_saves_accessed',
                          'complete_player_validated', 'complete_save_validated', 'ruleset_compatibility_verified', 'restore_approved'):
                require(observation[field] is False, 'Component exceeds its scope: ' + field)
            require(observation['input_files_unchanged'] is True and observation['input_bytes_unchanged'] is True,
                    'Input preservation checks missing')
            public_result = observation['public']
            require(public_result['input_bytes'] == len(public) and public_result['start_offset'] == 2428055 and
                    public_result['next_inflated_offset'] > 2428055 and public_result['unit_count'] > 0,
                    'Public inspection did not frame the exact occupied unit-list boundary')
            results.append({'mode': flavor, 'executable': artifact(exe), 'object': artifact(obj),
                'dependencies': artifact(dependencies), 'response': artifact(response), 'compile_log': artifact(compile_log),
                'test_log': artifact(test_log), 'pe': pe, 'imports': imports, 'test': observation})
        require(results[0]['test'] == results[1]['test'], 'Optimized and checked observations differ')
        unchanged(inputs)
        unchanged(protected)
        require(not denied, 'A forbidden operation was attempted')
        retired = []
        for path in [*[Path(row['object']['path']) for row in results], root / 'read_build_environment.cmd']:
            info = path.lstat()
            require(within(path, root) and stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                    not getattr(info, 'st_file_attributes', 0) & 0x400, 'Unexpected intermediate identity')
            row = {**artifact(path), 'file_identity': [info.st_dev, info.st_ino], 'mtime_ns': info.st_mtime_ns}
            after = path.lstat()
            require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) ==
                    (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) and
                    artifact(path)['sha256'] == row['sha256'],
                    'Intermediate changed before retirement')
            path.unlink()
            retired.append(row)
        report = {'schema': 'zerosis.retail_save.player_units.v1',
            'status': 'PASS_X64_RETAIL_PLAYER_UNITS_COMPONENT', 'utc': datetime.now(timezone.utc).isoformat(),
            'build_root': str(root), 'inputs': inputs, 'compiler': compiler, 'results': results,
            'source_inputs': source_inputs,
            'source_conformance': artifact(STAGE / 'source_conformance.json'),
            'protected': protected, 'protected_unchanged': True, 'child_commands': [list(x) for x in calls],
            'forbidden_access_attempts': denied, 'retired_intermediates': retired,
            'retired_logical_bytes': sum(x['bytes'] for x in retired),
            'previous_goal_turn_classification': 'progress', 'public_inflated_input_bytes': len(public),
            'public_inflated_sha256': OUTPUT_SHA, 'public_save_or_body_retained': False,
            'original_install_or_user_saves_accessed': False, 'host_gamecore_or_hwnd_executed': False,
            'integrated_into_current_host': False, 'full_sdk_recompiled': False,
            'sdk_restore_verified': False, 'full_player_framed': False, 'public_unit_bodies_structurally_framed': True,
            'synthetic_unit_bodies_framed': True, 'unit_object_id_placement_verified': False, 'full_engine_goal_complete': False}
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
        print(json.dumps({'status': report['status'], 'checks_per_mode': results[0]['test']['checks'],
            'public': results[0]['test']['public'], 'retired_logical_bytes': report['retired_logical_bytes'],
            'report': artifact(REPORT)}))
        return 0
    except BaseException as error:
        (STAGE / 'failed_attempt.json').write_text(json.dumps({'status': 'FAILED_RETAIL_PLAYER_UNITS_COMPONENT',
            'error': type(error).__name__ + ': ' + str(error), 'build_root': str(root),
            'inputs': inputs, 'completed_modes': results, 'child_commands': [list(x) for x in calls],
            'forbidden_access_attempts': denied, 'native_engine_executed': False}, indent=2) + '\n', encoding='utf8')
        raise


if __name__ == '__main__':
    raise SystemExit(main())
