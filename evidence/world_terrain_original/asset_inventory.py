"""Read-only inventory of the retail Civ V terrain, feature and fog-of-war assets.

Only FPK tables (names, sizes, offsets) and small text definitions are read. Nothing in the
game install is written, extracted to the install, executed or loaded as a module.
usage: python -B -X utf8 asset_inventory.py OUT.json
"""
from __future__ import annotations
import collections
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from civ5_ui_assets import Fpk

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
PACKS = ['Resource/DX9/TerrainTextures.fpk', 'Resource/Common/TerrainModels.fpk', 'Resource/Common/FeatureModels.fpk',
         'Resource/DX9/FeatureTextures.fpk', 'Resource/DX9/MiscTextures.fpk', 'Resource/DX9/EffectTextures.fpk',
         'Resource/DX9/StrategicViewTextures.fpk', 'Resource/DX9/DecalTextures.fpk', 'Resource/Common/MiscData.fpk',
         'Resource/Common/EffectData.fpk']
KEYWORDS = re.compile(r'fog|cloud|war|blend|mask|terrain|coast|ocean|water|river|lake|shore|hex|edge|piece|noise|'
                      r'forest|jungle|marsh|tree|hill|mountain|snow|tundra|desert|grass|plain|ice|reef|lut|light', re.I)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def main(out: Path) -> int:
    report = dict(schema='zerosis.world_terrain_original.asset_inventory.v1', game_root=str(GAME), executed=False,
                  method='FPK table parse with the project reader; text definitions read as UTF-8; no member bytes extracted.',
                  packs={}, definitions={})
    for relative in PACKS:
        path = GAME / relative
        pack = Fpk(path)
        names = sorted((entry.name.replace('\\', '/'), entry.size) for entry in pack.entries.values())
        folders = collections.Counter(name.rsplit('/', 1)[0] if '/' in name else '.' for name, _ in names)
        matched = [dict(name=name, bytes=size) for name, size in names if KEYWORDS.search(name)]
        report['packs'][relative] = dict(bytes=path.stat().st_size, sha256=digest(path), entries=len(names),
                                         folders=dict(sorted(folders.items())), matched=matched)
    for relative in ('Assets/DLC/Shared/Terrain/TerrainDef.csv',):
        path = GAME / relative
        report['definitions'][relative] = dict(bytes=path.stat().st_size, sha256=digest(path),
                                               text=path.read_text('utf-8-sig'))
    library = GAME / 'Resource/Common/TerrainPiecesLibrary.fxsb'
    raw = library.read_bytes()
    strings = sorted(set(match.group().decode('ascii') for match in re.finditer(rb'[ -~]{6,}', raw[:4 << 20])))
    report['pieces_library'] = dict(path=str(library), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                    head_hex=raw[:64].hex(), ascii_strings_in_first_4mib=len(strings),
                                    sample_strings=[s for s in strings if KEYWORDS.search(s)][:400])
    with out.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, indent=1, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps({name: dict(entries=value['entries'], matched=len(value['matched'])) for name, value in report['packs'].items()}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).absolute()))
