"""Attest a linked private candidate without loading or executing the Host."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
from collect_baseline import pe_header


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def normalized(path):
    return os.path.normcase(os.path.abspath(path))


def dependencies(path):
    document = load(path)
    data = document.get('Data', document)
    return {normalized(p) for p in [data['Source'], *data['Includes']]}


def attest(path):
    path = Path(path)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify(build_id):
    report_path = PROJECT / 'evidence/ui_window_host' / build_id / 'build_result.json'
    report = load(report_path)
    require(report['build_id'] == build_id and report['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT',
            'Candidate is not successfully linked')
    require(report['source_inputs_unchanged'] and report['provider_inputs_unchanged'], 'Build input changed')
    require(not any(report[key] for key in ('gamecore_loaded', 'sdk_linked', 'stage_updated',
                                          'mods_updated', 'host_runtime_executed')), 'Build exceeded private compile scope')
    frozen = {normalized(row['original_path']): normalized(row['path']) for row in report['compiler_inputs']}
    for row in report['compiler_inputs']:
        require(sha(row['original_path']) == row['sha256'] == sha(row['path']), 'Compiler input changed')
    required_tus = {'host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer'}
    discoveries = {row['translation_unit']: row for row in report['dependency_discovery']['translation_units']}
    finals = {row['translation_unit']: row for row in report['final_compilation']['translation_units']}
    require(set(discoveries) == set(finals) == required_tus, 'Wrong translation-unit coverage')
    final_sets = {}
    for name in sorted(required_tus):
        require(discoveries[name]['returncode'] == finals[name]['returncode'] == 0, 'Compilation failed')
        for row in (discoveries[name], finals[name]):
            text = Path(row['log']['path']).read_text(encoding='utf8', errors='replace')
            require(not re.search(r'\bwarning\s+[A-Z]+\d+', text, re.I), 'Compiler emitted a warning')
        expected = {frozen[p] for p in dependencies(discoveries[name]['dependency_report']['path'])}
        final_sets[name] = dependencies(finals[name]['dependency_report']['path'])
        require(expected == final_sets[name], 'Final compile used a different header closure')
    names = {Path(p).name.lower() for p in final_sets['host_main']}
    require({'uipopupcontext.h', 'interactivegameloop.h', 'interactivegamesession.h',
             'interactiveuisession.h'}.issubset(names), 'Host missed current UI/session implementation')
    # The window produces tagged input; the host loop owns the deferred editor buffer.
    require('bitmapeditorinput.h' in names, 'Host loop missed its editor buffer')
    require('bitmapwindow.h' in names and 'bitmapwindow.h' in
            {Path(p).name.lower() for p in final_sets['window']}, 'Window/host event contract missing')
    sources = {Path(row['path']).name: row for row in report['sources']}
    header = sources['UiPopupAssets.generated.h']
    scene = sources['UiScene.lua']
    require(header['sha256'] == sha(header['path']), 'Generated catalog changed')
    require(scene['sha256'] == '39a0b4c3529ac03febb57ea9187074e3db39516e2eb1c1f3452136adcf41dfcd',
            'Candidate missed the current SaveMenu Lua correction')
    generated = Path(header['path']).read_bytes()
    match = re.search(rb'static const char ZeroSisUiScene\[\]=\r?\n(.*?);', generated, re.S)
    require(match is not None, 'Generated scene declaration missing')
    embedded = bytes(int(h, 16) for h in re.findall(rb'\\x([0-9a-f]{2})', match[1]))
    expected = Path(scene['path']).read_bytes() + b'\n' + Path(sources['UiPresentationInput.lua']['path']).read_bytes()
    for flag, addon in [('City', 'UiCityView.lua'), ('Unit', 'UiUnitPanel.lua'),
                        ('SocialPolicy', 'UiSocialPolicy.lua'), ('Economic', 'UiEconomicOverview.lua'),
                        ('ActionInfo', 'UiActionInfoPanel.lua'), ('Notification', 'UiNotificationPanel.lua')]:
        expected += b'\nif hasRetained' + flag.encode() + b'Ui then\n' + Path(sources[addon]['path']).read_bytes() + b'\nend\n'
    require(embedded == expected, 'Compiled scene differs from the complete current Lua/addendum assembly')
    for marker in (b'saveMenuGameTypes', b'GAME_SINGLE_PLAYER', b'NameBox', b'saveMenuSave', b'saveMenuClose', b'OnReturn'):
        require(marker in embedded, 'Required SaveMenu binding missing: ' + marker.decode())
    prepared = load(report['ui_assets']['path'])
    require(prepared['host_ui_runtime']['sha256'] == scene['sha256'], 'Prepared UI refers to an older scene')
    executable = Path(report['executable']['path'])
    require(sha(executable) == report['executable']['sha256'], 'Executable changed')
    pe = pe_header(executable)
    require(pe == report['executable']['pe'] and pe['architecture'] == 'x64', 'Wrong PE architecture')
    require({'imm32.dll', 'zerosislua51_x64.dll'}.issubset({s.lower() for s in report['imports']['dependencies']}),
            'Input/shared Lua dependency missing')
    require(not any('gamecore' in name.lower() or 'civilization' in name.lower()
                    for name in report['imports']['dependencies']), 'Retail module imported')
    reuse = report['frozen_input_reuse']
    require(reuse['donor_content_and_metadata_preserved'] and reuse['hardlinked_files'] > 0, 'Reuse not attested')
    before = load(Path(__file__).parent / 'frozen_reuse/before.json')
    protected = [row for row in before['files'] if row['relative_path'] in (
        'Play\\EarlyAccess\\release.json', 'tools\\Start-Engine.ps1',
        'evidence\\ui_window_host\\20261013T115435Z_2f60a56301d0\\build_result.json')]
    require(len(protected) == 3, 'Protected default/donor scope missing')
    require(all(sha(row['path']) == row['sha256'] for row in protected), 'Default or donor report changed')
    tests_path = Path(__file__).parent / 'frozen_reuse/result_20261013T140044Z_2df08189.json'
    tests = load(tests_path)
    require(tests['status'] == 'PASS' and tests['builder_sha256_loaded'] == report['source_hashes_before']['builder'],
            'Reuse tests do not cover the current builder')
    return {'schema': 'ZEROSIS_LINKED_HOST_NO_EXECUTION_ATTESTATION_V1', 'status': 'PASS',
            'utc': datetime.now(timezone.utc).isoformat(), 'build_id': build_id,
            'build_report': attest(report_path), 'executable': attest(executable), 'pe': pe,
            'translation_units': sorted(required_tus), 'compiler_warnings': 0,
            'exact_final_dependency_closure': True, 'current_source_frozen_hashes_match': True,
            'exact_embedded_current_scene_and_addenda': True, 'scene': scene,
            'generated_catalog': header, 'frozen_input_reuse': reuse, 'reuse_tests': attest(tests_path),
            'default_and_donor_report_unchanged': True, 'protected': protected,
            'host_executed_by_this_check': False, 'gamecore_loaded_by_this_check': False,
            'retail_mods_or_user_saves_scanned': False, 'native_window_acceptance_complete': False,
            'scope': 'Actual x64 compile/link, frozen source/catalog/import attestation only; no Host or SDK execution'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-id', required=True)
    args = parser.parse_args()
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id), 'Invalid build ID')
    result = verify(args.build_id)
    output = Path(__file__).parent / 'frozen_reuse' / ('linked_' + args.build_id + '.json')
    require(not output.exists(), 'Attestation already exists')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': result['status'], 'build_id': args.build_id,
                      'report': str(output), 'sha256': sha(output), 'reuse': result['frozen_input_reuse']}))
