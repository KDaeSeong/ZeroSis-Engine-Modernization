"""Select exactly one original BC3 DDS and retain one small SHA-pinned package."""
import hashlib
import json
from pathlib import Path
import struct
import sys
from water_pe_view import PROJECT,STAGE,ref,write_new
sys.path[:0]=[str(PROJECT/'tools')]
from civ5_ui_assets import Fpk,header,decode_dxt5_top_mip
from civ5_original_terrain_assets import validate_dds


def main():
    old=json.loads((PROJECT/'evidence/world_terrain_original/phase8/screen_lighting/screen_contract_pe.json').read_text('utf8'))
    source=Path(old['asset']['pack_path']);before=ref(source)
    assert before['sha256']=='8fb5183a2fe92d8add58d7758a231caafb27a2eb87b1958284eaa7d42a49577b'
    archive=Fpk(source);dds,selected=archive.read('specscreenmap.dds')
    assert selected['sha256']=='6f29e8b9c71a8e7ec4dd2983ac5fd46f45938635ec2bd2d1c113a6f40bc1455f' and len(dds)==1398256
    metadata=validate_dds(dds,'specscreenmap.dds');assert metadata['width']==metadata['height']==1024 and metadata['mips']==11 and metadata['format']=='BC3'
    marker=dds[32:76].split(b'\0')[0];tag=dds[116:124].split(b'\0')[0]
    assert marker==b'FTXTTerrain Heightfield' and tag==b'COLOR'
    # The ordinary terrain DDS validator accepts this tool tag. The existing
    # BC3 decoder checks every top-level block without changing compressed data.
    # There is no BC0NN dictionary/map declaration in this selected DDS.
    decoded,conversion=decode_dxt5_top_mip(dds,header(dds))
    assert len(decoded)==1024*1024*4 and conversion['encoding']=='DXT5_BC3_TOP_MIP_BGRA8'
    payload=b'ZSSCRL01'+struct.pack('<II',1,len(dds))+hashlib.sha256(dds).digest()+dds
    digest=hashlib.sha256(payload).hexdigest();folder=PROJECT/'Build/OriginalScreenLightAssets'/digest
    assert not folder.exists();folder.mkdir(parents=True)
    package=folder/'screen-light-assets.bin'
    with package.open('xb') as stream:stream.write(payload)
    levels=[];cursor=48+128
    for level in range(11):
        side=max(1,1024>>level);pitch=((side+3)//4)*16;count=pitch*((side+3)//4)
        levels.append(dict(level=level,width=side,height=side,offset=cursor,bytes=count,row_pitch=pitch));cursor+=count
    assert cursor==len(payload) and ref(source)==before
    result=dict(schema='zerosis.original_screen_light_assets.v1',status='PASS_SINGLE_ORIGINAL_SPECSCREENMAP_PACKAGE',scope='NoNative0',
        package=ref(package),source_pack=before,source_entry=selected,dds=dict(**metadata,bytes=len(dds),sha256=selected['sha256'],
            marker=marker.decode(),tag=tag.decode(),reserved_metadata_preserved=True,levels=levels),
        source_decoder=ref(PROJECT/'tools/civ5_ui_assets.py'),format_validator=ref(PROJECT/'tools/civ5_original_terrain_assets.py'),
        ftxt_validation=dict(conversion=conversion,bc0_dictionary_or_index_map_declared=False,compressed_mips_reordered=False,top_mip_bgra_sha256=hashlib.sha256(decoded).hexdigest(),
                             decoded_top_mip_retained=False,compressed_payload_unchanged=True),
        resource_contract=dict(original_shader='TerrainShader',original_slot=9,sampler_index=5,filter='LINEAR',address='CLAMP',srv='BC3_UNORM',additional_gamma_decode=False,
                               independent_from_water_raw_reflection=True),
        original_five_asset_packages_modified_or_copied=0,raw_dds_separate_copies=0,native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,source=ref(__file__))
    manifest=folder/'screen-light-assets.manifest.json'
    with manifest.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    output=write_new('water_screen_light_preparation.json',dict(result,manifest=ref(manifest)))
    print(dict(status=result['status'],package=ref(package),output=output))


if __name__=='__main__':main()
