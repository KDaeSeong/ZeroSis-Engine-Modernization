"""Summarise pinned coast styles and character points without extracting assets."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT/'tools'))
from civ5_ui_assets import Fpk


def main():
    inventory = json.loads((PROJECT/'evidence/world_terrain_original/asset_inventory.json').read_text('utf8'))
    relative = 'Resource/Common/TerrainModels.fpk'
    pack_path = Path(inventory['game_root'])/relative
    expected_sha = inventory['packs'][relative]['sha256']
    digest = lambda: hashlib.file_digest(pack_path.open('rb'), 'sha256').hexdigest()
    assert digest() == expected_sha
    pack = Fpk(pack_path)
    raw, style_meta = pack.read('coaststyles.xml')
    xml = ET.fromstring(raw.decode('utf-8-sig'))
    profiles = []
    for index, member in enumerate(xml.find('SplineCharacterList')):
        name = member.attrib['Filename'].lower()
        data, meta = pack.read(name)
        points = [json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line.strip()]
        assert points and len(points) <= 4096
        assert all(isinstance(point,list) and len(point)==3 and all(isinstance(x,(int,float)) for x in point) for point in points)
        profiles.append(dict(index=index, member=meta, point_count=len(points),
            minimum=[min(point[axis] for point in points) for axis in range(3)],
            maximum=[max(point[axis] for point in points) for axis in range(3)],
            first=points[0], last=points[-1], descending_x=all(a[0]>b[0] for a,b in zip(points,points[1:])),
            all_z_zero=all(point[2]==0 for point in points)))
    styles = []
    for style in xml.find('CoastStyleList'):
        rows = {child.tag:child.attrib for child in style}
        for key in ('HighBeach','LowBeach','Waterline'):
            assert int(rows[key]['Character']) in (*range(len(profiles)),65535)
        styles.append(dict(name=style.attrib['type'], parameters=rows))
    assert len(profiles)==9 and len(styles)==13
    assert digest()==expected_sha
    result=dict(schema='zerosis.original_water.phase3.coast_text_contract.v1',
        status='PASS_PINNED_COAST_TEXT_VALUES_ONLY', pack=dict(path=str(pack_path),sha256=expected_sha),
        coaststyles=style_meta, profiles=profiles, styles=styles,
        confirmed=['Character indices are declared by the listed filename order.',
                   'There are 9 character files and 13 styles; every character file is a 100-point three-coordinate array.',
                   'Style heights, offsets, smoothing amounts and TerrainType numbers below are exact file values, not chosen calibration.'],
        unverified=['The original runtime loader application, spline interpolation/periodicity, high/low-side sign, character length units and world-scale mapping are not traced here.',
                    'These text coordinates cannot by themselves prove the water-plane height constant cb1[12].x or a current-engine elevation/width.',
                    'TerrainType=5 is a coast-style file value; its relationship to the TerrainDef row-index rule must not be assumed from the number alone.',
                    '65535 is preserved as the file sentinel; its exact runtime branch meaning is not established by this text-only check.'],
        extracted_asset_bytes_written=0, source_or_game_files_modified=False,
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    assert all(row['point_count']==100 for row in profiles)
    with (STAGE/'coast_text_contract.json').open('x',encoding='utf8') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'],profiles=len(profiles),styles=len(styles),
                         points=sum(row['point_count'] for row in profiles),asset_bytes_written=0)))


if __name__=='__main__':
    main()
