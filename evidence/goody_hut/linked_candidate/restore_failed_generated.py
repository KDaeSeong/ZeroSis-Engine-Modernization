"""Restore exactly two disposable engine outputs after a precompile size failure."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import stat
import sys
import xml.etree.ElementTree as ET

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
OUTPUT = STAGE / 'failed_generated_restored.json'
RETAIL = os.path.normcase(os.path.abspath(r'C:\Users\home\OneDrive\Documents\My Games'))


def ref(path):
    path = Path(path)
    assert path.is_absolute() and path.resolve(strict=True) == path
    before = path.stat()
    assert stat.S_ISREG(before.st_mode) and not before.st_file_attributes & 0x400
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def seal(row):
    fresh = ref(row['path'])
    assert all(fresh[key] == row[key] for key in ('bytes', 'sha256'))
    return fresh


def main():
    assert not sys.flags.optimize and sys.dont_write_bytecode and not OUTPUT.exists()
    scope = json.loads((STAGE / 'scope.json').read_bytes())
    run = json.loads((STAGE / 'build_run.json').read_bytes())
    failed = json.loads((STAGE / 'catalog.json').read_bytes())
    size = json.loads((STAGE / 'generated_size_diagnostic.json').read_bytes())
    assert run['status'] == 'FAIL' and run['new_build_ids'] == [] and run['actual_objects'] == []
    assert failed['error'] == 'Input exceeds its bounded size' and failed['guard']['explicit_lua_provider_loads'] == 0
    assert scope['retail_mod_test_hold_active'] and not run['forbidden_access_attempts']
    base = json.loads(Path(scope['baseline_build']['path']).read_bytes())
    lease = [
        (PROJECT / 'Source/Host/UiPopupAssets.generated.h', Path(scope['baseline_generated_header']['path'])),
        (PROJECT / 'evidence/ui_popup/assets/prepared.json', Path(base['ui_assets']['path'])),
    ]
    old = {row['path']: row for row in scope['mutable_derived_before']}
    before, sources = [], []
    for target, source in lease:
        assert target.is_relative_to(PROJECT) and source.is_relative_to(PROJECT / 'Build/UiWindowHost' / scope['baseline_build_id'])
        actual, preserved = ref(target), ref(source)
        assert preserved['bytes'] == old[str(target)]['bytes'] and preserved['sha256'] == old[str(target)]['sha256']
        assert target.stat().st_nlink == 1 and not target.stat().st_file_attributes & 1
        assert (target.stat().st_dev, target.stat().st_ino) != (source.stat().st_dev, source.stat().st_ino)
        before.append(actual); sources.append(preserved)
    assert before[0] == {key: size['headers'][1][key] for key in ('path', 'bytes', 'sha256')}
    assert [row['bytes'] for row in before] == [423827534, 235676024]
    preservation = json.loads(Path(scope['frozen_preservation']['path']).read_bytes())
    source = json.loads(Path(scope['source_seal']['path']).read_bytes())
    rows = [*preservation['artifacts'], *source['production_sources'].values(), *source['new_assets_and_tests'].values(),
            *scope['source_backup_refs'], *sources, scope['progress_before'], scope['source_seal'], scope['source_conformance'],
            *[ref(STAGE / name) for name in ('scope.json', 'build_once.py', 'check_catalog.py', 'build_started.json', 'build_run.json', 'catalog.json', 'catalog_process.json', 'generated_size_diagnostic.json', 'restore_failed_generated.py')]]
    protected = list({row['path']: seal(row) for row in rows}.values())
    fonts = []
    font_root = Path(scope['original_goody_assets']['xml']['path']).parents[6] / 'Assets/UI/Fonts/Tw Cent MT'
    assert str(font_root).startswith(r'C:\Program Files (x86)\Steam\steamapps\common\Sid Meier')
    for font_id in ('TwCenMT14', 'TwCenMT16', 'TwCenMT20', 'TwCenMT22', 'TwCenMT24'):
        path = font_root / (font_id + '.ggxml')
        row = ref(path)
        glyphs = ET.fromstring(path.read_bytes()).find('glyphs')
        assert glyphs is not None and int(glyphs.attrib['count']) == len(glyphs.findall('glyph'))
        fonts.append(dict(font_id=font_id, input=row, glyph_count=len(glyphs.findall('glyph'))))
    temporary = [target.with_name(target.name + '.goody_restore.tmp') for target, _ in lease]
    assert not any(path.exists() for path in temporary)
    write_allow = {os.path.normcase(str(path)) for path in (*temporary, OUTPUT)}
    replace_allow = {(os.path.normcase(str(src)), os.path.normcase(str(dst))) for src, (dst, _) in zip(temporary, lease)}
    denied = []

    def guard(event, args):
        if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
            assert path != RETAIL and not path.startswith(RETAIL + os.sep)
            if event == 'open' and ((isinstance(args[1], str) and any(char in args[1] for char in 'wax+')) or args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                assert path in write_allow
        if event == 'os.rename':
            assert (os.path.normcase(str(args[0])), os.path.normcase(str(args[1]))) in replace_allow
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'socket.')) or event in ('ctypes.dlopen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.remove', 'os.rmdir', 'os.link', 'os.symlink', 'os.chmod'):
            denied.append(event)
            raise RuntimeError('Execution and unrelated mutation forbidden')

    sys.addaudithook(guard)
    receipt = dict(schema='zerosis.goody_hut.failed_generated_restoration.v1', status='STARTED', utc=datetime.now(timezone.utc).isoformat(),
        failed_attempt=ref(STAGE / 'build_run.json'), targets_before=before, preserved_sources=sources, current_installed_font_inputs=fonts,
        source_of_external_font_change_identified=False, original_installed_files_changed=False, preserved_artifact_count=len(protected),
        restorations=[], large_failure_payload_copies=0, raw_generated_failure_payload_retained=False,
        host_gamecore_hwnd_executed=False, retail_user_state_or_game_processes_accessed=False, full_engine_goal_complete=False)
    with OUTPUT.open('x', encoding='utf-8') as stream:
        def emit():
            stream.seek(0); json.dump(receipt, stream, indent=2); stream.write('\n'); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
        emit()
        try:
            for index, ((target, source), temp) in enumerate(zip(lease, temporary)):
                assert ref(target) == before[index] and ref(source) == sources[index] and target.stat().st_nlink == 1
                shutil.copyfile(source, temp)
                copied = ref(temp)
                assert all(copied[key] == sources[index][key] for key in ('bytes', 'sha256'))
                os.replace(temp, target)
                after = ref(target)
                assert all(after[key] == sources[index][key] for key in ('bytes', 'sha256'))
                receipt['restorations'].append(dict(before=before[index], after=after, source=sources[index])); emit()
            assert [ref(row['path']) for row in protected] == protected and not denied
            receipt.update(status='PASS_EXACT_TWO_DERIVED_OUTPUTS_RESTORED', protected_unchanged=True,
                before_logical_bytes=sum(row['bytes'] for row in before), after_logical_bytes=sum(row['bytes'] for row in sources),
                net_target_logical_decrease_bytes=sum(row['bytes'] for row in before) - sum(row['bytes'] for row in sources),
                measured_volume_free_space_change=False, temporary_files_remaining=sum(path.exists() for path in temporary))
        except BaseException as error:
            receipt.update(status='FAIL_PARTIAL_OR_NOT_RESTORED', error=repr(error)); raise
        finally:
            receipt['forbidden_attempts'] = denied; emit()
    print(json.dumps(dict(status=receipt['status'], restored=len(receipt['restorations']), logical_decrease_bytes=receipt['net_target_logical_decrease_bytes'], receipt=ref(OUTPUT))))


if __name__ == '__main__':
    main()
