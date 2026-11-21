"""Check that the _T1 id values of the terrain pieces are TerrainDef.csv row numbers (0-based, header excluded).

The retail EXE keeps TerrainDef rows in file order and looks the texel id up as a row (retail_terrain_blend_cpu_probe.json).
Here every non-zero id used by a piece is mapped to that row and the row's material type is compared with the piece name.
Read-only; no game, Host or tool other than Python is run.
usage: python -B -X utf8 pieces_id_rows.py
"""
from __future__ import annotations
import collections
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
pieces = json.loads((STAGE / 'pieces_library_format.json').read_text('utf8'))
inventory = json.loads((STAGE / 'asset_inventory.json').read_text('utf8'))
details = json.loads((STAGE / 'asset_details.json').read_text('utf8'))


def table(text):
    return [row for row in csv.reader(io.StringIO(text))][1:]


dlc = [r for r in table(inventory['definitions']['Assets/DLC/Shared/Terrain/TerrainDef.csv']['text']) if r]
fpk = [r for r in table(details['text']['terraindef.csv']['text']) if r]
assert len(dlc) == len(fpk) == 41
same_order = [i for i in range(41) if dlc[i][1] != fpk[i][1]]


def piece_type(name):
    stem = re.sub(r'\.csv$', '', name)
    stem = re.sub(r'^(Wonder_)?(Amer|Asia|Afri|Euro)_', '', stem)
    stem = re.sub(r'^Wonder_', '', stem)
    return re.sub(r'[ _]?\d+(_\d+)?(_H)?$', '', stem).replace(' ', '_').lower()


def material_type(diffuse):
    return re.sub(r'^(Amer|Asia|Afri|Euro|Generic|Worl)_', '', diffuse).replace('_D.dds', '').replace('.dds', '').lower()


EXPECTED = {'grass': {'grassland'}, 'grass_hill': {'grassland'}, 'plains': {'plain'}, 'plains_hill': {'plain', 'grassland'},
            'desert': {'desert'}, 'desert_hill': {'desert', 'plain'}, 'tundra': {'tundra'}, 'tundra_hill': {'tundra_hill', 'grassland'},
            'snow': {'snow'}, 'snow_hill': {'snow', 'grassland'}, 'mountain': {'mountain_base', 'mountain_top'},
            'moun': {'mountain_base', 'mountain_top', 'marsh'}, 'mesa': {'mesa', 'desert'}, 'reef': {'reef', 'shallow_seas'},
            'volcano': {'volcano', 'grassland'}, 'crater': {'crater', 'desert'}}
pairs = collections.Counter()
checked = matched = 0
for piece in pieces['piece_rows']:
    kind = piece_type(piece['csv'])
    for value in piece['id_values']:
        if value == 0:
            continue
        assert value < 41, (piece['csv'], value)
        material = material_type(dlc[value][1])
        pairs[(kind, material)] += 1
        if kind in EXPECTED:
            checked += 1
            matched += material in EXPECTED[kind]
used = sorted({v for p in pieces['piece_rows'] for v in p['id_values']})
checks = dict(
    all_ids_are_rows=max(used) < 41 and min(used) == 0,
    every_piece_uses_zero_outside=all(p['id_values'][0] == 0 for p in pieces['piece_rows']),
    copies_share_row_order=same_order == [0],
    row0_differs=(dlc[0][1], fpk[0][1]) == ('Asia_Tundra_D.dds', 'NULL'),
    examples=(dlc[11][1], dlc[19][1], dlc[27][1], dlc[34][1]) ==
             ('Amer_Grassland_D.dds', 'Asia_Grassland_D.dds', 'Afri_Desert_D.dds', 'Euro_Grassland_D.dds'),
    typed_pieces_match_row_material=checked > 300 and matched == checked)
value = dict(schema='zerosis.world_terrain_original.pieces_id_rows.v1',
             inputs={name: hashlib.sha256((STAGE / name).read_bytes()).hexdigest()
                     for name in ('pieces_library_format.json', 'asset_inventory.json', 'asset_details.json')},
             used_ids=used, rows_differing_between_copies=same_order,
             row0=dict(dlc=dlc[0][1], fpk=fpk[0][1]),
             typed_checks=dict(checked=checked, matched=matched),
             piece_type_to_row_material=[dict(piece=k[0], row_material=k[1], uses=v) for k, v in sorted(pairs.items())],
             checks=checks, status='PASS' if all(checks.values()) else 'FAIL', native_execution=False,
             meaning='Piece _T1 values index TerrainDef rows in file order. Value 0 (outside the hex footprint) is row 0, '
                     'which is Asia_Tundra in the DLC copy and NULL in the TerrainModels.fpk copy.')
out = STAGE / 'pieces_id_rows.json'
if out.exists():
    out.unlink()
with out.open('x', encoding='utf8', newline='\n') as stream:
    json.dump(value, stream, indent=1, ensure_ascii=False)
    stream.write('\n')
print(json.dumps(dict(status=value['status'], checks=checks, typed=value['typed_checks'])))
