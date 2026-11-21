"""Write the small reader contract and actual DDS header summary; no package is produced."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
import civ5_original_terrain_assets as terrain
from civ5_ui_assets import Fpk

def main():
    inventory=json.loads((PROJECT/'evidence/world_terrain_original/asset_inventory.json').read_text('utf8'))
    game=Path(inventory['game_root']);rows=terrain.parse_csv((game/terrain.CSV_RELATIVE).read_bytes())
    pack=Fpk(game/terrain.PACK_RELATIVE)
    names=sorted({row[role].lower() for row in rows for role in ('diffuse','height','specular') if row[role] is not None})
    textures=[];absent=[]
    for name in names:
        if name not in pack.entries:absent.append(name);continue
        data,source=pack.read(name)
        textures.append(dict(name=name,bytes=len(data),sha256=source['sha256'],**terrain.validate_dds(data,name)))
    layout=dict(schema='zerosis.original_terrain.package_format.v2',endianness='little',padding='none',magic='ZSTERR02',
        header=dict(bytes=24,fields=[['magic','8 raw ASCII bytes'],['version','u32 = 2'],['row_count','u32 1..64'],
            ['texture_count','u32 1..256'],['library_bytes','u32 20..33554432']]),
        terrain_row=dict(bytes=32,layout='<IIIfIIII',fields=['row_index','continent','legacy_id_hex_column','texture_scale_f32',
            'projection_0_or_1','diffuse_texture_index','height_texture_index','specular_texture_index'],
            ordering='TerrainDef source order, zero-based row index',expanded_materials='Projection 0 => one; Projection 1 => three; sum <= 64',
            null_texture_index=terrain.NULL_TEXTURE,declared_missing_texture_index=terrain.MISSING_TEXTURE,
            declared_missing_only=dict(row=8,role='height',original_name='Generic_Gibraltar_H.dds'),
            base_dominance='read from source row and discarded; absent from package and renderer weights'),
        texture_record=dict(fields=[['name_bytes','u32 1..128'],['dds_bytes','u32 128..33554432'],
            ['dds_sha256','32 raw digest bytes'],['name','name_bytes ASCII lowercase, no NUL'],['dds','dds_bytes unchanged original bytes']],
            ordering='unique texture name, sorted casefold; index is zero-based record ordinal'),
        piece_library=dict(fields=[['library_sha256','32 raw digest bytes'],['library','library_bytes unchanged TerrainPiecesLibrary.fxsb bytes']],
            version=20,sha256=terrain.LIBRARY_SHA256,bytes=27595584),
        trailer='none; parser must consume exact file length',max_package_bytes=terrain.MAX_PACKAGE_BYTES,
        expected_original_profile=dict(rows=41,expanded_materials=47,textures=72,missing=absent),dds=textures,
        dds_format_summary={codec:sum(row['format']==codec for row in textures) for codec in sorted({row['format'] for row in textures})},
        actual_payload_bytes=sum(row['bytes'] for row in textures)+27595584,
        whole_package_sha='content-addressed directory and manifest; every DDS and library also have embedded SHA256',
        prepare_api='prepare(game_root: Path, output_root: Path) -> package_path,package_sha256,manifest_path,package_bytes,row_count,expanded_material_count,texture_count,originals_unchanged,reused_existing',
        game_root_read_only=True,native_execution=False)
    with (STAGE/'format.json').open('x',encoding='utf8') as stream:json.dump(layout,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status='PASS_FORMAT_CONTRACT_AND_DDS_HEADERS',dds=len(textures),formats=layout['dds_format_summary'],payload_bytes=layout['actual_payload_bytes'],missing=absent)))

if __name__=='__main__':main()
