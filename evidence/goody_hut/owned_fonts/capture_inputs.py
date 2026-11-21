"""Capture only the selected current font inputs in a reusable owned cache."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import sys
import zipfile

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
PRIOR = STAGE.parent / 'shared_fonts'
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
PROFILE = PROJECT / 'Source/Assets/UI/font_input_profile.json'
BACKUP = PRIOR / 'font_cache_sources_before.zip'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def ref(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path, 'Non-canonical path')
    a = path.stat()
    require(path.is_file() and not a.st_file_attributes & 0x400, 'Non-ordinary input')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    b = path.stat()
    require((a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns) ==
            (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns), 'Input changed while hashing')
    return dict(path=str(path), bytes=b.st_size, sha256=digest)


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    require(sys.dont_write_bytecode and not sys.flags.optimize, 'Use unoptimized Python -B')
    output = STAGE / 'capture_result.json'
    require(not output.exists() and not (STAGE / 'capture_started.json').exists(), 'Single-use capture')
    require(ref(BACKUP)['sha256'] == 'fe7e887e352644f5a1327eb314310d2c184f35f233103b8fa069fdff7b84009b', 'Source backup changed')
    with zipfile.ZipFile(BACKUP) as archive:
        helper = archive.read('tools/ui_font_profile.py')
        old_profile = archive.read('Source/Assets/UI/font_input_profile.json')
    require(PROFILE.read_bytes() == old_profile and PROFILE.stat().st_nlink == 1,
            'Current profile is not the backed-up source')
    profile_before = ref(PROFILE)
    sys.path.insert(0, str(PROJECT / 'tools'))
    namespace = {'__file__': str(PROJECT / 'tools/ui_font_profile.py'), '__name__': 'sealed_font_capture'}
    exec(compile(helper, namespace['__file__'], 'exec'), namespace)
    write(STAGE / 'capture_started.json', dict(utc=datetime.now(timezone.utc).isoformat(),
          script=ref(__file__), backup=ref(BACKUP), profile_before=profile_before))
    original = namespace['capture_profile'](GAME)
    originals = namespace['verify_profile_inputs'](original, GAME)
    require(len(originals) == 15, 'Selected font input set changed')
    inventory = sorted((str(Path(row['path']).relative_to(GAME)).replace('\\', '/'), row['bytes'], row['sha256']) for row in originals)
    content_id = hashlib.sha256(json.dumps(inventory, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
    cache_parent = PROJECT / 'Build/SharedUiFontInputs'
    cache_parent.mkdir(exist_ok=True)
    require(cache_parent.resolve(strict=True) == cache_parent and not cache_parent.stat().st_file_attributes & 0x400,
            'Cache parent is not ordinary')
    cache = cache_parent / content_id
    cache.mkdir(exist_ok=True)
    require(cache.resolve(strict=True) == cache and not cache.stat().st_file_attributes & 0x400, 'Cache root is not ordinary')
    copies, reused = [], []
    for source in originals:
        src = Path(source['path'])
        target = cache / src.relative_to(GAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        require(target.parent.resolve(strict=True) == target.parent, 'Cache parent changed')
        require(ref(src) == source, 'Installed source changed before capture')
        if target.exists():
            actual = ref(target)
            require(all(actual[key] == source[key] for key in ('bytes', 'sha256')), 'Existing content-addressed input differs')
            reused.append(actual)
        else:
            with src.open('rb') as incoming, target.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            actual = ref(target)
            require(all(actual[key] == source[key] for key in ('bytes', 'sha256')), 'Captured font bytes differ')
            copies.append(actual)
        require(ref(src) == source, 'Installed source changed during capture')
        require((src.stat().st_dev, src.stat().st_ino) != (target.stat().st_dev, target.stat().st_ino),
                'Owned cache aliases a mutable installed input')
    require(namespace['verify_profile_inputs'](original, GAME) == originals, 'Installed input changed during capture')
    owned = namespace['capture_profile'](cache)
    owned_rows = namespace['verify_profile_inputs'](owned, cache)
    require(sorted((str(Path(row['path']).relative_to(cache)).replace('\\', '/'), row['bytes'], row['sha256']) for row in owned_rows) == inventory,
            'Owned font profile is not byte-identical to the captured sources')
    require({name: row['glyph_count'] for name, row in original['fonts'].items()} ==
            {name: row['glyph_count'] for name, row in owned['fonts'].items()}, 'Capture lost glyphs')
    temp = PROFILE.with_suffix('.json.capture.tmp')
    require(not temp.exists() and ref(PROFILE) == profile_before, 'Profile changed before publication')
    write(temp, owned)
    os.replace(temp, PROFILE)
    result = dict(schema='zerosis.ui.owned_font_inputs_capture.v1', status='PASS', utc=datetime.now(timezone.utc).isoformat(),
          script=ref(__file__), backup=ref(BACKUP), profile_before=profile_before, profile=ref(PROFILE),
          content_id=content_id, cache_root=str(cache), original_profile=original, original_inputs=originals,
          owned_profile=owned, owned_inputs=owned_rows, copied_inputs=copies, reused_inputs=reused,
          selected_files=len(originals), glyph_counts={name: row['glyph_count'] for name, row in owned['fonts'].items()},
          source_and_cache_byte_identical=True, source_inputs_unchanged=True, source_file_hardlinks_created=0,
          original_game_files_modified=False, retail_user_state_accessed=False, game_processes_queried=False,
          host_gamecore_hwnd_executed=False, default_promoted=False, full_engine_goal_complete=False)
    write(output, result)
    print(json.dumps(dict(status=result['status'], content_id=content_id, copied=len(copies), reused=len(reused),
          copied_bytes=sum(row['bytes'] for row in copies), glyph_counts=result['glyph_counts'], receipt=ref(output))))


if __name__ == '__main__':
    main()
