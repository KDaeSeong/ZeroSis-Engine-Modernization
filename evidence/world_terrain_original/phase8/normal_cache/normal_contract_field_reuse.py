"""Reuse identical strict HLSL passes and audit the current CPU/GPU field ABI."""
from pathlib import Path
import hashlib,json,re

ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
OUT=ROOT/'normal_contract_shader'


def artifact(path):
    path=Path(path).absolute();before=path.stat();raw=path.read_bytes();after=path.stat()
    assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),file_identity=[after.st_dev,after.st_ino],mtime_ns=after.st_mtime_ns)


def main():
    OUT.mkdir(exist_ok=True);target=OUT/'normal_contract_field_reuse.json';assert not target.exists()
    paths={name:PROJECT/'Source/Presentation'/name for name in ('OriginalLightingFieldShader.h','OriginalLightingFieldGpuTypes.inc',
        'OriginalLightingFieldGpu.inc','OriginalTerrainGpu.inc','WorldTerrainRenderer.cpp')}
    before={name:artifact(path) for name,path in paths.items()}
    source={name:path.read_text('ascii') for name,path in paths.items()}
    stage6=PROJECT/'evidence/world_terrain_original/phase6/review/field_shader'
    old_refs={name:artifact(stage6/name/'result.json') for name in ('attempt01','attempt02')}
    old={name:json.loads(Path(row['path']).read_bytes()) for name,row in old_refs.items()}
    literals={}
    for short,name in (('height','HeightShaderSource'),('normal','NormalShaderSource')):
        match=re.search(name+r'\[\]\s*=\s*R"([A-Za-z0-9_]*)\((.*?)\)\1";',source['OriginalLightingFieldShader.h'],re.S)
        assert match;literal=match[2].encode('ascii');digest=hashlib.sha256(literal).hexdigest()
        owner='attempt02' if short=='height' else 'attempt01'
        assert digest==old[owner]['literal_sha256'][short]
        literals[short]=dict(bytes=len(literal),sha256=digest,reused_from=old_refs[owner])
    compiler=artifact(old['attempt02']['compiler']['path'])
    assert compiler['sha256']==old['attempt01']['compiler']['sha256']==old['attempt02']['compiler']['sha256']=='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
    passes=[]
    for stem,owner in (('height','attempt02'),('normal','attempt01')):
        for row in old[owner]['passes']:
            if row['stem']!=stem:continue
            assert row['exit_code']==0 and '/Ges' in row['command'] and '/WX' in row['command']
            assert all(row['reflection']['checks'].values())
            artifact(row['log']['path'])
            passes.append(dict(stem=stem,entry=row['entry'],profile=row['profile'],literal_sha256=literals[stem]['sha256'],
                historical_result=old_refs[owner],historical_exit_code=0,historical_command=row['command'],
                historical_bytecode=row['bytecode'],reflection=row['reflection'],compiler_log=artifact(row['log']['path']),
                current_bytecode_retained=False,current_fxc_execution=False))
    assert len(passes)==4 and {(row['stem'],row['profile']) for row in passes}=={(s,p) for s in ('height','normal') for p in ('vs_5_0','ps_5_0')}
    gpu=source['OriginalLightingFieldGpu.inc'];types=source['OriginalLightingFieldGpuTypes.inc'];terrain=source['OriginalTerrainGpu.inc']
    checks=[]
    def check(name,test):assert test,name;checks.append(dict(name=name,pass_=True))
    check('field_cb160_float4x10_unchanged','float materials[8][4],origin[4],parameters[4]' in types and 'sizeof(LightingFieldConstants)==160' in types)
    check('height68_R16_FLOAT_single_mip','td.Width=td.Height=68' in gpu and 'td.Format=DXGI_FORMAT_R16_FLOAT' in gpu and 'td.MipLevels=td.ArraySize=1' in gpu)
    check('normal66_RGBA8_UNORM_policy','td.Width=td.Height=66' in gpu and 'td.Format=DXGI_FORMAT_R8G8B8A8_UNORM' in gpu)
    check('shadow66_R16_UNORM_retained','td.Format=DXGI_FORMAT_R16_UNORM' in gpu and 'D3D11_SUBRESOURCE_DATA initial{shadow66.data(),66*2,0}' in gpu)
    check('known68_R8_UINT_unchanged','known68.size()==68*68' in gpu and 'td.Format=DXGI_FORMAT_R8_UINT' in gpu)
    check('all_saved_resource_arrays_45',len(re.findall(r'ShaderResourceView[^;\n]*,45>',gpu))>=5 and not re.search(r'ShaderResourceView[^;\n]*,43>',gpu))
    check('one_get_exact45','PSGetShaderResources(0,45,rawResources.data())' in gpu and gpu.count('PSGetShaderResources(')==1)
    check('save_attach_loop_bound_by_same_array','for(unsigned i=0;i<resources.size();++i)resources[i].Attach(rawResources[i])' in gpu)
    check('restore_collect_and_bind_same45','for(unsigned i=0;i<resources.size();++i)oldResources[i]=resources[i].Get()' in gpu and 'PSSetShaderResources(0,45,oldResources.data())' in gpu)
    check('hazard_clear45_before_OM','PSSetShaderResources(0,45,empty.data());cache.context->OMSetRenderTargets(0,nullptr,nullptr)' in gpu)
    check('draw_and_post_height_cleanup45','PSSetShaderResources(0,45,resources.data())' in gpu and 'OMSetRenderTargets(0,nullptr,nullptr);cache.context->PSSetShaderResources(0,45,empty.data())' in gpu)
    check('normal_height_mask_two_private_inputs','PSSetShaderResources(0,2,heightInputs)' in gpu)
    check('main_terrain_resource_array_45','std::array<ID3D11ShaderResourceView*,45> resources{}' in terrain and 'PSSetShaderResources(0,static_cast<UINT>(resources.size()),resources.data())' in terrain)
    check('main_terrain_exit_clear45','clear[45]{};cache.context->PSSetShaderResources(0,45,clear)' in source['WorldTerrainRenderer.cpp'])
    check('field_views_68_then66','D3D11_VIEWPORT heightViewport{0,0,68,68,0,1}' in gpu and 'D3D11_VIEWPORT normalViewport{0,0,66,66,0,1}' in gpu)
    after={name:artifact(path) for name,path in paths.items()};assert before==after
    report=dict(schema='zerosis.phase8.normal_contract.field_shader_reuse.v1',status='PASS_FOUR_IDENTICAL_STRICT_FIELD_SHADERS_REUSED_AND_CURRENT_ABI_AUDITED',
        current_sources=before,compiler=compiler,literals=literals,passes=passes,static_checks=checks,check_count=len(checks),
        fresh_shader_compiles=0,reused_strict_shader_stages=4,old_evidence_modified=False,
        precision_policy=dict(current_height='R16_FLOAT red has the same binary16 component precision as recovered RGBA16_FLOAT source; other original channels are not represented.',
            current_normal='R8G8B8A8_UNORM retains recovered 8-bit component precision; actual original RTV/SRV gamma view selection remains unknown.',
            current_shadow='Existing R16_UNORM CPU shadow upload retained; no new original-format equivalence is claimed.',
            original_scratch='Custom0x102=>RGBA8_TYPELESS27 plusUNORM28/SRGB29; quality-dependent128/256/512 allocation/full mip chains.',
            current_scratch='68height/66normal two-/one-texel halo, mip0, current bilinear/wrap and view policy remain candidates.'),
        actual_gpu_or_original_view_selection_verified=False,host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
        new_payload_or_shader_bytecode_generated=False)
    with target.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],checks=len(checks),reused_stages=4,path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest())))


if __name__=='__main__':main()
