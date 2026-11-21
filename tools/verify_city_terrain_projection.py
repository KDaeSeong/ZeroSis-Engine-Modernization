"""Check retained CityView anchor/input geometry against its displayed terrain frame."""
from pathlib import Path
import hashlib
import json
import re
import sys

from ui_pixel_scene import city_view_raster_projection


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nodes(node):
    yield node
    for child in node['children']:
        yield from nodes(child)


def verify(path):
    result = json.loads(path.read_text(encoding='utf8'))
    assert result['status'].endswith('_PASS') and not result['failures']
    stdout = Path(result['stdout']['path'])
    assert digest(stdout) == result['stdout']['sha256']
    native_log = stdout.read_text(encoding='utf8')
    cancelled = [tuple(map(int, match)) for match in
                 re.findall(r'^INTERACTIVE_PREPARE_CLOSE_RETAINED=(\d+)\|(\d+)$', native_log, re.M)]
    records = {Path(row['path']): row['sha256'] for row in result['generated_files']}
    scenes = {}
    snapshots = []
    for file, expected in records.items():
        if re.fullmatch(r'play-scene-\d+\.json', file.name):
            assert digest(file) == expected
            scene = json.loads(file.read_text(encoding='utf8'))
            scenes[scene['generation']] = scene
        elif re.fullmatch(r'play-ui-\d+\.json', file.name):
            assert digest(file) == expected
            snapshot = json.loads(file.read_text(encoding='utf8'))
            if snapshot.get('popupKind') == 'CityView':
                snapshots.append((file, snapshot))
    checks = []
    unpublished = []
    for file, snapshot in snapshots:
        projection = snapshot['cityView']['projection']
        city_view_raster_projection(projection)
        if projection['frameGeneration'] not in scenes:
            sequence = int(re.fullmatch(r'play-ui-(\d+)\.json', file.name)[1])
            # A WM_CLOSE during packet preparation intentionally retains the
            # previous frame. Its completed backdrop is never displayed.
            matches = [(request, retained) for request, retained in cancelled
                       if sequence in (request, request-1) and
                       projection['frameGeneration'] == retained+1 and retained == max(scenes)]
            assert len(matches) == 1
            if sequence != matches[0][0]:
                assert re.search(r'^INTERACTIVE_CITY_BACKDROP=' + str(sequence) + r'\|', native_log, re.M)
            unpublished.append({'snapshot': str(file), 'sha256': records[file],
                                'reason': 'native close retained the preceding displayed frame'})
            continue
        scene = scenes[projection['frameGeneration']]
        assert scene['pixelHitCount'] == 0 and scene['pixelHitKeys'] == [] and scene['pixelHitFile'] == ''
        visible = {row[0] for row in scene['plots'] if row[3] and row[4]}
        assert set(map(int, projection['plots'])) <= visible
        tree = list(nodes(snapshot['tree']))
        by_key = {node['key']: node for node in tree}
        anchors = 0
        for node in tree:
            if node['kind'] != 'WorldAnchor' or 'worldPosition' not in node:
                continue
            grid = node['worldGrid']  # Must survive the stock FLuaVector reload and VecAdd.
            index = grid['y'] * projection['gridWidth'] + grid['x']
            row = projection['plots'].get(str(index))
            visible_anchor = row is not None and row['anchorVisible']
            x = row['centerX'] if visible_anchor else -1000000
            y = row['centerY'] if visible_anchor else -1000000
            expected = {'x': x + grid['offsetX'], 'y': y + grid['offsetY'], 'z': grid['offsetZ']}
            assert node['worldPosition'] == expected
            assert abs(node['x'] - expected['x']) < 1e-6
            assert abs(node['y'] - (expected['y'] - expected['z'])) < 1e-6
            anchors += 1
        for target in snapshot['inputTargets']:
            node = by_key[target['key']]
            assert target['bounds'] == {key: node[key] for key in ('x', 'y', 'width', 'height')}
        checks.append({'snapshot': str(file), 'sha256': records[file], 'generation': scene['generation'],
                       'world_anchors': anchors, 'native_targets': len(snapshot['inputTargets'])})
    assert snapshots and sum(row['world_anchors'] for row in checks) > 0
    return {'status': 'PASS_CITY_TERRAIN_ANCHOR_AND_NATIVE_INPUT_PROJECTION',
            'source_result': {'path': str(path), 'sha256': digest(path)}, 'checks': checks,
            'unpublished_snapshots': unpublished,
            'retail_projection_equivalence_verified': False, 'human_play_verified': False}


if __name__ == '__main__':
    source = Path(sys.argv[1]).resolve(strict=True)
    report = verify(source)
    output = source.parent / 'city_terrain_projection_review.json'
    assert not output.exists(), 'Refusing to overwrite an earlier projection review'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'report': str(output), 'sha256': digest(output)}))
