"""Read-only source sizing and lookup for the original terrain package."""
import csv
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
from civ5_ui_assets import Fpk

def main():
    inventory=json.loads((PROJECT/'evidence/world_terrain_original/asset_inventory.json').read_text('utf8'))
    game=Path(inventory['game_root'])
    rows=list(csv.DictReader(io.StringIO(inventory['definitions']['Assets/DLC/Shared/Terrain/TerrainDef.csv']['text'])))
    needed={row[field].lower() for row in rows for field in ('Diffuse','Heightmap','Specmap') if row[field]!='NULL'}
    sources={};errors=[];packs=[]
    for path in sorted(game.rglob('*.fpk')):
        try:pack=Fpk(path)
        except (OSError,ValueError) as ex:
            errors.append(dict(path=str(path),error=str(ex)));continue
        packs.append(str(path))
        for name in needed&pack.entries.keys():
            entry=pack.entries[name]
            sources.setdefault(name,[]).append(dict(pack=str(path),entry=entry.name,bytes=entry.size))
    report=dict(schema='zerosis.original_terrain.phase1.asset_source_lookup.v1',game_root=str(game),
        rows=len(rows),expanded_materials=sum(3 if row['Projection(0=horizontal 1=vertical)']=='1' else 1 for row in rows),
        unique_texture_names=len(needed),sources=sources,missing=sorted(needed-sources.keys()),scanned_packs=len(packs),errors=errors,
        existing_v1=next((str(path) for path in (PROJECT/'Build/TerrainAssets').glob('*/terrain-assets.manifest.json')),None),
        no_game_or_native_execution=True)
    output=STAGE/'source_lookup.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({key:report[key] for key in ('rows','expanded_materials','unique_texture_names','missing','scanned_packs','errors')}))

if __name__=='__main__':main()
