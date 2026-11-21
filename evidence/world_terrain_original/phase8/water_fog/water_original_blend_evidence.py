"""Read-only retail PE/DXBC metadata; no render-state equivalence is inferred."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new

def main():
    root=PROJECT/'evidence/world_terrain_original'
    sources=[root/n for n in ('retail_terrain_pipeline_probe.json','retail_renderer_probe.json','phase5/semantics/lighting_contract.json')]
    before=[ref(p)for p in sources]
    pipeline,registry,contract=[json.loads(p.read_text('utf8'))for p in sources]
    exe=Path(contract['original_exe']['path']);exe_before=ref(exe);raw=exe.read_bytes()
    assert exe_before['sha256']=='b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
    u16=lambda n:struct.unpack_from('<H',raw,n)[0]
    u32=lambda n:struct.unpack_from('<I',raw,n)[0]
    pe=u32(0x3c);assert raw[pe:pe+4]==b'PE\0\0'
    opt=pe+24;assert u16(opt)==0x10b
    base=u32(opt+28);sections=[]
    for i in range(u16(pe+6)):
        at=opt+u16(pe+20)+i*40
        sections.append(dict(name=raw[at:at+8].rstrip(b'\0').decode('ascii'),virtual_size=u32(at+8),rva=u32(at+12),raw_size=u32(at+16),raw_offset=u32(at+20)))
    def locate(va,count):
        rva=va-base
        for s in sections:
            delta=rva-s['rva']
            if 0<=delta and delta+count<=max(s['virtual_size'],s['raw_size']):
                if delta+count>s['raw_size']:return dict(va=f'{va:08x}',section=s['name'],file_backed=False)
                off=s['raw_offset']+delta;assert off+count<=len(raw)
                return dict(va=f'{va:08x}',section=s['name'],file_backed=True,file_offset=off,bytes=count,sha256=hashlib.sha256(raw[off:off+count]).hexdigest())
        return dict(va=f'{va:08x}',file_backed=False,section=None)
    def cstring(va):
        r=locate(va,1);assert r['file_backed'];off=r['file_offset'];end=raw.index(0,off);assert end-off<128
        return raw[off:end].decode('ascii')
    water=pipeline['effect_records']['effects']['0x5b'];assert water['name']=='WaterShader'
    binding=next(r for r in registry['shader_registry']['shaders']if r['name']=='WaterShader')
    table=locate(int(binding['binding_table'],16),len(binding['bindings'])*16);assert table['file_backed']
    names=[cstring(u32(table['file_offset']+16*i))for i in range(len(binding['bindings']))]
    assert names==binding['bindings']
    shaders=[]
    for index,record in enumerate(water['passes']):
        s=record['ps']['sm5'];off=int(s['file_offset'],16);blob=raw[off:off+s['bytes']]
        assert blob[:4]==b'DXBC'and hashlib.sha256(blob).hexdigest()==s['sha256']
        assert struct.unpack_from('<I',blob,24)[0]==len(blob)
        count=struct.unpack_from('<I',blob,28)[0];assert count<=32
        chunks=[]
        for i in range(count):
            at=struct.unpack_from('<I',blob,32+4*i)[0];size=struct.unpack_from('<I',blob,at+4)[0]
            assert at+8+size<=len(blob)
            chunks.append(dict(tag=blob[at:at+4].decode('ascii'),bytes=size,sha256=hashlib.sha256(blob[at:at+8+size]).hexdigest()))
        assert all(c['tag']in ('RDEF','ISGN','OSGN','ISG1','OSG1','SHEX','SHDR','STAT','SFI0')for c in chunks)
        shaders.append(dict(pass_index=index,source=s,chunks=chunks,standalone_shader_chunks_not_om_descriptors=True))
    after=[ref(p)for p in sources];assert before==after and exe_before==ref(exe)
    result=dict(schema='zerosis.original_water_fog.phase8.retail_blend_boundary.v1',status='PASS_PINNED_WATER_SHADER_METADATA_BLEND_UNRESOLVED',
        inputs=before,original_exe=exe_before,pe_image_base=base,shader_registry_table=table,binding_names=names,
        water_effect_record=locate(int(water['record'],16),pipeline['effect_records']['stride']),
        effect_table_layout=pipeline['effect_records']['pass_record'],pass_count=water['pass_count_field'],pixel_shaders=shaders,
        confirmed=dict(shader_internal_premultiplied_overlay=True,post_colour_order=contract['confirmed_water']['colour_order'],
            output_alpha=contract['confirmed_water']['alpha'],hardware_om_blend_state=False),
        boundaries=[
            'The existing pass-layout trace identifies five shader handles and a pass count, not blend descriptors.',
            'Standalone shader chunks and output alpha do not determine D3D11 blend enable, factors, operations or write masks.',
            'No new static proof connecting retail WaterShader draw submission to an OM blend descriptor was found in this scoped review.',
            'No retail OM call-chain disassembly, live state capture, game execution or original blending-state acceptance is claimed.',
            'Current water opaque scene composition and RGB-only alpha coast/river blending remain isolated-renderer candidates.',
            'The new water FOW colour functions preserve their supplied alpha; current upstream opaque scene alpha is one.'
        ],original_files_unchanged=True,new_raw_asset_or_shader_copy_retained=False,native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False)
    output=Path(__file__).with_suffix('.json');write_new(output,result)
    print(json.dumps(dict(status=result['status'],passes=len(shaders),evidence=ref(output))))

if __name__=='__main__':main()
