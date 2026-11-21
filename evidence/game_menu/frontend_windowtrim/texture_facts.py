"""File-only facts about the WindowTrim textures behind the four front-end Image candidates.

Reads the pinned V3 front-end manifest, re-reads each FPK entry by offset with SHA checks and decodes it
with the project's lossless FTXT decoder. Nothing is executed; no game, Host or GPU process starts.
usage: python -B -X utf8 texture_facts.py
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import civ5_ui_assets as ui

MANIFEST = PROJECT / 'evidence/game_menu/replay_calendar_legend/legend/assets_v3.json'
MANIFEST_SHA = 'eb5408e1aeb55ed8469c2fb313f18beb82eb8bab3c2cc9456f60c3b7a1a3d9a1'
XML_WIDTH, XML_HEIGHT = 82, 396


def ref(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def read(source):
    with open(source['pack_path'], 'rb') as stream:
        stream.seek(source['offset'])
        raw = stream.read(source['bytes'])
    assert hashlib.sha256(raw).hexdigest() == source['sha256'], source['entry']
    return raw


def entry(pack, name):
    fpk = ui.Fpk(pack)
    raw, record = fpk.read(name)
    index_name = name[:-4] + '-index.dds'
    index = fpk.read(index_name) if index_name.casefold() in fpk.entries else (None, None)
    return raw, record, index[0], index[1]


def facts(raw, index):
    decoded, conversion = ui.decode_dds(raw, index)
    width, height = conversion['width'], conversion['height']
    pixels = decoded[128:]

    def alpha(x, y):
        return pixels[(y * width + x) * 4 + 3]

    opaque_beyond = sum(1 for x in range(min(XML_WIDTH, width), width) for y in range(height) if alpha(x, y))
    total = sum(1 for x in range(width) for y in range(height) if alpha(x, y))
    edge_rows = {str(y): sum(1 for x in range(width) if alpha(x, y)) for y in (0, 1, height - 2, height - 1)}
    return dict(width=width, height=height, conversion=conversion, opaque_texels=total,
                opaque_texels_in_columns_not_drawn=opaque_beyond, opaque_texels_per_edge_row=edge_rows,
                drawn_rows_beyond_texture=max(0, XML_HEIGHT - height),
                drawn_columns=min(XML_WIDTH, width), texture_columns_not_drawn=max(0, width - XML_WIDTH))


def main():
    manifest_ref = ref(MANIFEST)
    assert manifest_ref['sha256'] == MANIFEST_SHA
    manifest = json.loads(MANIFEST.read_text('utf8'))
    textures = {row['basename']: row for row in manifest['active_skin']['textures']}
    candidates = []
    for row in manifest['original_image_size_candidates']:
        candidates.append(dict(key=row['key'], texture=row['texture'], source_attributes=row['source_attributes'],
                               target_bounds=row['target_bounds'], current_policy=row['policy'],
                               current_transform=row['transform']))
    result = {}
    for name in ('windowtrimleft.dds', 'windowtrimright.dds'):
        active = textures[name]
        layers = []
        for candidate in active['candidates']:
            raw, record, index, index_record = entry(candidate['pack']['path'], candidate['entry'])
            try:
                value = facts(raw, index)
            except Exception as error:  # older layers may use another wrapper; record, do not guess
                value = dict(decode_error=str(error))
            layers.append(dict(layer=candidate['layer'], entry=record, index_entry=index_record, **value))
        active_facts = facts(read(active['source']), read(active['index_source']))
        result[name] = dict(active_layer=active['layer'], active_source=active['source'], active=active_facts, layers=layers)
    report = dict(schema='zerosis.frontend_windowtrim.texture_facts.v1', manifest=manifest_ref,
                  candidates=candidates, textures=result, xml_size=[XML_WIDTH, XML_HEIGHT],
                  native_execution=False, host_or_game_executed=False)
    output = STAGE / 'texture_facts.json'
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, indent=1)
        stream.write('\n')
    summary = {name: dict(active=value['active_layer'], size=[value['active']['width'], value['active']['height']],
                          hidden_opaque=value['active']['opaque_texels_in_columns_not_drawn'],
                          layers=[(l['layer'], l.get('width'), l.get('height'), l.get('decode_error')) for l in value['layers']])
               for name, value in result.items()}
    print(json.dumps(dict(status='PASS_WINDOWTRIM_TEXTURE_FACTS', candidates=len(candidates), summary=summary)))


if __name__ == '__main__':
    main()
