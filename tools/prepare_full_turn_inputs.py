"""Assemble the ten headless V4 inputs from read-only local files in a private directory."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3

from benchmark_bnw_turns import MODULES, DATA, require, save_json
from collect_baseline import PROJECT, digest
from prepare_host_audio_catalog import NAMES, encode as encode_audio
from prepare_host_script_catalog import LAYERS, encode as encode_scripts


def prepare(game, cache, module_roots, dest, golden_age=False):
    dest.mkdir(parents=True, exist_ok=True)
    origins = {}
    def copy(source, name):
        sha = digest(source)
        target = dest/name
        if target.exists():
            require(digest(target) == sha, f'Different existing input: {target}; select a fresh output directory')
        else:
            shutil.copyfile(source, target)
        require(digest(target) == sha == digest(source), 'Source changed during copy: ' + str(source))
        origins[name] = {'path': str(source), 'sha256': sha}
    for name in MODULES:
        for directory in module_roots:
            if (directory/name).is_file():
                copy(directory/name, name)
                break
    for name, target in [('Civ5DebugDatabase.db', 'rules.db'), ('Localization-Merged.db', 'localization.db')]:
        db = cache/name
        if db.is_file():
            for suffix in ('-wal', '-journal'):
                journal = Path(str(db)+suffix)
                require(not journal.exists() or journal.stat().st_size == 0, 'Database has a live journal: '+str(db))
            copy(db, target)
    icu = game/'Locale/icudt44l.dat'
    if icu.is_file():
        copy(icu, 'icudt44l.dat')
    audio = [game/'Assets/Sounds/XML'/name for name in NAMES]
    if all(p.is_file() for p in audio):
        audio_hashes = {str(p): digest(p) for p in audio}
        payload, _ = encode_audio(audio)
        require(audio_hashes == {str(p): digest(p) for p in audio}, 'Installed audio sources changed')
        publish_catalog(dest/'audio-catalog.bin', payload)
        origins['audio-catalog.bin'] = audio_hashes
    rows = []
    for priority, (directory, virtual) in enumerate(LAYERS):
        files = sorted((game/directory).glob('*.lua'))
        if not files:
            rows = []
            break
        for p in files:
            rows.append(dict(priority=priority, virtual_path=virtual+'/'+p.name.lower(),
                             origin=p.relative_to(game).as_posix(), snapshot={'path':str(p),'sha256':digest(p)}))
    if rows:
        if golden_age:
            p=game/'Assets/UI/InGame/Popups/GoldenAgePopup.lua'
            sha=digest(p)
            require(sha=='611ccc0d0e7b25d4b679438cfa6cd7b935fe666de79cb98f7adf8a2a6048c1f7',
                    'Installed GoldenAgePopup.lua differs from the supported original')
            rows.append(dict(priority=0, virtual_path='ui/ingame/popups/goldenagepopup.lua',
                             origin=p.relative_to(game).as_posix(),snapshot={'path':str(p),'sha256':sha}))
        payload, _, _ = encode_scripts(rows)
        require(all(digest(Path(r['snapshot']['path'])) == r['snapshot']['sha256'] for r in rows), 'Installed Lua changed')
        publish_catalog(dest/'script-catalog.bin', payload)
        origins['script-catalog.bin'] = [r['snapshot'] for r in rows]
    missing = [name for name in MODULES+DATA if name not in origins]
    hashes = {name: digest(dest/name) for name in origins}
    counts = None
    if 'rules.db' in hashes:
        with sqlite3.connect((dest/'rules.db').as_uri()+'?mode=ro&immutable=1', uri=True) as db:
            counts = list(db.execute('SELECT (SELECT COUNT(*) FROM Civilizations),(SELECT COUNT(*) FROM Units),'
                                     '(SELECT COUNT(*) FROM Buildings)').fetchone())
    if not missing:
        manifest = ('ZEROSIS_HOST_BUNDLE_V4\n'+''.join(f'{n}|{hashes[n]}\n' for n in MODULES+DATA)).encode('ascii')
        publish_catalog(dest/'bundle.manifest', manifest)
    report = dict(status='MISSING_INPUTS' if missing else 'PRIVATE_INPUTS_PREPARED', missing=missing,
                  files=hashes, sources=origins, rules_counts=counts,
                  historical_rule_counts=[45,148,140], gamecore_loaded=False)
    save_json(dest/'input_sources.json', report)
    return report


def publish_catalog(target, data):
    if target.is_file():
        require(target.read_bytes() == data, 'Different existing input: '+str(target))
    else:
        with target.open('xb') as stream:
            stream.write(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--modules', action='append', type=Path, default=[])
    parser.add_argument('--output', type=Path, default=PROJECT/'Build/FullTurnBenchmark/inputs')
    parser.add_argument('--golden-age', action='store_true', help='Include the stock informational popup and its Escape handler')
    args = parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((PROJECT/'Build/FullTurnBenchmark').resolve()):
        parser.error('Select a private FullTurnBenchmark build directory')
    result = prepare(args.game.resolve(strict=True), args.cache.resolve(strict=True), args.modules, output, args.golden_age)
    print(json.dumps({k:result[k] for k in ('status','missing','rules_counts','files')}))
    raise SystemExit(2 if result['missing'] else 0)
