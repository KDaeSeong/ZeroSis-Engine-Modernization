"""Pin actual reflection classes, resource/sampler and water OM call paths."""
from water_pe_view import Pe, PROJECT, STAGE, ref, write_new
import hashlib
import json
import re
import struct


def main():
    pe=Pe()
    ranges={
        'reflection_classes':(0x5a0f80,0x5a105b),
        'units_reflection_names':(0x609730,0x60977f),
        'wonders_reflection_name':(0x6ec630,0x6ec654),
        'landmarks_reflection_name':(0x69e5b0,0x69e5e8),
        'ice_reflection_dispatch':(0x751f30,0x751f41),
        'reflection_create':(0x5f0a33,0x5f0ac8),
        'render_resource_formats':(0x8bc880,0x8bc8cc),
        'raw_rtv_creation':(0x8bca88,0x8bcac7),
        'normal_and_srgb_srv_creation':(0x8bcae0,0x8bcb54),
        'water_stage_creation':(0x73abe5,0x73ac1e),
        'water_raw_reflection_binding':(0x73acac,0x73acde),
        'stage_wrapper':(0x8cd6a0,0x8cd718),
        'stage_blend_index_storage':(0x8cd0db,0x8cd0fb),
        'default_blend_registers':(0x8be436,0x8be459),
        'water_blend_template_eight':(0x8be5dc,0x8be61f),
        'blend_state_creation':(0x8be637,0x8be6ea),
        'stage_om_blend_submission':(0x8c036a,0x8c03b2),
        'stage_om_blend_submission_alternate':(0x8c0dbc,0x8c0e04),
        'draw_resource_and_sampler_call':(0x8bf670,0x8bf6be),
        'draw_srv_variant_and_sampler':(0x8bd160,0x8bd1d5),
        'sampler_zero_initialization':(0x8be700,0x8be785),
        'draw_ps_resource_submission':(0x8bf713,0x8bf727),
        'draw_ps_sampler_submission':(0x8bf7b0,0x8bf7c8),
    }
    blocks={}
    for key,(start,stop) in ranges.items():
        raw=pe.data(start,stop-start);rows=pe.rows(start,stop)
        assert sum(n for a,n,m,o in rows)==len(raw),key
        blocks[key]=dict(start=f'{start:08x}',stop=f'{stop:08x}',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                         instructions=[dict(va=f'{a:08x}',mnemonic=m,operands=o) for a,n,m,o in rows])
    checks=[]
    def has(key,*snippets):
        lines=[r['mnemonic']+' '+r['operands'] for r in blocks[key]['instructions']]
        assert all(s in lines for s in snippets),(key,snippets)
        checks.append(dict(block=key,required_instructions=snippets))
    has('reflection_classes','test byte ptr [esi + 0x1b4], 0x40','test byte ptr [esi + 0x1b4], 0x20',
        'test byte ptr [esi + 0x1b4], 2','test byte ptr [esi + 0x1b4], 1',
        'call 0x609730','call 0x6ec630','call 0x69e5b0','call 0x751f30')
    names={hex(a):pe.string(a) for a in [0xa2633c,0xa2634c,0xa228ec,0xa3473c,0xa28cd8]}
    assert list(names.values())==['UnitsReflection','UnitsAlphaReflection','WondersReflection','LandmarksReflection','Reflection Texture Raw']
    has('ice_reflection_dispatch','push 1','push 0','call 0x5facb0')
    has('render_resource_formats','cmp eax, 0x102','mov edx, 0x1c','mov ecx, 0x1b','mov dword ptr [esp + 8], 0x1d')
    has('raw_rtv_creation','mov edx, dword ptr [edx + 0x24]','call edx')
    has('normal_and_srgb_srv_creation','mov eax, dword ptr [ecx + 0x1c]','call eax','call edx')
    has('water_raw_reflection_binding','movzx edx, word ptr [0xda12c0]','mov word ptr [ecx + 0x20], dx','mov word ptr [ecx + 0x54], ax')
    has('draw_srv_variant_and_sampler','cmp dword ptr [ecx + ebp*8 + 0x30568], 0','mov esi, dword ptr [esi + 4]',
        'mov esi, dword ptr [esi]','mov esi, dword ptr [ecx + esi*8 + 0x30564]')
    has('sampler_zero_initialization','lea eax, [edi + 0x30564]','mov dword ptr [eax + 4], ebp',
        'mov ebx, 0x15','mov dword ptr [esp + 0x2c], esi','mov dword ptr [esp + 0x30], esi',
        'mov dword ptr [esp + 0x34], esi','mov ecx, dword ptr [edx + 0x5c]','call ecx')
    # Track the wrapper's concrete stack permutation rather than guessing the
    # meaning of its compact "8" argument from an effect name or PS alpha.
    sp=0;memory={4*i:('arg',i) for i in range(1,14)};regs={};fp=None
    def address(expression):
        match=re.fullmatch(r'\[(esp|eax)(?: \+ (0x[0-9a-f]+|[0-9]+))?\]',expression)
        assert match,expression
        base=sp if match[1]=='esp' else regs['eax'][1]
        return base+(int(match[2],0) if match[2] else 0)
    def value(expression):
        expression=expression.removeprefix('dword ptr ')
        if expression.startswith('['):return memory[address(expression)]
        if expression in regs:return regs[expression]
        if expression=='esp':return ('stack',sp)
        return ('literal',int(expression,0))
    for a,n,m,o in pe.rows(*ranges['stage_wrapper']):
        if m=='sub':
            dst,src=o.split(', ');assert dst=='esp';sp-=int(src,0)
        elif m=='push':sp-=4;memory[sp]=value(o)
        elif m in ('mov','movss'):
            dst,src=o.split(', ');v=value(src)
            if dst.startswith('dword ptr '):memory[address(dst.removeprefix('dword ptr '))]=v
            else:regs[dst]=v
        elif m=='fld':fp=value(o)
        elif m=='fstp':memory[address(o.removeprefix('dword ptr '))]=fp
        elif m=='call':
            assert o=='0x8ccfb0';break
        else:raise AssertionError((m,o))
    arguments=[memory[sp+4*i] for i in range(21)]
    assert arguments==[('arg',1)]+[('literal',0)]*8+[('arg',i) for i in range(2,14)]
    assert arguments[9]==('arg',2)
    has('stage_blend_index_storage','mov esi, dword ptr [esp + 0x34]','mov dword ptr [eax + edx + 0x40], esi')
    has('water_stage_creation','push 3','push 8','call 0x8cd6a0')
    has('water_blend_template_eight','mov dword ptr [esp + 0x128], esi','mov dword ptr [esp + 0x12c], 5',
        'mov dword ptr [esp + 0x130], 6','mov dword ptr [esp + 0x134], esi',
        'mov dword ptr [esp + 0x138], eax','mov dword ptr [esp + 0x13c], eax',
        'mov dword ptr [esp + 0x140], esi','mov byte ptr [esp + 0x144], cl')
    has('blend_state_creation','mov dword ptr [esp + 0x14], 9','mov edx, dword ptr [edx + 0x50]','call edx','add edi, 0x20','add ebp, 0x14')
    has('stage_om_blend_submission','mov eax, dword ptr [esi + 0x40]','mov ecx, dword ptr [ecx + 0x8c]',
        'mov eax, dword ptr [eax + 0x30964]','call ecx')
    has('stage_om_blend_submission_alternate','mov eax, dword ptr [edi + 0x40]',
        'mov edx, dword ptr [esi + eax*4 + 0x30964]','mov eax, dword ptr [ecx + 0x8c]','call eax')
    all_draw=pe.rows(0x8bf5b0,0x8bfe20)
    assert not any('0x8c]' in o or '0x30964' in o for a,n,m,o in all_draw),'Per-draw override needs a new trace'
    registry=json.loads((PROJECT/'evidence/world_terrain_original/retail_renderer_probe.json').read_text('utf8'))
    water=next(r for r in registry['shader_registry']['shaders'] if r['name']=='WaterShader')
    assert len(water['bindings'])==14 and water['bindings'][4]=='ReflectionMap'
    assert struct.unpack('<f',pe.data(0xa07094,4))[0]>1e38
    pe.verify()
    result=dict(schema='zerosis.phase10.water_reflection_state_contract.v1',status='PASS_RETAIL_RAW_REFLECTION_SAMPLER_AND_WATER_OM_STATE',scope='NoNative0',
        original_exe=pe.before,source=ref(__file__),blocks=blocks,checks=checks,wrapper_stage_arguments=arguments,strings=names,
        confirmed=dict(reflection_callbacks=[dict(mask=64,classes=['units_opaque','units_alpha'],entry='00609730'),
            dict(mask=32,classes=['wonders'],entry='006ec630'),dict(mask=2,classes=['landmarks'],entry='0069e5b0'),
            dict(mask=1,classes=['ice'],entry='00751f30',ice_identification='Existing map feature-list evidence globald68f9c plus renderer target 5facb0; not a forest/terrain callback')],
            reflection_texture=dict(global_handle='00da12c0',format_typeless=27,rtv_format=28,normal_srv=28,srgb_srv=29,water_binding_slot=4,water_sampler_index=0),
            water_reflection_sampler=dict(filter=21,address_u=1,address_v=1,address_w=1,srgb_decode=False,max_lod_float_bits=f'{pe.u32(0xa07094):08x}'),
            water_blend=dict(index=8,enabled=True,source_rgb=5,destination_rgb=6,rgb_operation=1,source_alpha=2,destination_alpha=2,alpha_operation=1,write_mask=15,independent_blend=False,alpha_to_coverage=False),
            water_colour_order='WaterPS gamma -> overlay -> gray/FOW/LUT -> distance fog -> OM source-alpha RGB blend and additive alpha'),
        corrections_to_phase8=['Raw reflection four scene callbacks do not contain terrain or forests.',
            'Water ReflectionMap t4 and final Terrain t9 both bind the original Raw reflection resource.',
            'Raw reflection RTV is RGBA8_UNORM; water ReflectionMap SRV is UNORM with LINEAR_WRAP.',
            'Water OM blend is state8 rather than opaque. Source alpha is not overwritten to one before OM.'],
        unresolved=['Original reflection camera and water-plane runtime constant producer still require call-chain reconstruction.',
            'Current candidate screen/world projector and original scene-class asset/instance providers are separate runtime contracts.',
            'Dynamic original callbacks, full-scene visibility, native rendering and screen acceptance remain held.'],
        native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,original_inputs_modified=False,asset_payload_copies=0)
    output=write_new('water_retail_state_contract.json',result)
    print(json.dumps(dict(status=result['status'],blocks=len(blocks),checks=len(checks),output=output)))


if __name__=='__main__':main()
