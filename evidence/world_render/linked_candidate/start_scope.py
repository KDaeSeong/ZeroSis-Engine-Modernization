"""Scope one current camera/civilian Host link and private preparation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
DONOR = '20261016T122615Z_1af4a5449cf1'
CPP = ('Source/Host/InteractiveGameLoop.h', 'Source/Presentation/WorldViewRenderer.h',
       'Source/Presentation/WorldViewRenderer.cpp', 'Source/Presentation/WorldTerrainRenderer.cpp',
       'Source/Presentation/WorldCameraControls.h', 'Source/Presentation/WorldUnitArtSelection.h')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def pinned(relative, expected):
    row = artifact(PROJECT / relative)
    require(row['sha256'] == expected, 'Approved input changed: ' + relative)
    return row


def main():
    destination = STAGE / 'scope.json'
    require(not destination.exists(), 'Inspect an existing scope instead of replacing it')
    progress = pinned('evidence/save_menu/20261013_original_screen/current_progress.json', 'b2cfc00355f2da7fb1afdea8315fa1d8e9b211a5c7b6f73aa121c58be6ca8a41')
    prior = {name: pinned(path, sha) for name, path, sha in (
        ('overwrite', 'evidence/save_overwrite/source_contract/conformance.json', '7b69f3fca41b188d7ff6b403183f0cc2964d47d2e9f135ad9b339f7ff04e43cb'),
        ('camera', 'evidence/world_camera/controls/conformance.json', '9c21c35700576ed4aa4c6e8264f88571e1531624770c53a21057cd42306fbca2'),
        ('civilian', 'evidence/unit_models/civilian_start/conformance.json', 'c8417ed25b5949af2a7e7ab1fdb28c744e6d126fb83a32692f0dacb8d909d57d'))}
    donor = pinned(f'evidence/ui_window_host/{DONOR}/build_result.json', '1c6e4f2640bca96c687fb118e47e48116d8162a48276ccc91405578a40ea170d')
    build, overwrite, civilian = (read(row['path']) for row in (donor, prior['overwrite'], prior['civilian']))
    for row in overwrite['sources']:
        require(artifact(row['path']) == row, 'An overwrite-approved source changed')
    cpp = [artifact(PROJECT / relative) for relative in CPP]
    syntax = read(civilian['proofs']['actual_current_consumer_syntax']['path'])
    consumed = {row['path'].casefold(): row for row in syntax['project_inputs_after'].values()}
    for row in cpp:
        expected = consumed[row['path'].casefold()]
        require(all(row[key] == expected[key] for key in ('bytes', 'sha256')), 'Current syntax scope differs')
    changed, unchanged = [], []
    for row in build['compiler_inputs']:
        path = Path(row['original_path'])
        if row.get('root_name') == 'project' and path.is_relative_to(PROJECT / 'Source'):
            current = artifact(path)
            if current['sha256'] != row['sha256']:
                changed.append({'relative': path.relative_to(PROJECT).as_posix(),
                    'before': {key: row[key] for key in ('path', 'bytes', 'sha256')}, 'current': current})
            else:
                unchanged.append(current)
    require({row['relative'] for row in changed} == set(CPP[:4]), 'Unexpected Source changes beyond approved camera/civilian delta')
    roles, by_tu = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer'), {}
    for phase in ('dependency_discovery', 'final_compilation'):
        require(len(build[phase]['translation_units']) == 5, 'Expected five translation units')
        for role, row in zip(roles, build[phase]['translation_units']):
            ref = row['response']
            response_ref = artifact(ref['path'])
            require(response_ref['sha256'] == ref['sha256'], 'Baseline response changed')
            flags = Path(ref['path']).read_text('utf-8-sig').splitlines()
            language = [flag for flag in flags if flag.startswith('/std:')]
            charset = [flag for flag in flags if flag.startswith('/source-charset:')]
            require(language == ['/std:c++17' if role == 'terrain_renderer' else '/std:c++14'], 'Baseline C++ profile differs')
            require(charset == ['/source-charset:utf-8' if role == 'world_renderer' else '/source-charset:windows-1252'], 'Baseline charset differs')
            item = by_tu.setdefault(role, {'baseline_responses': {}})
            item[phase] = {'language': language[0], 'source_charset': charset[0],
                'required_flags': ['/EHsc', '/W4', '/WX', '/O2', '/MD', '/fp:strict'],
                'forbidden_flags': ['/Od', '/MT', '/MDd', '/Zi', '/ZI', '/Yc', '/Yu', '/Zs'],
                'defines_exact': [flag for flag in flags if flag.startswith('/D')]}
            item['baseline_responses'][phase] = response_ref
    headers = [row for row in build['compiler_inputs'] if Path(row['path']).name == 'UiPopupAssets.generated.h']
    require(len(headers) == 1, 'Frozen generated header is ambiguous')
    recovery = {key: headers[0][key] for key in ('path', 'bytes', 'sha256')}
    require(artifact(recovery['path']) == recovery, 'Frozen header recovery changed')
    generated = artifact(PROJECT / 'Source/Host/UiPopupAssets.generated.h')
    require(generated['sha256'] == recovery['sha256'] and Path(generated['path']).stat().st_nlink == 1, 'Mutable header aliases a frozen input')
    previous = read(PROJECT / 'evidence/unit_models/civilian_start/scope.json')['existing_files_before'][0]
    require(artifact(previous['backup']['path']) == previous['backup'] and previous['backup']['sha256'] == 'd8df1ed76c8ac71685a2a187d25729840758b77425de4e2363f7f2b81bbb798b', 'Camera-to-civilian terrain predecessor differs')
    protected = [pinned(path, sha) for path, sha in (
        ('Play/EarlyAccess/release.json', '5587028d64ff6206780837ee7112f0c34d62676fb0627ee099d4eb03aef9c2c5'),
        ('tools/Start-Engine.ps1', 'c487ce6c89e374bb625961ce81cf6cbae210608c578542658038e6cb06173d7c'),
        ('Source/Host/NativeSaveArchive.h', 'd1ce478b093adb53acb280ff8d286ffa1d791f28783d888d9f22738e69a8e5dc'),
        (f'Build/UiWindowHost/{DONOR}/final/ZeroSisHost_x64.exe', 'c830cd9faecea8c8696375850759fcab2500fe351d049983c5d8c4ff9f389f17'),
        ('evidence/interactive_game/20261016T123256Z_fae85fb9fe79/request.json', 'f0b9b8e898946337a56b6fc180b783b552385104b3786cd573b6ebbf42ca07ef'))]
    dependencies = {name: pinned(path, sha) for name, path, sha in (
        ('overwrite_wrapper', 'evidence/save_overwrite/linked_candidate/verify_candidate.py', '98622bfbdd93fe19c0863fec397a5390272bc5a6f060cb26ed6babcf22009686'),
        ('common_pe', 'evidence/save_delete/linked_candidate/verify_candidate.py', 'dd06ea0c0b31faa2423639eb2f95fdd11c3ffcd6ae1ae48a9505280e3d6ba4da'),
        ('pe_base', 'Tests/verify_load_menu_linked_candidate.py', '54388cfc99f1e00e6143da71a64439d165f502b099d6c9e019524e48743aa3a2'))}
    unit = {name: pinned(path, sha) for name, path, sha in (
        ('binary', 'Build/UnitAssets/fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573/unit-assets.bin', 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'),
        ('manifest', 'Build/UnitAssets/fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573/unit-assets.manifest.json', '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'),
        ('preparation_contract', 'evidence/unit_models/civilian_start/preparation_contract.json', '1a3b3659482c1d39fed0a32041697a3701f664a6d9f059c24002365be0566436'))}
    backup = STAGE / 'source_before/current_progress.json'
    backup.parent.mkdir(exist_ok=False)
    shutil.copyfile(progress['path'], backup)
    require(artifact(backup)['sha256'] == progress['sha256'], 'Progress backup differs')
    scope = {'schema': 'zerosis.world_camera_civilian_linked_scope.v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'previous_goal_turn': 'PROGRESS', 'requirements': [
            'Compile/link one current x64 Host with camera and grounded civilian-art selection; preserve the full original UI/3D/campaign/save/mod/multicore endpoint.',
            'Read actual PE/UI62 bytes and five current TU compile/link lineage; no machine-code behavioral acceptance claim.',
            'Prepare a matching private run with the new external three-art package, shared immutable inputs and two private databases.',
            'Retain B7/R7, default EA0.6 and required recovery; retire only proven superseded B6/R6 plus current intermediates after acceptance.',
            'No Host/GameCore/HWND or retail MODS/user saves/settings/process access during human new-mod testing.'],
        'original_game_new_mod_test_hold': True, 'retail_mod_test_hold_active': True,
        'default_promoted': False, 'execution_allowed': False, 'host_gamecore_hwnd_executed': False,
        'prior_source_conformances': prior,
        'prior_linked_conformance': pinned('evidence/save_overwrite/linked_candidate/conformance.json', '2bf87c5f1805df28586a8795bed733219679d6f76d7f05af9c94da65daf2b1aa'),
        'historical_ui_attestation': pinned(f'evidence/save_overwrite/linked_candidate/attestation_{DONOR}.json', 'be044d872c99f21317fea7f97a024b31bf02e05eedecf87d25f3e05102908578'),
        'verifier_dependencies': dependencies, 'source19_seals': overwrite['sources'], 'cpp_feature_seals': cpp,
        'unchanged_project_source_seals': unchanged,
        'unchanged_baseline_seals': {relative: artifact(PROJECT / relative) for relative in ('Source/Host/UiLoadMenuContract.h', 'tools/prepare_ui_popup_assets.py')},
        'source_precedence': [{'relative': CPP[3], 'superseded': previous['source'], 'superseded_backup': previous['backup'], 'current': cpp[3], 'approval': prior['civilian']}],
        'donor_build': donor, 'frozen_input_reuse_donor': donor,
        'cpp_negative_control': {'build': donor, 'expected_changed_existing': changed, 'expected_missing_new': list(CPP[4:]), 'historical_ui_feature_remains_valid': True},
        'current_unit_assets': unit,
        'expected_cpp_consumers': {CPP[4]: ['host_main', 'world_renderer', 'terrain_renderer'], CPP[1]: ['host_main', 'world_renderer', 'terrain_renderer'], CPP[0]: ['host_main'], CPP[2]: ['world_renderer'], CPP[3]: ['terrain_renderer'], CPP[5]: ['terrain_renderer']},
        'expected_compile_profile': {'by_tu': by_tu}, 'protected_artifacts': protected,
        'header_recovery': recovery, 'generated_header_before': generated, 'prepared_assets_recovery': build['ui_assets'],
        'prepared_assets_before': artifact(PROJECT / 'evidence/ui_popup/assets/prepared.json'),
        'builder': pinned('tools/build_ui_window_host.py', '04a69d9ab99dab2f6f4566084cb87ce294bf6e9adb5c6410d790a763f25397ef'),
        'common_helper': artifact(PROJECT / 'evidence/save_delete/linked_candidate/run_stage.py'),
        'progress_before': progress, 'progress_backup': artifact(backup),
        'storage_before': artifact(PROJECT / 'evidence/storage/20261016T141227Z.json'),
        'cleanup_at_start': 'Prior COMPLETE cleanup35 revalidated absent; no whole source/header clone, frozen B7 header is recovery input.',
        'full_engine_goal_complete': False}
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(scope, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps({'scope': artifact(destination), 'cpp_changed_existing': 4, 'cpp_new_headers': 2,
                      'unchanged_project_sources': len(unchanged), 'backup_bytes': backup.stat().st_size,
                      'header_recovery_reused_without_copy': True}))


if __name__ == '__main__':
    main()
