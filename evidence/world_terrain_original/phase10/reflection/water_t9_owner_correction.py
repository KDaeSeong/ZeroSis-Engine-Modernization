"""Correct the prior Raw-reflection/t9 inference using the actual owner+8 base."""
import hashlib
from water_pe_view import Pe, STAGE, PROJECT, ref, write_new


def main():
    pe=Pe();ranges={
        'renderer_constructor':(0x40fe10,0x40fe23),'chunk_owner_argument':(0x5df310,0x5df36e),
        'chunk_owner_storage':(0x679af0,0x679afe),'primary_source_copy':(0x6782cf,0x678303),
        'final_t9_resource_sampler':(0x5ad91e,0x5ad940)}
    blocks={}
    for name,(a,b) in ranges.items():
        rows=pe.rows(a,b);raw=pe.data(a,b-a)
        # The chunk call range ends at the last complete instruction; no decoded
        # operand or call is allowed to depend on an incomplete trailing byte.
        if sum(row[1] for row in rows)!=len(raw):
            b=rows[-1][0]+rows[-1][1];raw=pe.data(a,b-a);rows=pe.rows(a,b)
        blocks[name]=dict(start=f'{a:08x}',stop=f'{b:08x}',sha256=hashlib.sha256(raw).hexdigest(),
            instructions=[dict(va=f'{va:08x}',mnemonic=m,operands=o) for va,n,m,o in rows])
    def require(name,*needles):
        text=[r['mnemonic']+' '+r['operands'] for r in blocks[name]['instructions']]
        assert all(n in text for n in needles),(name,needles)
    require('renderer_constructor','lea ecx, [esi + 8]','call 0x458420')
    require('chunk_owner_argument','lea eax, [esi + 8]','push eax','call 0x679af0')
    require('chunk_owner_storage','mov edx, dword ptr [esp + 8]','mov dword ptr [ecx + 0x13c], edx')
    require('primary_source_copy','lea edi, [ebx + 0x548]','mov ecx, 0xa','rep movsd dword ptr es:[edi], dword ptr [esi]')
    require('final_t9_resource_sampler','movzx eax, word ptr [eax + 0x564]','mov word ptr [edi + 0x2a], ax','mov eax, 5','mov word ptr [edi + 0x5e], ax')
    primary=8+0x564;array=0xda12a4+(primary-0x548)
    assert primary==0x56c and array==0xda12c8
    pe.verify()
    result=dict(schema='zerosis.phase10.final_t9_owner_correction.v1',status='PASS_TERRAIN_T9_SPECSCREENMAP_SEPARATE_FROM_WATER_RAW',scope='NoNative0',
        original=pe.before,blocks=blocks,source=ref(__file__),owner_adjustment=8,owner_t9_offset=0x564,primary_t9_offset=primary,
        primary_array_base=0x548,global_array_base=0xda12a4,final_t9_handle_global=array,terrain_sampler=5,
        confirmed=['Chunk owner is the renderer base subobject at primary+8.',
            'Final terrain t9 reads primary+56c = globalda12c8 = specscreenmap.dds.',
            'Terrain t9 packet sampler index5 is LINEAR_CLAMP with UNORM SRV.',
            'Water ReflectionMap remains globalda12c0 with sampler index0 LINEAR_WRAP/UNORM.'],
        superseded_claims=[dict(path=str(PROJECT/'evidence/world_terrain_original/phase8/screen_lighting/screen_provider_contract.json'),
            invalid_claim='Final t9 is RawReflection globalda12c0; primary object and base-subobject were incorrectly treated as identical.'),
            dict(path=str(STAGE/'water_retail_state_contract.json'),invalid_claim='The claim that both water and terrain consume the same Raw resource; water OM/sampler and scene-class proofs remain valid.'),
            dict(path=str(STAGE/'water_integration_review.json'),invalid_claim='Prior isolated Raw->terrain source integration and screen wrap assumption are superseded; water blend/fog contracts remain valid.')],
        sibling_proofs=[ref(PROJECT/'evidence/world_terrain_original/phase10/cache'/n) for n in ['cache_owner_setter_trace.json','cache_owner_adjustment_trace.json','cache_normal_sampler_trace.json']],
        native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,original_modified=False)
    output=write_new('water_t9_owner_correction.json',result);print(dict(status=result['status'],output=output))


if __name__=='__main__':main()
