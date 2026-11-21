"""Read-only details of selected retail terrain/fog assets: DDS headers and small text definitions.

Member bytes are read into memory only; nothing is written to the game install or extracted to disk.
usage: python -B -X utf8 asset_details.py OUT.json
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from civ5_ui_assets import Fpk

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
DDS = {
    'Resource/DX9/EffectTextures.fpk': ['fogcloudtile_dif_01.dds', 'fogcloudtile_dif_02.dds', 'fogcloudtile_dif_03.dds', 'fx_fog_dif.dds'],
    'Resource/DX9/MiscTextures.fpk': ['fogramp.dds', 'tf_blend.dds', 'hexgrid.dds', 'hex_contour1.dds', 'hex_contour2.dds',
                                      'minimapfog.dds', 'fx_fog_test_mask.dds'],
    'Resource/DX9/TerrainTextures.fpk': ['hexgridid.dds', 'euro_grassland_d.dds', 'euro_grassland_h.dds', 'euro_plain_d.dds',
                                         'euro_plain_h.dds', 'euro_mountain_base_h.dds', 'sunlight_europe_terrain.dds',
                                         'shadowlight_europe_terrain.dds', 'waterdepthcolor.dds', 'waterbumps.dds',
                                         'river_alpha.dds', 'forest_europe.dds', 'forest_overlay_europe.dds', 'forest_tile1.dds'],
}
TEXT = {
    'Resource/Common/MiscData.fpk': ['fogcolor.csv', 'hexgrid.xml'],
    'Resource/Common/TerrainModels.fpk': ['forests.xml', 'coaststyles.xml', 'icesettings.xml', 'terraindef.csv'],
}
FOURCC = {b'DXT1': 'BC1', b'DXT3': 'BC2', b'DXT5': 'BC3', b'ATI1': 'BC4', b'ATI2': 'BC5', b'BC4U': 'BC4', b'BC5U': 'BC5'}


def dds_header(data: bytes) -> dict:
    if data[:4] != b'DDS ' or len(data) < 128:
        return dict(valid=False)
    w = struct.unpack_from('<32I', data, 0)
    flags, height, width, depth, mips = w[2], w[3], w[4], w[6], w[7]
    pf_flags, fourcc, bits = w[20], data[84:88], w[22]
    masks = w[23:27]
    fmt = FOURCC.get(fourcc) if pf_flags & 4 else None
    if fourcc == b'\x71\x00\x00\x00':
        fmt = 'A16B16G16R16F'
    elif pf_flags & 4 and fourcc == b'\x24\x00\x00\x00':
        fmt = 'A16B16G16R16'
    elif not fmt:
        fmt = f'RGB{bits} masks={[hex(m) for m in masks]} flags={hex(pf_flags)}'
    return dict(valid=True, width=width, height=height, depth=depth, mips=mips, format=fmt,
                cubemap=bool(w[28] & 0x200))


def main(out: Path) -> int:
    report = dict(schema='zerosis.world_terrain_original.asset_details.v1', executed=False, dds={}, text={})
    for relative, names in DDS.items():
        pack = Fpk(GAME / relative)
        for name in names:
            data, meta = pack.read(name)
            report['dds'][name] = dict(pack=relative, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), **dds_header(data))
    for relative, names in TEXT.items():
        pack = Fpk(GAME / relative)
        for name in names:
            data, meta = pack.read(name)
            report['text'][name] = dict(pack=relative, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                        text=data.decode('utf-8-sig', errors='replace')[:20000])
    with out.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, indent=1, ensure_ascii=False)
        stream.write('\n')
    for name, row in report['dds'].items():
        print(name, row.get('width'), row.get('height'), row.get('format'), row.get('mips'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]).absolute()))
