"""Read/freeze exactly the five approved menu DDS entries and needed indices."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
import civ5_ui_assets as assets

SELECTED = ('Corner16.dds', 'Grid9Frame27Square.dds', 'Grid9Frame27SquareBlack.dds', 'Slider32.dds', 'SliderBackH.dds')
RAW = PROJECT / 'Source/Assets/UI/Assets/UI/Art/Controls/9 Grids'
OUTPUT = PROJECT / 'Source/Assets/UI/MenuSuiteControlTextures'
RECEIPT = STAGE / 'texture_reuse.json'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    path = Path(path).absolute()
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse texture input/output path')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Texture artifact is not a regular file')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Texture artifact changed during hashing')
    return dict(path=str(path), bytes=before.st_size, sha256=sha, file_identity=[before.st_dev, before.st_ino],
                mtime_ns=before.st_mtime_ns, file_attributes=getattr(before, 'st_file_attributes', 0))


def main():
    require(__debug__ and sys.dont_write_bytecode and not RECEIPT.exists(), 'Inspect a previous one-use texture freeze instead of replaying it')
    baseline_path = PROJECT / 'Build/UiWindowHost/20261026T133507Z_ea39cdb67229/frozen/ui_assets/prepared.json'
    report = json.loads((PROJECT / 'evidence/ui_window_host/20261026T133507Z_ea39cdb67229/build_result.json').read_bytes())
    baseline_path = Path(report['ui_assets']['path'])
    require(artifact(baseline_path)['sha256'] == report['ui_assets']['sha256'], 'Retained preparation identity differs')
    prepared = json.loads(baseline_path.read_bytes())
    pack_rows = prepared['game_menu_control_pack_sources']
    expected = {Path(row['path']).name.casefold(): row for row in pack_rows}
    packs, source_before = [], []
    for name in assets.PACK_POLICY:
        require(name.casefold() in expected, 'Unregistered original menu texture pack')
        row = expected[name.casefold()]
        actual = artifact(row['path'])
        require(actual['sha256'] == row['sha256'], 'Original texture pack differs from the attested baseline')
        source_before.append(actual)
        packs.append(assets.Fpk(row['path']))
    targets = {RAW / name for name in SELECTED} | {OUTPUT / name for name in SELECTED}
    targets |= {RAW / (name[:-4] + '-index.dds') for name in SELECTED}
    targets.add(RECEIPT)
    parent_dirs = {directory for target in targets for directory in target.parents if directory.is_relative_to(PROJECT / 'Source/Assets/UI')}
    created, reused, denied = [], [], []
    def audit(event, values):
        if event.startswith(('subprocess.', 'ctypes.', 'socket.', 'urllib.', 'http.client.', 'sqlite3.', 'winreg.', 'os.exec', 'os.spawn')) or event in (
                'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.fork', 'os.kill', 'os.killpg',
                'os.remove', 'os.rmdir', 'os.rename', 'os.replace', 'os.symlink', 'os.link', 'os.truncate', 'os.utime'):
            denied.append(event)
            raise PermissionError('File-only selected texture freeze rejects ' + event)
        if event == 'open' and values and isinstance(values[0], (str, bytes, os.PathLike)):
            path, _, flags = values
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                require(Path(os.fsdecode(path)).absolute() in targets and not os.path.lexists(path), 'Texture write escaped an exact fresh target')
        elif event == 'os.mkdir':
            require(Path(values[0]).absolute() in parent_dirs, 'Texture directory creation escaped exact target ancestors')
        elif event == 'os.chmod':
            require(str(Path(values[0]).absolute()) in created, 'Only a new owned texture may become readonly')
    sys.addaudithook(audit)
    def retain(path, raw):
        expected_hash = hashlib.sha256(raw).hexdigest()
        if path.exists():
            row = artifact(path)
            require((row['bytes'], row['sha256']) == (len(raw), expected_hash), 'Existing selected texture has different bytes')
            reused.append(str(path))
            return row
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
        created.append(str(path))
        os.chmod(path, stat.S_IREAD)
        row = artifact(path)
        require((row['bytes'], row['sha256']) == (len(raw), expected_hash), 'Selected texture freeze failed exact readback')
        return row
    records = []
    for name in SELECTED:
        matches = [pack for pack in packs if name.casefold() in pack.entries]
        require(matches, 'The exact selected DDS is absent from registered packs: ' + name)
        selected = matches[0]
        raw, origin = selected.read(name)
        index_name = name[:-4] + '-index.dds'
        tag = raw[116:124].split(b'\0', 1)[0]
        private = raw[32:76].split(b'\0', 1)[0] in (b'FTXTInterface', b'FTXTInterface Scalable') and tag.startswith(b'BC0') and len(tag) == 5
        index, index_origin = selected.read(index_name) if private else (None, None)
        normalized, conversion = assets.decode_dds(raw, index)
        frozen_source = retain(RAW / name, raw)
        frozen_index = retain(RAW / index_name, index) if index is not None else None
        output = frozen_source if normalized == raw else retain(OUTPUT / name, normalized)
        records.append(dict(requested_name='Assets/UI/Art/Controls/9 Grids/' + name, basename=name.casefold(),
            source=origin, index_source=index_origin, candidate_sources=[str(pack.path) for pack in matches],
            frozen_source=frozen_source, frozen_index=frozen_index, conversion=conversion, output=output,
            candidate_filename_policy='EXACT_APPROVED_FIVE_ORIGINAL_MENU_TEXTURES_SHARED_SOURCE_V1'))
    source_after = [artifact(row['path']) for row in source_before]
    require(source_after == source_before and not denied, 'An original pack changed or a native operation was attempted')
    result = dict(schema='zerosis.menu_suite_ui.selected_textures.v1', status='PASS_EXACT_FIVE_MENU_TEXTURES_FROZEN_FILE_ONLY',
        producer=artifact(Path(__file__).absolute()), baseline_prepared=artifact(baseline_path), exact_requested_names=list(SELECTED),
        records=records, original_packs_before=source_before, original_packs_after=source_after,
        created_files=[artifact(path) for path in created], reused_files=reused, originals_read_only=True,
        logical_bytes_created=sum(Path(path).stat().st_size for path in created), full_pack_copied=False,
        font_or_audio_inputs_touched=False, native_execution=False, host_sdk_clr_hwnd_gpu_game_or_pil_loaded=False,
        renderer_or_original_ui_acceptance=False, denied_operations=[])
    with RECEIPT.open('xb') as stream:
        stream.write(json.dumps(result, indent=2).encode('ascii') + b'\n')
    print(json.dumps(dict(status=result['status'], files_created=len(created), logical_bytes_created=result['logical_bytes_created'],
                          selected_original_dds=5, paired_indices=sum(row['frozen_index'] is not None for row in records), native_execution=False)))


if __name__ == '__main__':
    main()
