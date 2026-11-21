"""Decode the retail Resource/Common/TerrainPiecesLibrary.fxsb (read only) and record its format and contents summary.

Layout (reader at EXE 0x5fca30, see retail_terrain_pipeline_probe.json): u32 version 20, then four counted arrays:
A = u32 row offsets, B = u8 run-length stream, C = u16 run-length stream, D = 0x56c-byte piece records.
No game, Host or tool other than Python is run.
usage: python -I pieces_library_format.py TerrainPiecesLibrary.fxsb OUT.json
"""
import collections, hashlib, json, re, struct, sys

EXPECTED_SHA256 = '86faac1e80634b0031a9df98889682fbc17ddc72341fc68fbf5b33e7ce4c1c7a'
path, out = sys.argv[1], sys.argv[2]
raw = open(path, 'rb').read()
sha = hashlib.sha256(raw).hexdigest()
if sha != EXPECTED_SHA256:
    raise SystemExit('Pieces library differs from the analysed file: ' + sha)


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned pieces library evidence no longer matches: ' + message)


offset = 0
version, = struct.unpack_from('<I', raw, offset)
offset += 4
require(version == 20, 'version 20')
sections = {}
for name, element in (('A_row_offsets_u32', 4), ('B_runs_u8', 1), ('C_runs_u16', 2), ('D_pieces', 0x56c)):
    count, = struct.unpack_from('<I', raw, offset)
    sections[name] = dict(file_offset=offset + 4, count=count, element_bytes=element)
    offset += 4 + count * element
require(offset == len(raw), 'the four arrays end exactly at the end of the file')
A = struct.unpack_from('<%dI' % sections['A_row_offsets_u32']['count'], raw, sections['A_row_offsets_u32']['file_offset'])
b0 = sections['B_runs_u8']['file_offset']
B = raw[b0:b0 + sections['B_runs_u8']['count']]
C = struct.unpack_from('<%dH' % sections['C_runs_u16']['count'], raw, sections['C_runs_u16']['file_offset'])
D0, SIZE, PIECES = sections['D_pieces']['file_offset'], 0x56c, sections['D_pieces']['count']


def text(record, at):
    return record[at:record.index(b'\0', at)].decode('latin1')


IMAGES = ('heightmap', 'id_map', 'height_blend', 'id_blend')
NAME_FIELDS = (0x46a, 0x4aa, 0x4ea, 0x52a)
pieces, starts = [], []
for index in range(PIECES):
    record = raw[D0 + index * SIZE:D0 + (index + 1) * SIZE]
    word = lambda at: struct.unpack_from('<I', record, at)[0]
    require(text(record, 0x3ea) == text(record, 0x42a), 'duplicated CSV name')
    require(word(0x3bc) == index, 'record index field')
    require((word(0x94), word(0x98)) == (word(0x3c0), word(0x3c4)), 'duplicated cell grid size')
    starts.append([word(0x3d4 + 4 * k) for k in range(4)])
    pieces.append(dict(index=index, csv=text(record, 0x3ea), images=[text(record, at) for at in NAME_FIELDS],
                       cells=[word(0x94), word(0x98)], class_field=word(0x3c8)))
flat = [value for row in starts for value in row] + [len(A)]
require(flat == sorted(flat), 'image row tables are stored in piece order')

usage_b = usage_c = 0
values = [collections.Counter() for _ in IMAGES]
for index, piece in enumerate(pieces):
    sizes, id_values = [], set()
    for k in range(4):
        start = starts[index][k]
        size = flat[index * 4 + k + 1] - start
        for row in range(size):
            position, total = A[start + row], 0
            while total < size:
                if k == 0:   # heightmap: (u16 count, u16 value) runs in C
                    count, value = C[position], C[position + 1]
                    usage_c = max(usage_c, position + 2)
                else:        # id / blend maps: (u8 count, u8 value) runs in B
                    count, value = B[position], B[position + 1]
                    usage_b = max(usage_b, position + 2)
                    if k == 1:
                        id_values.add(value)
                values[k][value] += count
                total += count
                position += 2
            require(total == size, f'piece {index} image {k} row {row} run lengths sum to the image width')
        sizes.append(size)
    require(len(set(sizes)) == 1, 'all four images of a piece share one square size')
    piece.update(image_size=sizes[0], id_values=sorted(id_values))
require(usage_b == len(B) and usage_c == len(C), 'the run-length streams are consumed exactly')

csv_names = [p['csv'] for p in pieces]
classes = collections.defaultdict(list)
for p in pieces:
    classes[p['class_field']].append(p['csv'])
require({k: len(v) for k, v in classes.items()} == {1: 70, 2: 69, 3: 104, 4: 56}, 'class field counts')
require(collections.Counter(p['image_size'] for p in pieces) == {128: 148, 512: 151}, 'image sizes')
require(all(p['cells'] == [10, 10] for p in pieces), '10 x 10 cell grid per piece')
require(pieces[0]['csv'] == 'Amer_Grass_1_1.csv' and pieces[0]['images'] == [
    'Amer_Grass_1_1_H.dds', 'Amer_Grass_1_1_T1.dds', 'Amer_Grass_1_1_H_BLEND.dds', 'Amer_Grass_1_1_T_BLEND.dds'], 'first piece')
by_csv = {p['csv']: p for p in pieces}
require(by_csv['Amer_Grass_1_1.csv']['id_values'] == [0, 11] and by_csv['Asia_Grass_1_1.csv']['id_values'] == [0, 19] and
        by_csv['Afri_Desert_1_1.csv']['id_values'] == [0, 27], 'id map examples')
height = values[0]
report = dict(
    schema='zerosis.world_terrain_original.pieces_library_format.v1',
    file=dict(name='TerrainPiecesLibrary.fxsb', bytes=len(raw), sha256=sha), executed=False,
    method='Byte parse of the four counted arrays and full run-length decode of every image; nothing else is run.',
    version=version, sections=sections,
    record_fields={'0x094/0x098 and 0x3c0/0x3c4': 'cell grid width/height (10 x 10 for every piece)',
                   '0x3bc': 'record index', '0x3c8': 'class number 1-4 (meaning not proven; see class_examples)', '0x3d4..0x3e0': 'first row in A of the four images',
                   '0x3ea and 0x42a': 'source CSV name', '0x46a/0x4aa/0x4ea/0x52a': 'names of the _H, _T1, _H_BLEND, _T_BLEND images'},
    image_encoding=dict(
        heightmap='square image; A[start+row] indexes C; each row is (u16 count, u16 value) runs summing to the width',
        id_map_and_blends='square image; A[start+row] indexes B; each row is (u8 count, u8 value) runs summing to the width'),
    pieces=PIECES, image_sizes=dict(collections.Counter(p['image_size'] for p in pieces)),
    class_examples={str(k): dict(count=len(v), first=v[:8]) for k, v in sorted(classes.items())},
    value_summary=dict(
        heightmap=dict(min=min(height), max=max(height), distinct=len(height)),
        id_map=dict(distinct=sorted(values[1]), zero_share=round(values[1][0] / sum(values[1].values()), 4)),
        height_blend=dict(distinct=len(values[2]), zero_share=round(values[2][0] / sum(values[2].values()), 4)),
        id_blend=dict(distinct=len(values[3]), zero_share=round(values[3][0] / sum(values[3].values()), 4))),
    piece_rows=pieces,
    interpretation=dict(
        proven=['The file holds 299 pieces; each has a 10 x 10 cell grid and four square images (128 or 512 px).',
                'Heightmaps are 16-bit, id maps and the two blend maps are 8-bit, all row run-length encoded.',
                'Outside the hex-shaped footprint the id and blend maps are 0 (leading and trailing zero runs).'],
        not_proven=['What the 10 x 10 cell grid entries select, and how pieces are chosen for a map position.',
                    'The meaning of the class field (observed: 1 mostly flat grass/desert, 2 mostly flat plains/tundra, '
                    '3 mostly hills, 4 natural wonders; it is not the continent, every class mixes Amer/Asia/Afri/Euro).',
                    'The meaning of id map values: they are not TerrainDef IDs (Amer_Grass pieces use 11, TerrainDef '
                    'grassland is 2).',
                    'How height_blend and id_blend are combined with the TerrainShaderScreen blend inputs.']))
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_PIECES_LIBRARY_FORMAT', sha256=sha, pieces=PIECES, out=out)))
