"""Exercise real cached font loading while all installed-game opens are denied."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import ui_font_profile as fonts


def ref(path):
    with Path(path).open('rb') as stream:
        return {'path': str(path), 'bytes': Path(path).stat().st_size,
                'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def main():
    assert sys.dont_write_bytecode and not sys.flags.optimize
    output = STAGE / 'owned_input_contract.json'
    assert not output.exists()
    before = [ref(fonts.PROFILE_PATH), ref(Path(fonts.__file__))]
    profile = json.loads(fonts.PROFILE_PATH.read_bytes())
    cases, fixtures = [], []
    for name, root in [('installed', str(fonts.GAME)),
                       ('outside', str(PROJECT / ('a' * 64))),
                       ('bad_name', str(PROJECT / 'Build/SharedUiFontInputs/not_a_content_hash'))]:
        value = copy.deepcopy(profile)
        value['asset_root'] = root
        value['profile_id'] = fonts.profile_identity(value)
        fixture = STAGE / ('owned_input_negative_' + name + '.json')
        with fixture.open('x', encoding='utf-8') as stream:
            json.dump(value, stream)
        fixtures.append((name, fixture))
    installed = os.path.normcase(str(fonts.GAME))
    denied_installed, denied_process = [], []

    def audit(event, arguments):
        if event == 'open' and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            path = os.path.normcase(os.path.abspath(os.fsdecode(arguments[0])))
            if path == installed or path.startswith(installed + os.sep):
                denied_installed.append(path)
                raise RuntimeError('Installed game input was accessed')
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'ctypes.')) or event in ('os.system', 'os.startfile'):
            denied_process.append(event)
            raise RuntimeError('No process, window or DLL activity in the owned input contract')

    sys.addaudithook(audit)
    try:
        root = fonts.profile_input_root()
        parsed_profile, parsed = fonts.load_font_profile()
        assert parsed_profile == profile and set(parsed) == set(fonts.FONT_IDS)
        assert all(font.ggxml_path.is_relative_to(root) and
                   len(font.glyphs) == profile['fonts'][name]['glyph_count'] for name, font in parsed.items())
        cases.append({'name': 'real_complete_cache_load_with_installed_opens_denied', 'pass': True})
        for name, fixture in fixtures:
            try:
                fonts.profile_input_root(fixture)
            except ValueError as error:
                assert 'engine-owned cache' in str(error)
                cases.append({'name': name, 'pass': True, 'rejection': str(error)})
            else:
                raise AssertionError('Non-cache font root was accepted: ' + name)
        stale = copy.deepcopy(profile)
        stale['fonts']['TwCenMT14']['ggxml']['sha256'] = '0' * 64
        stale['fonts']['TwCenMT16']['ggxml']['sha256'] = '0' * 64
        stale['profile_id'] = fonts.profile_identity(stale)
        try:
            fonts.verify_profile_inputs(stale, root)
        except ValueError as error:
            assert 'differs from the sealed profile' in str(error)
            cases.append({'name': 'actual_cached_file_sha_mismatch_rejected', 'pass': True, 'rejection': str(error)})
        else:
            raise AssertionError('Changed cache identity was accepted')
        assert not denied_installed and not denied_process
        assert [ref(fonts.PROFILE_PATH), ref(Path(fonts.__file__))] == before
        report = dict(schema='zerosis.ui.owned_font_input_contract.v1', status='PASS', inputs=before,
                      cases=cases, case_count=len(cases), installed_input_opens=0, additional_processes_or_dlls=0,
                      parsed_font_count=len(parsed), parsed_glyph_counts={name: len(font.glyphs) for name, font in parsed.items()},
                      cached_files_verified=len(fonts.verify_profile_inputs(profile, root)),
                      host_gamecore_hwnd_executed=False, retail_user_state_accessed=False, native_acceptance_verified=False)
    finally:
        for _, fixture in fixtures:
            fixture.unlink()
    assert all(not fixture.exists() for _, fixture in fixtures)
    report['temporary_manifests_removed'] = len(fixtures)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'cases': len(cases), 'receipt': ref(output)}))


if __name__ == '__main__':
    main()
