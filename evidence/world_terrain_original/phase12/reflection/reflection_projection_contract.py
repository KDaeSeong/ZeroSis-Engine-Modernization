"""Pin the base reflection projector and Water PS consumer without native load."""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
READER=PROJECT/'evidence/world_terrain_original/phase10/reflection/water_pe_view.py'
spec=importlib.util.spec_from_file_location('reflection_contract_pe',READER)
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)


def main():
    output=ROOT/'reflection_projection_contract.json';assert not output.exists()
    pe=reader.Pe();checks=[]
    traces={name:json.loads((ROOT/(name+'.json')).read_text('utf8')) for name in (
        'reflection_owners_aligned','reflection_raw_view_consumers','reflection_bounds_axis','reflection_raw_selector')}
    for trace in traces.values():assert trace['original']==pe.before

    def has(trace,block,*pairs):
        items={int(row['va'],16):(row['mnemonic'],row['operands']) for row in traces[trace]['blocks'][block]['instructions']}
        for address,mnemonic,operands in pairs:
            assert items[address]==(mnemonic,operands),(hex(address),items.get(address),mnemonic,operands)
            checks.append(dict(address=hex(address),mnemonic=mnemonic,operands=operands,trace=trace,block=block))
    has('reflection_owners_aligned','projector_complete',
        (0x615960,'movss','xmm2, dword ptr [0xda1b90]'),(0x615968,'movss','xmm7, dword ptr [0xda1b60]'),
        (0x615983,'addss','xmm0, xmm7'),(0x6159aa,'mulss','xmm0, xmm1'),
        (0x6159c4,'xorps','xmm3, xmm0'),(0x6159c7,'addss','xmm3, dword ptr [0xda1b64]'),
        (0x615a1c,'mulss','xmm2, xmm1'),(0x615a3c,'mulss','xmm0, xmm1'),
        (0x615ad5,'movss','dword ptr [esp + 0x44], xmm0'),(0x615adb,'movss','dword ptr [esp + 0x48], xmm1'),
        (0x615ae1,'movss','dword ptr [esp + 0x4c], xmm0'),
        (0x615aff,'fld','dword ptr [0x9fcfdc]'),(0x615b13,'sub','esp, 0x18'),
        (0x615b16,'fstp','dword ptr [esp + 0x14]'),(0x615b1d,'fld','dword ptr [0x9f1588]'),
        (0x615b2a,'fstp','dword ptr [esp + 0x10]'),(0x615b2e,'movss','dword ptr [esp + 0xc], xmm0'),
        (0x615b34,'fld','dword ptr [esp + 0x50]'),(0x615b38,'movss','xmm0, dword ptr [esp + 0x4c]'),
        (0x615b3e,'fstp','dword ptr [esp + 8]'),(0x615b49,'movss','dword ptr [esp + 4], xmm0'),
        (0x615b4f,'fstp','dword ptr [esp]'),(0x615b53,'call','0x8a86d4'),
        (0x615c0e,'movss','xmm0, dword ptr [ebx + 0x75744]'),(0x615c16,'movss','xmm1, dword ptr [ebx + 0x75748]'),
        (0x615c1e,'movss','xmm2, dword ptr [ebx + 0x7574c]'),(0x615c26,'mulss','xmm0, xmm3'),
        (0x615c3a,'xorps','xmm0, xmm3'),(0x615c3d,'addss','xmm0, dword ptr [esp + 0x1c]'),
        (0x615c96,'call','0x8a86e0'),(0x615cb0,'call','0x8a868c'),
        (0x615cbe,'mov','edi, 0xda1890'),(0x615cd1,'mov','edi, 0xda1a90'),(0x615ce9,'mov','edi, 0xda1990'))
    has('reflection_bounds_axis','bounds_reduction',
        (0x5d05f5,'comiss','xmm2, xmm0'),(0x5d05f8,'ja','0x5d0603'),(0x5d0600,'movaps','xmm2, xmm0'),
        (0x5d0603,'comiss','xmm0, xmm3'),(0x5d0606,'ja','0x5d060b'),(0x5d0608,'movaps','xmm3, xmm0'),
        (0x5d064b,'mov','dword ptr [esi + 0xda1b60], eax'),(0x5d066f,'mov','dword ptr [esi + 0xda1b64], ecx'),
        (0x5d069a,'mov','dword ptr [esi + 0xda1b90], eax'),(0x5d06a6,'mov','dword ptr [esi + 0xda1b94], ecx'))
    has('reflection_raw_view_consumers','units_raw_view',
        (0x63a904,'cmp','byte ptr [esp + 0x84], 0'),(0x63a930,'push','0xda1a90'),
        (0x63a935,'lea','ecx, [edi + 0xda1990]'),(0x63a954,'call','0x8a868c'))
    has('reflection_raw_view_consumers','ice_raw_view',
        (0x5faee6,'mov','esi, 0xda1990'),(0x5faeeb,'test','bl, bl'),(0x5faeef,'mov','esi, 0xda1310'),
        (0x5faf66,'mov','esi, 0xda1a90'),(0x5faf6b,'test','bl, bl'),(0x5faf6f,'mov','esi, 0xda12d0'))
    has('reflection_raw_view_consumers','shader_projector_binding',
        (0x73aac3,'lea','esi, [eax + 0xda1890]'),(0x73aac9,'lea','edi, [ebx + 0x160]'),
        (0x73aacf,'mov','ecx, 0x10'),(0x73aad4,'rep movsd','dword ptr es:[edi], dword ptr [esi]'))
    # Independently resolve PE32 imports instead of naming a thunk from memory.
    pe_at=struct.unpack_from('<I',pe.raw,60)[0];opt=pe_at+24
    directory=pe.base+struct.unpack_from('<I',pe.raw,opt+104)[0];imports={}
    while True:
        original,stamp,chain,name,first=struct.unpack('<5I',pe.data(directory,20))
        if not any((original,stamp,chain,name,first)):break
        module=pe.string(pe.base+name)
        index=0
        while True:
            value=pe.u32(pe.base+(original or first)+index*4)
            if not value:break
            if not value&0x80000000:imports[pe.base+first+index*4]=(module,pe.string(pe.base+value+2))
            index+=1
        directory+=20
    thunk_contract={0x8a868c:'D3DXMatrixMultiply',0x8a86d4:'D3DXMatrixOrthoOffCenterRH',0x8a86e0:'D3DXMatrixLookAtRH'}
    thunks=[]
    for address,name in thunk_contract.items():
        raw=pe.data(address,6);assert raw[:2]==b'\xff\x25'
        iat=struct.unpack_from('<I',raw,2)[0];module,actual=imports[iat]
        assert actual==name and module.lower()=='d3dx9_42.dll',(address,actual)
        thunks.append(dict(address=hex(address),iat=hex(iat),module=module,name=name,sha256=hashlib.sha256(raw).hexdigest()))
    constants={hex(address):dict(bits=hex(pe.u32(address)),value=struct.unpack('<f',pe.data(address,4))[0]) for address in (0x9dc2c8,0x9f1588,0x9fcfdc,0x9fcf90,0x9f72f4)}
    assert [value['value'] for value in constants.values()]==[5000,30000,-30000,.5,1]
    shader=PROJECT/'evidence/world_terrain_original/phase3/semantics/bytecode/WaterShader_2_ps.asm'
    previous=json.loads((shader.parents[1]/'shader_semantics.json').read_text('utf8'))
    pinned=next(row['listing'] for row in previous['shaders'] if Path(row['listing']['path'])==shader)
    assert reader.ref(shader)['sha256']==pinned['sha256']
    asm=shader.read_text('utf-8-sig')
    shader_rows=[
        'mul r6.xyz, v3.yyyy, cb1[23].xywx',
        'mad r6.xyz, v3.xxxx, cb1[22].xywx, r6.xyzx',
        'mad r6.xyz, v3.zzzz, cb1[24].xywx, r6.xyzx',
        'add r6.xyz, r6.xyzx, cb1[25].xywx',
        'div r3.zw, r6.xxxy, r6.zzzz',
        'mad r3.zw, r3.zzzw, l(0.000000, 0.000000, 0.500000, -0.500000), l(0.000000, 0.000000, -0.500000, -0.500000)',
        'sample_indexable(texture2d)(float,float,float,float) r6.xyzw, r3.zwzz, t4.xyzw, s4']
    assert all(row in asm.splitlines() for row in shader_rows)
    # A direct call target scan is candidate provenance until its instruction
    # boundary and incoming argument path have also been checked.
    section=next(row for row in pe.sections if row[4]=='.text')
    code=pe.raw[section[3]:section[3]+section[2]];candidates={}
    for target in (0x615950,0x63a7a0):
        candidates[hex(target)]=[hex(section[0]+at) for at in range(len(code)-4) if code[at]==0xe8 and section[0]+at+5+struct.unpack_from('<i',code,at+1)[0]==target]
    pe.verify()
    result=dict(schema='zerosis.phase12.reflection_projection_contract.v1',status='PASS_BASE_REFLECTION_PROJECTOR_AND_WATER_UV_STATIC',
        scope='NoNative0',original=pe.before,writer=reader.ref(Path(__file__).absolute()),reader=reader.ref(READER),
        traces=[reader.ref(ROOT/(name+'.json')) for name in traces],imports=thunks,constants=constants,instruction_checks=checks,
        shader=dict(file=reader.ref(shader),semantic_receipt=reader.ref(shader.parents[1]/'shader_semantics.json'),required_rows=shader_rows),
        confirmed=dict(bounds_xy_minimum='DA1B60/64',bounds_xy_maximum='DA1B90/94',
            center='(DA1B90/94/98 + DA1B60/64/68) * .5',signed_xy_span='Dx=(minX-maxX)*.5; Dy=(minY-maxY)*.5',
            eye='center - 5000 * owner[75744/75748/7574c]',target='center',up=[0,1,0],
            ortho_call_order=['out','Dx','-Dx','Dy','-Dy',30000,-30000],
            ortho_argument_stores=dict(left='615b4f:[esp]',right='615b49:[esp+4]',bottom='615b3e:[esp+8]',top='615b2e:[esp+c]',near='615b2a:[esp+10]',far='615b16:[esp+14]'),
            view='DA1990',projection='DA1A90',view_projection='DA1890 = view * projection',
            producer='Units helper reflection branch and ice true branch select these view/projection globals',
            consumer='Water cb1 byte 0x160 = rows22..25 receives DA1890; base UV uses XY/W then (.5,-.5)+(-.5,-.5)',
            camera_depth_slab='View Z=-30000 maps to depth0; View Z=+30000 maps to depth1',
            units='5000 and +/-30000 are original renderer coordinates; no metres or current-world scale is inferred',
            resource_owner='Water Raw UNORM+WRAP is separate from terrain static t9 UNORM+CLAMP'),
        candidates_and_open=dict(current_to_original_world_scale='Current adapter requires an explicit supplied affine matrix; scale100 is unverified',
            original_frame_input_provider=False,current_world_camera_calibration=False,original_water_plane_clipping=False,
            supplied_half_space='Algebraic optional plane conversion only; no recovered original waterline plane',
            indexed_view_adjustment='Loop exists for view count>1; base-view CPU model only',
            units_reflection_bool_dispatch='The conditional matrix selection is proved; full incoming reflection-bool caller chain is separate',
            d3dx_bitwise_float_parity=False,direct_call_candidates=candidates),
        native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],instruction_checks=len(checks),output=reader.ref(output))))


if __name__=='__main__':main()
