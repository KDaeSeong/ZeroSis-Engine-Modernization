"""Decode the 10 x 10 pattern cells of every piece in the retail TerrainPiecesLibrary.fxsb (read only).

Cell layout and meaning come from the matcher code (retail_piece_placement_probe.json): u32 terrain mask, u8 continent,
u8 owned, 2 unused bytes; cell (x, y) is stored at x + 10*y from record offset 0x9c.
No game, Host or tool other than Python is run.
usage: python -I piece_cells.py TerrainPiecesLibrary.fxsb OUT.json
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


offset = 4
counts = []
for element in (4, 1, 2):
    count, = struct.unpack_from('<I', raw, offset)
    counts.append(count)
    offset += 4 + count * element
pieces_count, = struct.unpack_from('<I', raw, offset)
D0, SIZE = offset + 4, 0x56c
require(pieces_count == 299 and D0 + pieces_count * SIZE == len(raw), 'piece array')
starts = [struct.unpack_from('<4I', raw, D0 + i * SIZE + 0x3d4) for i in range(pieces_count)]
flat = [v for row in starts for v in row] + [counts[0]]


def kind(name):
    stem = re.sub(r'\.csv$', '', name)
    stem = re.sub(r'^(Wonder_)?(Amer|Asia|Afri|Euro)_', '', stem)
    stem = re.sub(r'^Wonder_', '', stem)
    return re.sub(r'[ _]?\d+(_\d+)?(_H)?$', '', stem).replace(' ', '_').lower().replace('moun', 'mountain').replace('mountaintain', 'mountain')


bit_names = collections.defaultdict(set)
levels = collections.defaultdict(collections.Counter)
continent_bytes = collections.Counter()
rows = []
for index in range(pieces_count):
    record = raw[D0 + index * SIZE:D0 + (index + 1) * SIZE]
    name = record[0x3ea:record.index(b'\0', 0x3ea)].decode('latin1')
    level, flags = struct.unpack_from('<I', record, 0x3c8)[0], struct.unpack_from('<I', record, 0x3d0)[0]
    size = flat[index * 4 + 1] - flat[index * 4]
    require((flags & 1) == (size == 128), 'flag bit 0 marks a 128-pixel piece')
    owned, constraints = [], collections.Counter()
    for cell in range(100):
        mask, continent, own, unused_a, unused_b = struct.unpack_from('<IBBBB', record, 0x9c + 8 * cell)
        require((unused_a, unused_b) == (0x4d, 0), 'unused cell bytes')
        if own:
            require(mask and mask & (mask - 1) == 0, 'an owned cell names exactly one terrain bit')
            owned.append(dict(x=cell % 10, y=cell // 10, bit=mask.bit_length() - 1, continent=continent))
            bit_names[mask.bit_length() - 1].add(kind(name))
            prefix = name.split('_')[1] if name.startswith('Wonder_') else name.split('_')[0]
            continent_bytes[(prefix if prefix in ('Amer', 'Asia', 'Afri', 'Euro') else 'none', continent)] += 1
        elif mask != 0xffffffff or continent:
            require(continent == 0, 'cells that are not owned carry no continent')
            constraints[f'{mask:#010x}'] += 1
    require(owned, 'every piece owns at least one cell')
    require(len({c['bit'] for c in owned}) == 1 and len({c['continent'] for c in owned}) == 1, 'one terrain and continent per piece')
    levels[level][len(owned)] += 1
    rows.append(dict(index=index, csv=name, level=level, image_size=size, owned=owned, neighbour_constraints=dict(constraints)))
names = {bit: sorted(v) for bit, v in sorted(bit_names.items())}
require(names[0] == ['grass'] and names[1] == ['plains'] and names[2] == ['desert'] and names[3] == ['tundra'] and
        names[4] == ['snow'] and names[5] == ['grass_hill'] and names[6] == ['plains_hill'] and names[7] == ['desert_hill'] and
        names[8] == ['tundra_hill'] and names[9] == ['snow_hill'] and names[10] == ['mountain'] and names[13] == ['coast'] and
        names[14] == ['ocean'] and names[20] == ['reef'] and names[26] == ['gibraltar'] and sorted(names) == list(range(27)),
        'terrain bit names')
require(continent_bytes[('Amer', 1)] and continent_bytes[('Asia', 2)] and continent_bytes[('Afri', 3)] and
        continent_bytes[('Euro', 4)] and not any(c not in (0, {'Amer': 1, 'Asia': 2, 'Afri': 3, 'Euro': 4}.get(p, c))
                                                 for (p, c) in continent_bytes if p != 'none'), 'continent byte follows the name')
require(sorted(levels) == [1, 2, 3, 4], 'levels 1-4')
report = dict(schema='zerosis.world_terrain_original.piece_cells.v1',
              file=dict(name='TerrainPiecesLibrary.fxsb', bytes=len(raw), sha256=sha), executed=False,
              cell_layout='record +0x9c + 8*(x + 10*y): u32 terrain mask, u8 continent, u8 owned, 0x4d, 0',
              terrain_bits={str(bit): value for bit, value in names.items()},
              continent_byte={'0': 'any', '1': 'Amer', '2': 'Asia', '3': 'Afri', '4': 'Euro'},
              continent_byte_counts=[dict(name_prefix=p, value=c, owned_cells=n) for (p, c), n in sorted(continent_bytes.items())],
              levels={str(level): dict(pieces=sum(v.values()), owned_cells={str(k): n for k, n in sorted(v.items())})
                      for level, v in sorted(levels.items())},
              flag_bit0='record +0x3d0 bit 0 is set exactly for the 128-pixel pieces',
              piece_rows=rows,
              interpretation=dict(
                  proven=['Each piece owns 1 to 3 cells of one terrain bit and one continent; other cells are wildcards '
                          '(0xffffffff) or masks of allowed neighbours.',
                          'Levels: the matcher runs level 4 first, then 3, 2, 1 (see levels for what each holds).'],
                  not_proven=['Bit names are taken from the piece file names, not from game code.']))
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_PIECE_CELLS', sha256=sha, pieces=pieces_count, out=out)))
